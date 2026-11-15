"""Overlap protection and the fleet guard for AUTOMATIC incidents (Feature 021D-2) on SQLite.

The manual drone failure keeps its behaviour: every test that restricts the automatic path also
shows that the same situation is still allowed manually. PostgreSQL concurrency is covered in
`test_random_incidents_postgres.py`.
"""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, OperationalEvent
from app.orders import cancellation
from app.simulation import failure, random_incidents
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import (
    FleetGuardError,
    NoEligibleTargetError,
    eligible_mission_ids,
    fleet_availability,
    trigger_drone_failure,
)
from app.simulation.heartbeat import record_heartbeat
from app.simulation.incident_scheduler import IncidentScheduler
from app.simulation.models import FlightPhase, LprScenario, MissionFlight

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=8)  # the first flight is still outbound


def _flight(session: Session, mission_id: str) -> MissionFlight:
    session.expire_all()
    flight = session.get(MissionFlight, mission_id)
    assert flight is not None
    return flight


def _events(session: Session, kind: str) -> list[OperationalEvent]:
    session.expire_all()
    return list(
        session.scalars(select(OperationalEvent).where(OperationalEvent.event_type == kind))
    )


def _count_events(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OperationalEvent)) or 0


def _ground(session: Session, count: int, keep: set[str]) -> None:
    """Put `count` drones that are not in `keep` into MAINTENANCE."""
    drones = [d for d in session.scalars(select(Drone).order_by(Drone.id)) if d.id not in keep]
    for drone in drones[:count]:
        drone.status = DroneStatus.MAINTENANCE.value
    session.commit()


# --- overlap protection -----------------------------------------------------------------------


