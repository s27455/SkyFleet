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

import random
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.missions import repository as mission_repository
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionStatus
from app.simulation.clock import as_utc
from app.simulation.engine import write_snapshot
from app.simulation.flight import (
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
)

_rng = random.Random()


class FailureStage(StrEnum):
    BEFORE_DELIVERY = "BEFORE_DELIVERY"  # the parcel is still on board, nothing was handed over
    RECALL = "RECALL"  # the order was cancelled and the drone is flying back (018B)
    AFTER_DELIVERY = "AFTER_DELIVERY"  # the parcel was delivered; the drone is on its way back


class NoEligibleTargetError(Exception):
    def __init__(self) -> None:
        super().__init__("No drone is flying a mission that a failure could interrupt")


@dataclass(frozen=True)
class FailureResult:
    drone_id: str
    mission_id: str
    order_id: str
    stage: FailureStage
    landing_position: tuple[float, float]


def eligible_mission_ids(session: Session) -> list[str]:
    """Mission ids of the flights that look eligible, in id order (rechecked under locks)."""
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
    return list(session.scalars(statement))


def trigger_drone_failure(
    session: Session,
    now: datetime,
    settings: Settings,
    *,
    origin: EventOrigin = EventOrigin.MANUAL,
    rng: random.Random | None = None,
) -> FailureResult:
    """Fail one eligible flying drone; raises `NoEligibleTargetError`, changing nothing, if none."""
    chooser = rng or _rng
    candidates = eligible_mission_ids(session)
    session.rollback()  # end the read transaction; each candidate is rechecked under its locks
    chooser.shuffle(candidates)
    for mission_id in candidates:
        result = _fail_flight(session, mission_id, now, settings, origin)
        if result is not None:
            return result
    raise NoEligibleTargetError


def _fail_flight(
    session: Session, mission_id: str, now: datetime, settings: Settings, origin: EventOrigin
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
        order = mission_repository.get_order(session, mission.order_id, lock=True)
        drone = mission_repository.get_drone(session, mission.drone_id, lock=True)
        if order is None or drone is None:
            session.rollback()
            return None
        if (
            flight.phase not in ELIGIBLE_PHASES
            or flight.failed_at is not None
            or mission.status != MissionStatus.IN_FLIGHT.value
            or drone.status != DroneStatus.IN_FLIGHT.value
        ):
            session.rollback()
            return None  # it changed since the candidate list was read

        started = as_utc(flight.started_at)
        elapsed = max((now - started).total_seconds(), 0.0)
        legs = [leg_from_dict(entry) for entry in flight.legs]
        recalled = flight.recalled_at is not None
        delivered = flight.delivered_at is not None
        # The worker has not applied the next milestone yet; leave this flight to it.
        if not delivered and not recalled and elapsed >= legs[1].end_s:
            session.rollback()
            return None
        decision_s, _ = landing_decision(legs[-1], settings.sim_landing_approach_m)
        if (delivered or recalled) and elapsed >= decision_s:
            session.rollback()
            return None

        empty, loaded = consumption_rates(
            weight_kg=order.package_weight_kg,
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
            loaded=not delivered,  # the parcel is still on board until it is handed over
        )
        stage = (
            FailureStage.RECALL
            if recalled
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
            order_id=order.id,
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
            order_id=order.id,
            stage=stage,
            landing_position=landing,
        )
    except BaseException:
        session.rollback()
        raise
