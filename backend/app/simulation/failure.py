"""Drone failure incident (Feature 018C): the one backend behavior behind every trigger.

`trigger_drone_failure` is what the manual control calls today and what a future automatic trigger
will call: one request, the backend chooses an eligible flying drone, performs the real transition
and records one `DRONE_FAILURE` event in the same transaction, or reports `NoEligibleTargetError`
and creates nothing.

The transition replaces the flight's remaining legs by the leg flown so far, cut at the drone's
current position, and one short EMERGENCY leg to a simulated emergency landing point (a fixed
distance along the current heading, see `flight.emergency_landing_point`). Position and battery
carry on from where they are: no teleport, no reset. The simulation engine then flies the approach
and grounds the drone as MAINTENANCE (`engine._advance_failed`); the original mission never resumes.

Eligible: a flight in OUTBOUND, DELIVERING, RETURNING or DIVERTING (an active 018B recall
included) that has not failed, with an IN_FLIGHT mission and drone, and whose next milestone (the
handover, or the landing decision) the worker has not reached yet. Locks are taken in the engine's
order (flight, mission, order, drone); a candidate that changed in the meantime is skipped.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.missions import repository as mission_repository
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionPurpose, MissionStatus
from app.simulation.clock import as_utc
from app.simulation.engine import write_snapshot
from app.simulation.flight import (
    delivery_leg,
    emergency_landing_point,
    emergency_legs,
    landing_decision,
    leg_from_dict,
    leg_to_dict,
    state_at,
)
from app.simulation.models import FlightPhase, MissionFlight

ELIGIBLE_PHASES: tuple[str, ...] = (
    FlightPhase.OUTBOUND.value,
    FlightPhase.DELIVERING.value,
    FlightPhase.RETURNING.value,
    FlightPhase.DIVERTING.value,
    FlightPhase.RELOCATING.value,
)

_rng = random.Random()


class FailureStage(StrEnum):
    BEFORE_DELIVERY = "BEFORE_DELIVERY"  # the parcel is still on board, nothing was handed over
    RECALL = "RECALL"  # the order was cancelled and the drone is flying back (018B)
    AFTER_DELIVERY = "AFTER_DELIVERY"  # the parcel was delivered; the drone is on its way back
    HANDOVER_FAILED = "HANDOVER_FAILED"  # recipient unavailable; flying back with the parcel (018D)
    RELOCATION = "RELOCATION"  # an empty hub-to-hub relocation flight (019A)


class FleetGuardError(Exception):
    """An AUTOMATIC failure was refused because it would leave too few drones operational."""


# Serialises automatic failures on PostgreSQL (see `_enforce_fleet_guard`); the number is arbitrary.
_AUTOMATIC_FAILURE_LOCK_KEY = 0x5F1EE701


class NoEligibleTargetError(Exception):
    def __init__(
        self, message: str = "No drone is flying a mission that a failure could interrupt"
    ) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class FailureResult:
    drone_id: str
    mission_id: str
    order_id: str | None
    stage: FailureStage
    landing_position: tuple[float, float]


def has_other_incident(flight: MissionFlight) -> bool:
    """A recall, a pending or failed handover: another incident already affects this flight.

    Only AUTOMATIC failures respect it (Feature 021D-2); a manual failure is allowed as before.
    """
    return (
        flight.recalled_at is not None
        or flight.recipient_unavailable_at is not None
        or flight.handover_failed_at is not None
    )


def eligible_mission_ids(session: Session, *, exclude_incidents: bool = False) -> list[str]:
    """Mission ids of the flights that look eligible, in id order (rechecked under locks).

    `exclude_incidents` additionally skips flights another incident already affects (automatic
    failures only; the manual path leaves it off).
    """
    statement = (
        select(MissionFlight.mission_id)
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .join(Drone, Drone.id == Mission.drone_id)
        .where(
            MissionFlight.phase.in_(ELIGIBLE_PHASES),
            MissionFlight.failed_at.is_(None),
            Mission.status == MissionStatus.IN_FLIGHT.value,
            Drone.status == DroneStatus.IN_FLIGHT.value,
        )
        .order_by(MissionFlight.mission_id)
    )
    if exclude_incidents:
        statement = statement.where(
            MissionFlight.recalled_at.is_(None),
            MissionFlight.recipient_unavailable_at.is_(None),
            MissionFlight.handover_failed_at.is_(None),
        )
    return list(session.scalars(statement))


def fleet_availability(session: Session) -> tuple[int, int]:
    """(total drones, unavailable drones) as the automatic failure guard counts them.

    Unavailable: in MAINTENANCE (a failed or grounded drone, or one an operator took out of
    service: the status cannot tell them apart, so all count), or still in the short emergency
    approach of a failure, when the drone is IN_FLIGHT but will be grounded in seconds.
    """
    approaching = (
        select(Mission.drone_id)
        .join(MissionFlight, MissionFlight.mission_id == Mission.id)
        .where(MissionFlight.phase == FlightPhase.EMERGENCY_APPROACH.value)
    )
    total = session.scalar(select(func.count()).select_from(Drone)) or 0
    unavailable = (
        session.scalar(
            select(func.count())
            .select_from(Drone)
            .where(or_(Drone.status == DroneStatus.MAINTENANCE.value, Drone.id.in_(approaching)))
        )
        or 0
    )
    return total, unavailable


def _enforce_fleet_guard(session: Session) -> None:
    """Refuse an automatic failure that would leave fewer than ceil(total / 2) drones operational.

    The target is IN_FLIGHT and not failed, so it is operational now and the projection subtracts
    one. Automatic failures are serialised here on PostgreSQL by a transaction-scoped advisory lock
    taken before the count and held until the failure commits (or rolls back), so two overlapping
    automatic attempts cannot both pass the count (the second one counts the first one's flight,
    already in EMERGENCY_APPROACH). The lock is taken after the flight and drone locks; nothing
    holding it waits for any other lock, so it cannot deadlock. SQLite has one writer. A MANUAL
    failure never takes this lock and is never refused, so a manual failure racing an automatic one
    can leave one drone fewer than the guard alone would allow.
    """
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUTOMATIC_FAILURE_LOCK_KEY}
        )
    total, unavailable = fleet_availability(session)
    needed = math.ceil(total / 2)
    operational_after = total - unavailable - 1
    if operational_after < needed:
        raise FleetGuardError(
            f"Failing another drone would leave {max(operational_after, 0)} of {total} drones "
            f"operational; at least {needed} must remain"
        )


def trigger_drone_failure(
    session: Session,
    now: datetime,
    settings: Settings,
    *,
    origin: EventOrigin = EventOrigin.MANUAL,
    rng: random.Random | None = None,
    automatic_safety: bool = False,
) -> FailureResult:
    """Fail one eligible flying drone; raises `NoEligibleTargetError`, changing nothing, if none.

    `automatic_safety` (Feature 021D-2, used by the random incident scheduler only) adds two rules
    that the manual path does not have: a flight another incident already affects is not a
    candidate, and the fleet guard applies (`FleetGuardError`, changing nothing). Both are checked
    again under the flight, mission, order and drone locks.
    """
    chooser = rng or _rng
    candidates = eligible_mission_ids(session, exclude_incidents=automatic_safety)
    session.rollback()  # end the read transaction; each candidate is rechecked under its locks
    chooser.shuffle(candidates)
    for mission_id in candidates:
        result = _fail_flight(session, mission_id, now, settings, origin, automatic_safety)
        if result is not None:
            return result
    raise NoEligibleTargetError


def _fail_flight(
    session: Session,
    mission_id: str,
    now: datetime,
    settings: Settings,
    origin: EventOrigin,
    automatic_safety: bool = False,
) -> FailureResult | None:
    try:
        flight = session.scalars(
            select(MissionFlight)
            .where(MissionFlight.mission_id == mission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        mission = mission_repository.get_mission_for_update(session, mission_id)
        if flight is None or mission is None:
            session.rollback()
            return None
        relocation = mission.purpose == MissionPurpose.RELOCATION.value
        order = (
            None
            if mission.order_id is None
            else mission_repository.get_order(session, mission.order_id, lock=True)
        )
        drone = mission_repository.get_drone(session, mission.drone_id, lock=True)
        if drone is None or (order is None and not relocation):
            session.rollback()
            return None
        if (
            flight.phase not in ELIGIBLE_PHASES
            or flight.failed_at is not None
            or mission.status != MissionStatus.IN_FLIGHT.value
            or drone.status != DroneStatus.IN_FLIGHT.value
            or (automatic_safety and has_other_incident(flight))
        ):
            session.rollback()
            return None  # it changed since the candidate list was read
        if automatic_safety:
            _enforce_fleet_guard(session)

        started = as_utc(flight.started_at)
        elapsed = max((now - started).total_seconds(), 0.0)
        legs = [leg_from_dict(entry) for entry in flight.legs]
        recalled = flight.recalled_at is not None
        delivered = flight.delivered_at is not None
        handover_failed = flight.handover_failed_at is not None
        returning = recalled or handover_failed
        # The worker has not applied the next milestone yet; leave this flight to it.
        stop = delivery_leg(legs)
        if not delivered and not returning and stop is not None and elapsed >= stop.end_s:
            session.rollback()
            return None
        decision_s, _ = landing_decision(legs[-1], settings.sim_landing_approach_m)
        if (delivered or returning or relocation) and elapsed >= decision_s:
            session.rollback()
            return None

        empty, loaded = consumption_rates(
            weight_kg=0.0 if order is None else order.package_weight_kg,
            model=drone.model,
            payload_energy_factor=settings.mission_payload_energy_factor,
        )
        here = state_at(
            legs,
            elapsed,
            start_battery=flight.start_battery_pct,
            empty_rate=empty,
            loaded_rate=loaded,
        )
        landing = emergency_landing_point(
            legs, elapsed, here.position, settings.sim_emergency_landing_distance_m
        )
        new_legs = emergency_legs(
            legs,
            elapsed,
            here.position,
            landing,
            flight.pace_s_per_km,
            # the parcel is still on board until it is handed over (a relocation has none)
            loaded=not delivered and not relocation,
        )
        stage = (
            FailureStage.RELOCATION
            if relocation
            else FailureStage.RECALL
            if recalled
            else FailureStage.HANDOVER_FAILED
            if handover_failed
            else FailureStage.AFTER_DELIVERY
            if delivered
            else FailureStage.BEFORE_DELIVERY
        )
        flight.legs = [leg_to_dict(leg) for leg in new_legs]
        flight.failed_at = now
        write_snapshot(
            flight,
            drone,
            state_at(
                new_legs,
                elapsed,
                start_battery=flight.start_battery_pct,
                empty_rate=empty,
                loaded_rate=loaded,
            ),
            now,
        )
        append_event(
            session,
            event_type=EventType.DRONE_FAILURE,
            origin=origin,
            order_id=None if order is None else order.id,
            mission_id=mission.id,
            flight_id=flight.mission_id,
            drone_id=drone.id,
            reason=f"Simulated drone failure ({stage.value.lower().replace('_', ' ')}); "
            "emergency landing",
            details={"stage": stage.value, "landing_position": [landing[0], landing[1]]},
            dedupe_key=f"{EventType.DRONE_FAILURE.value}:{mission.id}",
            occurred_at=now,
        )
        session.commit()
        return FailureResult(
            drone_id=drone.id,
            mission_id=mission.id,
            order_id=None if order is None else order.id,
            stage=stage,
            landing_position=landing,
        )
    except BaseException:
        session.rollback()
        raise