def test_a_flight_with_a_pending_recipient_failure_is_not_an_automatic_failure_target(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    trigger_recipient_unavailable(seeded, LATER, sim_settings, rng=random.Random(1))
    assert _flight(seeded, mission_id).recipient_unavailable_at is not None

    assert eligible_mission_ids(seeded) == [mission_id]  # manual candidates are unchanged
    assert eligible_mission_ids(seeded, exclude_incidents=True) == []
    with pytest.raises(NoEligibleTargetError):
        trigger_drone_failure(
            seeded, LATER, sim_settings, origin=EventOrigin.AUTOMATIC, automatic_safety=True
        )
    assert _flight(seeded, mission_id).failed_at is None
    assert _events(seeded, "DRONE_FAILURE") == []

    manual = trigger_drone_failure(seeded, LATER, sim_settings, rng=random.Random(1))  # still ok
    assert manual.mission_id == mission_id
    assert _flight(seeded, mission_id).failed_at is not None


def test_a_recalled_flight_is_not_an_automatic_failure_target_but_is_a_manual_one(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    cancellation.cancel_order(seeded, "ORD-001", LATER, sim_settings)
    assert _flight(seeded, mission_id).recalled_at is not None

    with pytest.raises(NoEligibleTargetError):
        trigger_drone_failure(seeded, LATER, sim_settings, automatic_safety=True)

    assert trigger_drone_failure(seeded, LATER, sim_settings).mission_id == mission_id


def test_a_flight_whose_handover_failed_is_not_an_automatic_failure_target(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    _flight(seeded, mission_id).handover_failed_at = LATER
    seeded.commit()

    assert eligible_mission_ids(seeded, exclude_incidents=True) == []
    with pytest.raises(NoEligibleTargetError):
        trigger_drone_failure(seeded, LATER, sim_settings, automatic_safety=True)


def test_the_overlap_is_rechecked_under_the_locks_not_only_when_choosing(
    seeded: Session, launch: Launch, sim_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    trigger_recipient_unavailable(seeded, LATER, sim_settings, rng=random.Random(1))
    # A stale candidate list (read before the manual action) still names the flight.
    monkeypatch.setattr(failure, "eligible_mission_ids", lambda *_a, **_k: [mission_id])

    with pytest.raises(NoEligibleTargetError):
        trigger_drone_failure(seeded, LATER, sim_settings, automatic_safety=True)

    assert _flight(seeded, mission_id).failed_at is None
    assert _events(seeded, "DRONE_FAILURE") == []


def test_an_unaffected_flight_is_still_an_automatic_target_and_the_event_is_automatic(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch("ORD-001", "DRN-010")

    result = trigger_drone_failure(
        seeded, LATER, sim_settings, origin=EventOrigin.AUTOMATIC, automatic_safety=True
    )

    assert result.mission_id == mission_id
    (event,) = _events(seeded, "DRONE_FAILURE")
    assert event.origin == EventOrigin.AUTOMATIC.value


# --- fleet guard ------------------------------------------------------------------------------


def test_the_guard_counts_maintenance_and_the_emergency_approach_as_unavailable(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    launch("ORD-001", "DRN-010")
    assert fleet_availability(seeded) == (12, 0)
    _ground(seeded, 2, keep={"DRN-010"})
    assert fleet_availability(seeded) == (12, 2)

    trigger_drone_failure(seeded, LATER, sim_settings)  # the drone is IN_FLIGHT, in its approach

    seeded.expire_all()
    flying = seeded.get(Drone, "DRN-010")
    assert flying is not None and flying.status == DroneStatus.IN_FLIGHT.value
    assert fleet_availability(seeded) == (12, 3)  # the approaching drone already counts


@pytest.mark.parametrize(
    ("extra_drones", "grounded", "allowed"),
    [
        (
            0,
            5,
            True,
        ),  # 12 drones: 12 - 5 - 1 = 6 remain, ceil(12 / 2) = 6 -> allowed (exactly 50 %)
        (0, 6, False),  # 5 would remain
        (1, 5, True),  # 13 drones: ceil(13 / 2) = 7 and 13 - 5 - 1 = 7 -> allowed
        (1, 6, False),  # 6 would remain, 7 are needed
    ],
)
def test_the_guard_boundary_for_even_and_odd_fleets(
    seeded: Session,
    launch: Launch,
    sim_settings: Settings,
    make_drone: Callable[..., Drone],
    extra_drones: int,
    grounded: int,
    allowed: bool,
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    for n in range(extra_drones):
        seeded.add(make_drone(id=f"DRN-{900 + n}", hub_id="hub-forum-gdansk"))
    seeded.commit()
    _ground(seeded, grounded, keep={"DRN-010"})
    events_before = _count_events(seeded)

    def attempt() -> None:
        trigger_drone_failure(
            seeded, LATER, sim_settings, origin=EventOrigin.AUTOMATIC, automatic_safety=True
        )

    if allowed:
        attempt()
        assert _flight(seeded, mission_id).failed_at is not None
        return
    with pytest.raises(FleetGuardError) as refused:
        attempt()
    assert "at least" in str(refused.value)
    flight = _flight(seeded, mission_id)  # nothing was changed
    assert flight.failed_at is None and flight.phase == FlightPhase.OUTBOUND.value
    assert _count_events(seeded) == events_before
    drone = seeded.get(Drone, "DRN-010")
    assert drone is not None and drone.status == DroneStatus.IN_FLIGHT.value


def test_a_second_automatic_failure_counts_the_first_one_still_in_its_approach(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    first = launch("ORD-001", "DRN-010")
    second = launch("ORD-004", "DRN-007")
    _ground(seeded, 5, keep={"DRN-010", "DRN-007"})  # exactly one more failure is allowed

    result = trigger_drone_failure(
        seeded, LATER, sim_settings, rng=random.Random(3), automatic_safety=True
    )
    assert result.mission_id in {first, second}

    # The failed drone is still IN_FLIGHT (approach), yet it already counts: no second failure.
    with pytest.raises(FleetGuardError):
        trigger_drone_failure(
            seeded, LATER, sim_settings, rng=random.Random(3), automatic_safety=True
        )
    others = {first, second} - {result.mission_id}
    assert all(_flight(seeded, m).failed_at is None for m in others)


def test_the_manual_failure_is_never_guarded(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    _ground(seeded, 9, keep={"DRN-010"})  # far below half the fleet

    result = trigger_drone_failure(seeded, LATER, sim_settings)

    assert result.mission_id == mission_id
    assert _flight(seeded, mission_id).failed_at is not None


def test_a_refused_guard_leaves_the_session_usable(
    seeded: Session, launch: Launch, sim_settings: Settings
) -> None:
    launch("ORD-001", "DRN-010")
    _ground(seeded, 6, keep={"DRN-010"})
    with pytest.raises(FleetGuardError):
        trigger_drone_failure(seeded, LATER, sim_settings, automatic_safety=True)

    assert trigger_drone_failure(seeded, LATER, sim_settings).drone_id == "DRN-010"


# --- the scheduler with the real services -----------------------------------------------------


def _scheduler(factory: sessionmaker[Session], **weights: float) -> IncidentScheduler:
    settings = Settings(
        incident_sim_weight_lpr=weights.get("lpr", 0),
        incident_sim_weight_recipient=weights.get("recipient", 0),
        incident_sim_weight_failure=weights.get("failure", 0),
        incident_sim_cooldown_min_seconds=0,
        incident_sim_cooldown_max_seconds=0,
    )
    return IncidentScheduler(settings, rng=random.Random(1))


def _turn_on(factory: sessionmaker[Session], session: Session) -> None:
    record_heartbeat(session, clock.utcnow())
    with factory() as s:
        random_incidents.enable(s, clock.utcnow(), Settings())


def test_the_scheduler_skips_a_drone_failure_the_guard_refuses_and_records_why(
    seeded: Session,
    session_factory: sessionmaker[Session],
    launch: Launch,
    sim_settings: Settings,
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    _ground(seeded, 6, keep={"DRN-010"})
    _turn_on(session_factory, seeded)
    events_before = _count_events(seeded)

    outcome = _scheduler(session_factory, failure=1).run_step(session_factory, LATER, 0.0)

    assert outcome == "Skipped: Drone failure: fleet guard"
    assert _flight(seeded, mission_id).failed_at is None
    assert _count_events(seeded) == events_before  # a skip is not a mission event


def test_the_scheduler_triggers_a_drone_failure_with_the_automatic_origin(
    seeded: Session, session_factory: sessionmaker[Session], launch: Launch
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    _turn_on(session_factory, seeded)

    outcome = _scheduler(session_factory, failure=1).run_step(session_factory, LATER, 0.0)

    assert outcome is not None and outcome.startswith("Triggered: drone DRN-010 failed")
    assert _flight(seeded, mission_id).failed_at is not None
    (event,) = _events(seeded, "DRONE_FAILURE")
    assert event.origin == "AUTOMATIC"


def test_the_scheduler_marks_a_recipient_unavailable_with_the_automatic_origin(
    seeded: Session, session_factory: sessionmaker[Session], launch: Launch
) -> None:
    mission_id = launch("ORD-001", "DRN-010")
    _turn_on(session_factory, seeded)

    outcome = _scheduler(session_factory, recipient=1).run_step(session_factory, LATER, 0.0)

    assert outcome is not None and outcome.startswith("Triggered: recipient unavailable")
    flight = _flight(seeded, mission_id)
    assert flight.recipient_unavailable_at is not None
    assert flight.recipient_unavailable_origin == "AUTOMATIC"


def test_the_scheduler_starts_the_lpr_helicopter_once_and_keeps_its_single_scenario_rule(
    seeded: Session, session_factory: sessionmaker[Session]
) -> None:
    _turn_on(session_factory, seeded)
    sched = _scheduler(session_factory, lpr=1)

    first = sched.run_step(session_factory, NOW, 0.0)
    second = sched.run_step(session_factory, NOW, 1.0)  # the first pass is still crossing

    assert first == "Triggered: LPR helicopter started"
    assert second == "Skipped: LPR helicopter: already crossing the area"
    scenarios = list(seeded.scalars(select(LprScenario)))
    assert [s.origin for s in scenarios] == ["AUTOMATIC"] and len(scenarios) == 1
    (event,) = _events(seeded, "LPR_TRANSIT")
    assert event.origin == "AUTOMATIC"


def test_with_nothing_flying_every_mission_incident_is_skipped(
    seeded: Session, session_factory: sessionmaker[Session]
) -> None:
    _turn_on(session_factory, seeded)
    before = _count_events(seeded)

    outcome = _scheduler(session_factory, recipient=1, failure=1).run_step(
        session_factory, NOW, 0.0
    )

    assert outcome is not None and outcome.startswith("Skipped: ")
    assert "no eligible delivery" in outcome and "no eligible flight" in outcome
    assert _count_events(seeded) == before
