"""Automatic recovery of drones grounded by AUTOMATIC drone failures (Feature 022) on SQLite.

The failures are real: a mission is launched, a failure is triggered and the engine grounds the
drone, all with a controlled clock. PostgreSQL concurrency is in `test_drone_recovery_postgres.py`.
"""

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.config import Settings
from app.dispatch.models import DispatchAutoState
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.hubs.models import Hub
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import hubs_by_distance
from app.orders.models import DeliveryOrder
from app.simulation import engine, random_incidents, recovery
from app.simulation.failure import (
    FleetGuardError,
    fleet_availability,
    trigger_drone_failure,
)
from app.simulation.models import (
    EmergencyReason,
    FlightPhase,
    IncidentSchedulerState,
    MissionFlight,
)
from app.simulation.recovery import (
    NoHubWithRoomError,
    NotEligibleError,
    RecoveryState,
    due_mission_ids,
    recover_grounded_drone,
    run_recovery_step,
)

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
FAILED_AT = 8.0  # the flight is still outbound
LANDED_AT = 300.0  # long after the emergency approach: the engine grounds the drone here
DELAY = 120.0


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


class World:
    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def ground(
        self,
        pairs: list[tuple[str, str]],
        launch: Launch,
        origin: EventOrigin = EventOrigin.AUTOMATIC,
        landed: float = LANDED_AT,
    ) -> list[str]:
        """Launch each (order, drone), fail them all, and let the engine ground the drones."""
        mission_ids = [launch(order, drone) for order, drone in pairs]
        for n in range(len(mission_ids)):
            trigger_drone_failure(
                self.session, at(FAILED_AT), self.settings, origin=origin, rng=random.Random(n)
            )
        for mission_id in mission_ids:
            engine.advance_flight(self.factory, self.settings, mission_id, at(landed))
        self.session.expire_all()
        return mission_ids

    def fail_but_not_land(
        self, pair: tuple[str, str], launch: Launch, origin: EventOrigin = EventOrigin.MANUAL
    ) -> str:
        """Launch and fail one mission, then stop while the emergency approach is still flying."""
        mission_id = launch(*pair)
        trigger_drone_failure(self.session, at(FAILED_AT), self.settings, origin=origin)
        engine.advance_flight(self.factory, self.settings, mission_id, at(FAILED_AT + 1))
        self.session.expire_all()
        return mission_id

    def drone_of(self, mission_id: str) -> Drone:
        mission = self.session.get(Mission, mission_id)
        assert mission is not None
        drone = self.session.get(Drone, mission.drone_id)
        assert drone is not None
        return drone

    def flight(self, mission_id: str) -> MissionFlight:
        flight = self.session.get(MissionFlight, mission_id)
        assert flight is not None
        return flight

    def events(self, kind: EventType) -> list[OperationalEvent]:
        self.session.expire_all()
        return list(
            self.session.scalars(
                select(OperationalEvent)
                .where(OperationalEvent.event_type == kind.value)
                .order_by(OperationalEvent.id)
            )
        )

    def set_capacity_to_occupancy(self, *, except_hub: str | None = None) -> None:
        """Make every Hub (but `except_hub`) exactly full."""
        hubs = list(self.session.scalars(select(Hub)))
        counts = hub_occupancy(
            list(self.session.scalars(select(Drone))), hubs, self.settings.hub_dock_proximity_m
        )
        for hub in hubs:
            if hub.id != except_hub:
                hub.drone_capacity = max(counts[hub.id], 1)
        self.session.commit()
        self.session.expire_all()


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


def _one(world: World, launch: Launch) -> str:
    return world.ground([("ORD-001", "DRN-010")], launch)[0]


# --- eligibility and timing --------------------------------------------------------------------


def test_the_delay_starts_at_the_landing_not_at_the_failure(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    flight = world.flight(mission_id)
    assert flight.emergency_at is not None
    assert world.drone_of(mission_id).status == DroneStatus.MAINTENANCE.value

    # Counting from the failure (8 s) the drone would be due at 128 s; counting from the landing
    # (300 s) it is due at 420 s.
    assert due_mission_ids(world.session, at(FAILED_AT + DELAY + 1), world.settings) == []
    assert due_mission_ids(world.session, at(LANDED_AT + DELAY - 1), world.settings) == []
    assert due_mission_ids(world.session, at(LANDED_AT + DELAY), world.settings) == [mission_id]


def test_no_early_recovery_and_nothing_changes(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    before = (world.drone_of(mission_id).status, world.drone_of(mission_id).longitude)

    with pytest.raises(NotEligibleError, match="due at"):
        recover_grounded_drone(world.session, mission_id, at(LANDED_AT + 60), world.settings)

    drone = world.drone_of(mission_id)
    assert (drone.status, drone.longitude) == before
    assert world.events(EventType.DRONE_RECOVERED) == []


def test_a_due_automatic_failure_is_recovered_to_the_nearest_hub_with_room(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    drone = world.drone_of(mission_id)
    battery = drone.battery_pct
    position = (drone.longitude, drone.latitude)
    hubs = list(world.session.scalars(select(Hub)))
    nearest = hubs_by_distance(position, hubs)[0][0]

    result = recover_grounded_drone(
        world.session, mission_id, at(LANDED_AT + DELAY), world.settings
    )

    world.session.expire_all()
    drone = world.drone_of(mission_id)
    assert result.hub_id == nearest.id and drone.hub_id == nearest.id
    assert (drone.longitude, drone.latitude) == (nearest.longitude, nearest.latitude)
    assert drone.battery_pct == battery  # the battery is never reset
    assert drone.status == DroneStatus.CHARGING.value  # below 100 %: the charging rules take over
    assert result.status == DroneStatus.CHARGING


def test_a_full_battery_drone_becomes_idle_not_charging(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    drone = world.drone_of(mission_id)
    drone.battery_pct = 100
    world.session.commit()

    result = recover_grounded_drone(
        world.session, mission_id, at(LANDED_AT + DELAY), world.settings
    )

    assert result.status == DroneStatus.IDLE
    assert world.drone_of(mission_id).status == DroneStatus.IDLE.value


def test_the_mission_flight_and_order_are_not_changed_and_history_is_kept(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    mission = world.session.get(Mission, mission_id)
    assert mission is not None and mission.order_id is not None
    order = world.session.get(DeliveryOrder, mission.order_id)
    assert order is not None
    flight = world.flight(mission_id)
    before = (
        mission.status,
        order.status,
        order.updated_at,
        flight.phase,
        flight.emergency_reason,
        flight.emergency_at,
        flight.longitude,
        flight.latitude,
    )
    failures = len(world.events(EventType.DRONE_FAILURE))

    recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)

    world.session.expire_all()
    mission = world.session.get(Mission, mission_id)
    order = world.session.get(DeliveryOrder, order.id)
    flight = world.flight(mission_id)
    assert mission is not None and order is not None
    assert (
        mission.status,
        order.status,
        order.updated_at,
        flight.phase,
        flight.emergency_reason,
        flight.emergency_at,
        flight.longitude,
        flight.latitude,
    ) == before
    assert mission.status == MissionStatus.EMERGENCY.value
    assert flight.phase == FlightPhase.EMERGENCY.value
    assert len(world.events(EventType.DRONE_FAILURE)) == failures  # the failure stays


def test_exactly_one_recovered_event_with_a_unique_key(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)

    recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)

    (event,) = world.events(EventType.DRONE_RECOVERED)
    assert event.mission_id == mission_id and event.flight_id == mission_id
    assert event.drone_id == world.drone_of(mission_id).id
    assert event.origin == EventOrigin.AUTOMATIC.value
    assert (
        event.dedupe_key
        == recovery.recovery_event_key(mission_id)
        == f"DRONE_RECOVERED:{mission_id}"
    )
    assert (
        event.details is not None and event.details["hub_id"] == world.drone_of(mission_id).hub_id
    )
    assert event.occurred_at.replace(tzinfo=UTC) == at(LANDED_AT + DELAY)


# --- provenance ---------------------------------------------------------------------------------


def test_a_manual_failure_is_recovered_like_an_automatic_one_after_the_delay(
    world: World, launch: Launch
) -> None:
    (mission_id,) = world.ground([("ORD-001", "DRN-010")], launch, origin=EventOrigin.MANUAL)
    landed_at = world.flight(mission_id).emergency_at
    assert landed_at is not None

    # not before 120 s after the landing ...
    assert due_mission_ids(world.session, at(LANDED_AT + DELAY - 1), world.settings) == []
    with pytest.raises(NotEligibleError, match="due at"):
        recover_grounded_drone(world.session, mission_id, at(LANDED_AT + 60), world.settings)
    assert world.drone_of(mission_id).status == DroneStatus.MAINTENANCE.value

    # ... and then by the worker's own step, exactly once
    due = at(LANDED_AT + DELAY)
    assert due_mission_ids(world.session, due, world.settings) == [mission_id]
    assert run_recovery_step(world.factory, world.settings, due, RecoveryState()) == 1
    assert run_recovery_step(world.factory, world.settings, due, RecoveryState()) == 0

    world.session.expire_all()
    assert world.drone_of(mission_id).status != DroneStatus.MAINTENANCE.value
    (event,) = world.events(EventType.DRONE_RECOVERED)
    assert event.mission_id == mission_id
    assert event.origin == EventOrigin.AUTOMATIC.value  # the recovery itself is automatic
    (failure,) = [e for e in world.events(EventType.DRONE_FAILURE) if e.mission_id == mission_id]
    assert failure.origin == EventOrigin.MANUAL.value  # and the failure history is unchanged


def test_automatic_and_manual_failures_are_recovered_together_oldest_first(
    world: World, launch: Launch
) -> None:
    older = world.ground(
        [("ORD-001", "DRN-010")], launch, origin=EventOrigin.MANUAL, landed=LANDED_AT
    )[0]
    newer = world.ground(
        [("ORD-002", "DRN-011")], launch, origin=EventOrigin.AUTOMATIC, landed=LANDED_AT + 60
    )[0]
    settings = world.settings.model_copy(update={"drone_recovery_batch_size": 1})
    late = at(LANDED_AT + 60 + DELAY)

    assert due_mission_ids(world.session, late, world.settings) == [older, newer]
    assert run_recovery_step(world.factory, settings, late, RecoveryState()) == 1
    assert [e.mission_id for e in world.events(EventType.DRONE_RECOVERED)] == [
        older
    ]  # oldest first
    assert run_recovery_step(world.factory, settings, late, RecoveryState()) == 1

    assert [e.mission_id for e in world.events(EventType.DRONE_RECOVERED)] == [older, newer]
    world.session.expire_all()
    assert world.drone_of(older).status != DroneStatus.MAINTENANCE.value
    assert world.drone_of(newer).status != DroneStatus.MAINTENANCE.value


def test_a_failure_that_has_not_finished_landing_is_not_eligible(
    world: World, launch: Launch
) -> None:
    mission_id = world.fail_but_not_land(("ORD-001", "DRN-010"), launch)
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY_APPROACH.value  # still flying the approach
    assert flight.emergency_at is None
    far_future = at(LANDED_AT + 100 * DELAY)

    assert due_mission_ids(world.session, far_future, world.settings) == []
    assert run_recovery_step(world.factory, world.settings, far_future, RecoveryState()) == 0
    with pytest.raises(NotEligibleError):
        recover_grounded_drone(world.session, mission_id, far_future, world.settings)

    world.session.expire_all()
    assert world.drone_of(mission_id).status == DroneStatus.IN_FLIGHT.value
    assert world.events(EventType.DRONE_RECOVERED) == []


def test_the_service_can_be_reused_by_a_future_operator_recovery(
    world: World, launch: Launch
) -> None:
    (mission_id,) = world.ground([("ORD-001", "DRN-010")], launch, origin=EventOrigin.MANUAL)

    result = recover_grounded_drone(
        world.session,
        mission_id,
        at(LANDED_AT + 1),  # no waiting
        world.settings,
        wait_for_delay=False,
        origin=EventOrigin.MANUAL,
    )

    assert result.mission_id == mission_id
    (event,) = world.events(EventType.DRONE_RECOVERED)
    assert event.origin == EventOrigin.MANUAL.value


def test_unrelated_maintenance_drones_are_never_recovered(world: World, launch: Launch) -> None:
    _one(world, launch)
    others = [d for d in world.session.scalars(select(Drone)) if d.status != "MAINTENANCE"][:3]
    for drone in others:
        drone.status = DroneStatus.MAINTENANCE.value  # an operator took them out of service
    world.session.commit()
    late = at(LANDED_AT + 10 * DELAY)

    assert run_recovery_step(world.factory, world.settings, late, RecoveryState()) == 1

    world.session.expire_all()
    for drone in others:
        assert world.session.get(Drone, drone.id).status == DroneStatus.MAINTENANCE.value  # type: ignore[union-attr]
    assert len(world.events(EventType.DRONE_RECOVERED)) == 1


def test_other_emergency_reasons_a_moved_drone_and_a_changed_status_are_not_eligible(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    late = at(LANDED_AT + DELAY)
    flight, drone = world.flight(mission_id), world.drone_of(mission_id)

    flight.emergency_reason = EmergencyReason.BATTERY_CRITICAL.value
    world.session.commit()
    assert due_mission_ids(world.session, late, world.settings) == []
    with pytest.raises(NotEligibleError, match="drone-failure emergency"):
        recover_grounded_drone(world.session, mission_id, late, world.settings)
    flight.emergency_reason = EmergencyReason.DRONE_FAILURE.value

    drone.longitude += 0.01  # no longer where the failure grounded it
    world.session.commit()
    assert due_mission_ids(world.session, late, world.settings) == []
    with pytest.raises(NotEligibleError, match="no longer where"):
        recover_grounded_drone(world.session, mission_id, late, world.settings)
    drone.longitude -= 0.01

    drone.status = DroneStatus.IDLE.value  # an operator already handled it
    world.session.commit()
    assert due_mission_ids(world.session, late, world.settings) == []
    with pytest.raises(NotEligibleError, match="not MAINTENANCE"):
        recover_grounded_drone(world.session, mission_id, late, world.settings)


def test_a_later_maintenance_action_after_recovery_is_left_alone(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)
    drone = world.drone_of(mission_id)
    drone.status = DroneStatus.MAINTENANCE.value  # the operator takes it out of service again
    world.session.commit()

    late = at(LANDED_AT + 10 * DELAY)
    assert due_mission_ids(world.session, late, world.settings) == []
    assert run_recovery_step(world.factory, world.settings, late, RecoveryState()) == 0
    assert world.drone_of(mission_id).status == DroneStatus.MAINTENANCE.value


def test_recovery_does_not_need_random_incidents(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    assert random_incidents.is_enabled(world.factory) is False
    assert world.session.scalar(select(func.count()).select_from(IncidentSchedulerState)) == 0

    assert (
        run_recovery_step(world.factory, world.settings, at(LANDED_AT + DELAY), RecoveryState())
        == 1
    )
    assert world.drone_of(mission_id).status != DroneStatus.MAINTENANCE.value


# --- idempotency and restart --------------------------------------------------------------------


def test_a_failure_is_recovered_at_most_once(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    late = at(LANDED_AT + DELAY)

    recover_grounded_drone(world.session, mission_id, late, world.settings)
    with pytest.raises(NotEligibleError):
        recover_grounded_drone(world.session, mission_id, late, world.settings)
    assert run_recovery_step(world.factory, world.settings, late, RecoveryState()) == 0
    assert run_recovery_step(world.factory, world.settings, late, RecoveryState()) == 0

    assert len(world.events(EventType.DRONE_RECOVERED)) == 1


def test_an_existing_recovery_key_blocks_a_second_recovery(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)
    drone = world.drone_of(mission_id)
    drone.status = DroneStatus.MAINTENANCE.value
    drone.longitude, drone.latitude = (
        world.flight(mission_id).longitude,
        world.flight(mission_id).latitude,
    )  # as if it were grounded at the same spot again
    world.session.commit()

    with pytest.raises(NotEligibleError, match="already recovered"):
        recover_grounded_drone(world.session, mission_id, at(LANDED_AT + 2 * DELAY), world.settings)


def test_a_pending_recovery_survives_a_worker_restart(world: World, launch: Launch) -> None:
    mission_id = _one(world, launch)
    world.set_capacity_to_occupancy()  # every Hub is full: the recovery stays pending
    first_worker = RecoveryState()
    due = at(LANDED_AT + DELAY)
    assert run_recovery_step(world.factory, world.settings, due, first_worker) == 0
    assert world.drone_of(mission_id).status == DroneStatus.MAINTENANCE.value

    for hub in world.session.scalars(select(Hub)):
        hub.drone_capacity += 1  # room appears while the worker is "down"
    world.session.commit()
    second_worker = RecoveryState()  # a restart: nothing in memory, everything from the database

    assert run_recovery_step(world.factory, world.settings, at(LANDED_AT + 500), second_worker) == 1
    world.session.expire_all()
    assert world.drone_of(mission_id).status != DroneStatus.MAINTENANCE.value
    assert len(world.events(EventType.DRONE_RECOVERED)) == 1


# --- capacity ------------------------------------------------------------------------------------


def test_a_full_nearest_hub_is_skipped_for_the_next_one_with_room(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    drone = world.drone_of(mission_id)
    hubs = list(world.session.scalars(select(Hub)))
    ranked = [hub for hub, _ in hubs_by_distance((drone.longitude, drone.latitude), hubs)]
    counts = hub_occupancy(
        list(world.session.scalars(select(Drone))), hubs, world.settings.hub_dock_proximity_m
    )
    ranked[0].drone_capacity = max(counts[ranked[0].id], 1)  # the nearest Hub is full
    world.session.commit()
    assert counts[ranked[0].id] >= 1

    result = recover_grounded_drone(
        world.session, mission_id, at(LANDED_AT + DELAY), world.settings
    )

    assert result.hub_id == ranked[1].id


def test_when_every_hub_is_full_nothing_changes_and_it_stays_pending(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    world.set_capacity_to_occupancy()
    before = world.drone_of(mission_id)
    snapshot = (before.status, before.hub_id, before.longitude, before.latitude)
    due = at(LANDED_AT + DELAY)

    with pytest.raises(NoHubWithRoomError):
        recover_grounded_drone(world.session, mission_id, due, world.settings)
    assert run_recovery_step(world.factory, world.settings, due, RecoveryState()) == 0

    world.session.expire_all()
    after = world.drone_of(mission_id)
    assert (after.status, after.hub_id, after.longitude, after.latitude) == snapshot
    assert world.events(EventType.DRONE_RECOVERED) == []
    assert due_mission_ids(world.session, due, world.settings) == [mission_id]  # still pending
    counts = hub_occupancy(
        list(world.session.scalars(select(Drone))),
        list(world.session.scalars(select(Hub))),
        world.settings.hub_dock_proximity_m,
    )
    for hub in world.session.scalars(select(Hub)):
        assert counts[hub.id] <= hub.drone_capacity  # never overfilled


def test_a_hub_is_never_overfilled_by_a_batch(world: World, launch: Launch) -> None:
    ids = world.ground(
        [("ORD-001", "DRN-010"), ("ORD-002", "DRN-011"), ("ORD-003", "DRN-012")], launch
    )
    hubs = list(world.session.scalars(select(Hub)))
    drone = world.drone_of(ids[0])
    nearest = hubs_by_distance((drone.longitude, drone.latitude), hubs)[0][0]
    world.set_capacity_to_occupancy(except_hub=nearest.id)
    counts = hub_occupancy(
        list(world.session.scalars(select(Drone))), hubs, world.settings.hub_dock_proximity_m
    )
    nearest.drone_capacity = counts[nearest.id] + 1  # exactly one free place anywhere
    world.session.commit()

    recovered = run_recovery_step(
        world.factory, world.settings, at(LANDED_AT + DELAY), RecoveryState()
    )

    world.session.expire_all()
    assert recovered == 1
    counts = hub_occupancy(
        list(world.session.scalars(select(Drone))),
        list(world.session.scalars(select(Hub))),
        world.settings.hub_dock_proximity_m,
    )
    for hub in world.session.scalars(select(Hub)):
        assert counts[hub.id] <= hub.drone_capacity


# --- batches -------------------------------------------------------------------------------------


def test_recoveries_are_processed_in_bounded_batches_oldest_first(
    world: World, launch: Launch
) -> None:
    pairs = [
        ("ORD-001", "DRN-010"),
        ("ORD-002", "DRN-011"),
        ("ORD-003", "DRN-012"),
        ("ORD-004", "DRN-007"),
    ]
    ids = world.ground(pairs, launch)
    settings = world.settings.model_copy(update={"drone_recovery_batch_size": 3})
    late = at(LANDED_AT + DELAY)

    assert run_recovery_step(world.factory, settings, late, RecoveryState()) == 3
    assert len(world.events(EventType.DRONE_RECOVERED)) == 3
    assert run_recovery_step(world.factory, settings, late, RecoveryState()) == 1
    assert run_recovery_step(world.factory, settings, late, RecoveryState()) == 0

    assert {e.mission_id for e in world.events(EventType.DRONE_RECOVERED)} == set(ids)


# --- failure handling ---------------------------------------------------------------------------


def test_a_failure_while_recovering_rolls_everything_back(
    world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = _one(world, launch)
    before = world.drone_of(mission_id)
    snapshot = (before.status, before.hub_id, before.longitude, before.latitude)

    def broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("event store unavailable")

    monkeypatch.setattr(recovery, "append_event", broken)
    with pytest.raises(RuntimeError):
        recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)

    world.session.expire_all()
    after = world.drone_of(mission_id)
    assert (after.status, after.hub_id, after.longitude, after.latitude) == snapshot
    assert world.events(EventType.DRONE_RECOVERED) == []


def test_a_failing_step_is_logged_once_and_the_next_drone_still_recovers(
    world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    first, second = world.ground([("ORD-001", "DRN-010"), ("ORD-002", "DRN-011")], launch)
    real = recovery.recover_grounded_drone

    def flaky(session: Session, mission_id: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if mission_id == min(first, second):
            raise RuntimeError("boom")
        return real(session, mission_id, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(recovery, "recover_grounded_drone", flaky)
    state = RecoveryState()
    late = at(LANDED_AT + DELAY)

    with caplog.at_level(logging.ERROR, logger="skyfleet.recovery"):
        assert run_recovery_step(world.factory, world.settings, late, state) == 1
        assert run_recovery_step(world.factory, world.settings, late, state) == 0

    assert len(world.events(EventType.DRONE_RECOVERED)) == 1  # the other drone was recovered
    assert [r.levelno for r in caplog.records].count(
        logging.ERROR
    ) == 1  # logged once, not each look


# --- the fleet guard -----------------------------------------------------------------------------


def test_the_guard_counts_a_grounded_drone_until_it_is_recovered(
    world: World, launch: Launch
) -> None:
    mission_id = _one(world, launch)
    assert fleet_availability(world.session) == (12, 1)

    recover_grounded_drone(world.session, mission_id, at(LANDED_AT + DELAY), world.settings)

    assert fleet_availability(world.session) == (12, 0)


def test_recovery_does_not_weaken_the_fifty_percent_guard(world: World, launch: Launch) -> None:
    grounded = _one(world, launch)
    flying = launch("ORD-004", "DRN-007")  # a flight an automatic failure could hit
    keep = {world.drone_of(grounded).id, "DRN-007"}
    others = [
        d for d in world.session.scalars(select(Drone).order_by(Drone.id)) if d.id not in keep
    ]
    for drone in others[:5]:
        drone.status = DroneStatus.MAINTENANCE.value  # 5 out of service + 1 grounded = 6 of 12
    world.session.commit()
    assert fleet_availability(world.session) == (12, 6)

    with pytest.raises(FleetGuardError):  # the guard still refuses at the boundary
        trigger_drone_failure(
            world.session,
            at(FAILED_AT),
            world.settings,
            origin=EventOrigin.AUTOMATIC,
            rng=random.Random(1),
            automatic_safety=True,
        )

    recover_grounded_drone(world.session, grounded, at(LANDED_AT + DELAY), world.settings)
    assert fleet_availability(world.session) == (12, 5)
    result = trigger_drone_failure(
        world.session,
        at(FAILED_AT),
        world.settings,
        origin=EventOrigin.AUTOMATIC,
        rng=random.Random(1),
        automatic_safety=True,
    )  # one more drone is available again, so the guard now allows exactly one failure
    assert result.mission_id == flying
    assert fleet_availability(world.session)[1] == 6  # and it never goes below half


# --- the worker loop calls the recovery step -----------------------------------------------------


class StopLoopError(Exception):
    pass


def _run_worker(
    monkeypatch: pytest.MonkeyPatch,
    world: World,
    ticks: int,
    now: datetime,
) -> None:
    """Run the real `run_forever` for a fixed number of ticks, with a fixed clock and no waiting."""
    count = {"ticks": 0}
    fake_monotonic = {"now": 0.0}

    def monotonic() -> float:
        fake_monotonic["now"] += 100.0
        return fake_monotonic["now"]

    def sleep(_seconds: float) -> None:
        count["ticks"] += 1
        if count["ticks"] >= ticks:
            raise StopLoopError

    monkeypatch.setattr(worker, "get_engine", lambda: world.session.get_bind())
    monkeypatch.setattr("app.worker.clock.utcnow", lambda: now)
    monkeypatch.setattr("app.worker.time.sleep", sleep)
    monkeypatch.setattr("app.worker.time.monotonic", monotonic)
    with pytest.raises(StopLoopError):
        worker.run_forever(world.settings)


def test_the_worker_loop_recovers_automatic_and_manual_failures_once(
    world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    automatic = world.ground([("ORD-001", "DRN-010")], launch, origin=EventOrigin.AUTOMATIC)[0]
    manual = world.ground([("ORD-002", "DRN-011")], launch, origin=EventOrigin.MANUAL)[0]
    assert random_incidents.is_enabled(world.factory) is False  # recovery needs no other mode

    _run_worker(monkeypatch, world, ticks=4, now=at(LANDED_AT + DELAY + 5))

    world.session.expire_all()
    assert world.drone_of(automatic).status != DroneStatus.MAINTENANCE.value
    assert world.drone_of(manual).status != DroneStatus.MAINTENANCE.value
    recovered = world.events(EventType.DRONE_RECOVERED)
    assert sorted(e.mission_id or "" for e in recovered) == sorted([automatic, manual])  # once each


def test_the_worker_loop_leaves_a_drone_that_is_not_due_grounded(
    world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    (mission_id,) = world.ground([("ORD-001", "DRN-010")], launch, origin=EventOrigin.MANUAL)

    _run_worker(monkeypatch, world, ticks=3, now=at(LANDED_AT + DELAY - 30))

    world.session.expire_all()
    assert world.drone_of(mission_id).status == DroneStatus.MAINTENANCE.value
    assert world.events(EventType.DRONE_RECOVERED) == []


def test_a_recovery_failure_never_stops_the_worker_loop(
    world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def broken(*args: object, **kwargs: object) -> int:
        calls.append(1)
        raise RuntimeError("recovery broke")

    monkeypatch.setattr("app.worker.run_recovery_step", broken)

    _run_worker(monkeypatch, world, ticks=4, now=at(LANDED_AT))  # only StopLoopError escapes

    assert len(calls) >= 2  # the step was tried again on later ticks
    row = world.session.get(DispatchAutoState, "auto-dispatch")  # the other steps kept running
    assert row is not None and not row.enabled
