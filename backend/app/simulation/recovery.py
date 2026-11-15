"""Automatic recovery of drones grounded by a drone failure (Feature 022).

A drone failure (018C) ends with the drone grounded in `MAINTENANCE` where it landed. Nothing ever
returned such a drone to service, so a long run slowly emptied the fleet. This module is the
simulated ground crew: `recovery_delay` real seconds after the emergency landing it moves the drone
straight to a Hub (no flight, no teleporting during a mission) and lets the existing charging rules
take over.

Nothing new is stored per drone. Eligibility is derived from durable records, so a worker restart
loses nothing and no in-memory timer exists:

* the drone is in `MAINTENANCE` exactly where its failed flight stopped (it has not moved since),
* that flight ended as `EMERGENCY` with reason `DRONE_FAILURE`, and its mission is `EMERGENCY`,
* the mission has a `DRONE_FAILURE` event, whatever its origin: an AUTOMATIC and a MANUAL failure
  are recovered alike. A drone an operator put into `MAINTENANCE`, or one that stopped for another
  emergency reason, has no such failed flight and is never touched,
* the real time since `mission_flights.emergency_at` (set when the landing was committed) is at
  least the delay,
* no `DRONE_RECOVERED` event exists for the mission. That event, with the unique key
  `DRONE_RECOVERED:<mission id>`, is the "done" marker, so a failure is recovered at most once.

"Pending" is simply eligible, due and still `MAINTENANCE`: with every Hub full nothing changes and
the next look tries again. Recovery changes the drone only: the mission stays `EMERGENCY`, the
flight stays an emergency, the order keeps its status and the failure history is untouched.

Locks follow the established order: flight, mission, drone, then the Hubs (all of them, by id, so
two recoveries cannot lock them in opposite orders). Eligibility and capacity are rechecked under
those locks, using the same occupancy rule as landings (`missions.presence`).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import Exists, exists, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.drones.repository import get_drone_for_update
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.events.service import append_event
from app.hubs.models import Hub
from app.missions.capacity import has_free_place
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import hub_point, hubs_by_distance
from app.simulation.clock import as_utc
from app.simulation.models import EmergencyReason, FlightPhase, MissionFlight

logger = logging.getLogger("skyfleet.recovery")

FULL_BATTERY_PCT = 100
# The drone's stored position is a copy of the flight's final position, so they match exactly; the
# tolerance only absorbs float formatting.
POSITION_TOLERANCE_DEG = 1e-9
# Upper bound of candidates looked at per step (the fleet is small; this keeps a step bounded even
# if many drones are waiting).
MAX_CANDIDATES = 50


class NotEligibleError(Exception):
    """The drone cannot be recovered now (it changed, was recovered, or was never eligible)."""


class NoHubWithRoomError(Exception):
    """Every Hub is full: the recovery stays pending and is tried again later."""


@dataclass(frozen=True)
class RecoveryResult:
    drone_id: str
    mission_id: str
    hub_id: str
    status: DroneStatus


def recovery_event_key(mission_id: str) -> str:
    """The unique event key that makes a mission's recovery happen at most once."""
    return f"{EventType.DRONE_RECOVERED.value}:{mission_id}"


def _event_exists(mission_id_column: InstrumentedAttribute[str], event_type: EventType) -> Exists:
    return exists().where(
        OperationalEvent.event_type == event_type.value,
        OperationalEvent.mission_id == mission_id_column,
    )


def due_mission_ids(session: Session, now: datetime, settings: Settings) -> list[str]:
    """Missions whose grounded drone is eligible and due, oldest landing first (not yet locked)."""
    cutoff = now - timedelta(seconds=settings.drone_recovery_delay_seconds)
    statement = (
        select(MissionFlight.mission_id)
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .join(Drone, Drone.id == Mission.drone_id)
        .where(
            Drone.status == DroneStatus.MAINTENANCE.value,
            Mission.status == MissionStatus.EMERGENCY.value,
            MissionFlight.phase == FlightPhase.EMERGENCY.value,
            MissionFlight.emergency_reason == EmergencyReason.DRONE_FAILURE.value,
            MissionFlight.failed_at.is_not(None),
            MissionFlight.emergency_at.is_not(None),
            MissionFlight.emergency_at <= cutoff,
            func.abs(Drone.longitude - MissionFlight.longitude) <= POSITION_TOLERANCE_DEG,
            func.abs(Drone.latitude - MissionFlight.latitude) <= POSITION_TOLERANCE_DEG,
            _event_exists(MissionFlight.mission_id, EventType.DRONE_FAILURE),  # any origin
            ~_event_exists(MissionFlight.mission_id, EventType.DRONE_RECOVERED),
        )
        .order_by(MissionFlight.emergency_at, MissionFlight.mission_id)
        .limit(MAX_CANDIDATES)
    )
    return list(session.scalars(statement))


def _has_event(session: Session, mission_id: str, event_type: EventType) -> bool:
    statement = select(OperationalEvent.id).where(
        OperationalEvent.event_type == event_type.value, OperationalEvent.mission_id == mission_id
    )
    return session.scalars(statement.limit(1)).first() is not None


def _ineligible_reason(
    session: Session,
    flight: MissionFlight,
    mission: Mission,
    drone: Drone,
    now: datetime,
    settings: Settings,
    *,
    wait_for_delay: bool,
) -> str | None:
    """Why the drone may not be recovered now, rechecked on the locked rows; None when it may."""
    if drone.status != DroneStatus.MAINTENANCE.value:
        return f"drone {drone.id} is {drone.status}, not MAINTENANCE"
    if (
        flight.phase != FlightPhase.EMERGENCY.value
        or flight.emergency_reason != EmergencyReason.DRONE_FAILURE.value
        or flight.failed_at is None
        or flight.emergency_at is None
        or mission.status != MissionStatus.EMERGENCY.value
    ):
        return f"mission {mission.id} did not end as a drone-failure emergency"
    if (
        abs(drone.longitude - flight.longitude) > POSITION_TOLERANCE_DEG
        or abs(drone.latitude - flight.latitude) > POSITION_TOLERANCE_DEG
    ):
        return f"drone {drone.id} is no longer where mission {mission.id} grounded it"
    if not _has_event(session, mission.id, EventType.DRONE_FAILURE):
        return f"mission {mission.id} has no drone-failure event"
    if _has_event(session, mission.id, EventType.DRONE_RECOVERED):
        return f"mission {mission.id} was already recovered"
    if wait_for_delay:
        due = as_utc(flight.emergency_at) + timedelta(seconds=settings.drone_recovery_delay_seconds)
        if now < due:
            return f"recovery of mission {mission.id} is due at {due.isoformat()}"
    return None


def recover_grounded_drone(
    session: Session,
    mission_id: str,
    now: datetime,
    settings: Settings,
    *,
    wait_for_delay: bool = True,
    origin: EventOrigin = EventOrigin.AUTOMATIC,
) -> RecoveryResult:
    """Move the drone grounded by `mission_id`'s failure to the nearest Hub with a free place.

    One transaction. Raises `NotEligibleError` (nothing changed) when the drone may not be
    recovered, `NoHubWithRoomError` (nothing changed) when every Hub is full. Any `DRONE_FAILURE`
    qualifies, whatever the origin of the failure. The defaults are what the worker uses (wait for
    the delay, record the recovery as AUTOMATIC); an operator-initiated "Recover Drone" action can
    pass `wait_for_delay=False` and `origin=EventOrigin.MANUAL` and reuse everything else.
    """
    try:
        drone_id = session.scalar(select(Mission.drone_id).where(Mission.id == mission_id))
        if drone_id is None:
            raise NotEligibleError(f"mission {mission_id} does not exist")
        # Lock order: flight, mission, drone, then the Hubs.
        flight = session.scalars(
            select(MissionFlight)
            .where(MissionFlight.mission_id == mission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        mission = session.scalars(
            select(Mission)
            .where(Mission.id == mission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        drone = get_drone_for_update(session, drone_id)
        if flight is None or mission is None or drone is None:
            raise NotEligibleError(f"mission {mission_id} has no flight or drone")
        reason = _ineligible_reason(
            session,
            flight,
            mission,
            drone,
            now,
            settings,
            wait_for_delay=wait_for_delay,
        )
        if reason is not None:
            raise NotEligibleError(reason)

        hubs = list(
            session.scalars(
                select(Hub)
                .order_by(Hub.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        fresh_drones = session.scalars(
            select(Drone).order_by(Drone.id).execution_options(populate_existing=True)
        ).all()
        occupancy = hub_occupancy(fresh_drones, hubs, settings.hub_dock_proximity_m)
        origin_point = (drone.longitude, drone.latitude)
        chosen = next(
            (
                hub
                for hub, _km in hubs_by_distance(origin_point, hubs)
                if has_free_place(hub, occupancy, drone_docked_here=False)
            ),
            None,
        )
        if chosen is None:
            raise NoHubWithRoomError(f"every Hub is full; drone {drone.id} stays grounded")

        # The drone moves; the mission, the flight and the order stay exactly as they were. The
        # battery is kept: the existing charging rules decide how it recovers from here.
        drone.hub_id = chosen.id
        drone.longitude, drone.latitude = hub_point(chosen)
        drone.status = (
            DroneStatus.CHARGING.value
            if drone.battery_pct < FULL_BATTERY_PCT
            else DroneStatus.IDLE.value
        )
        recorded = append_event(
            session,
            event_type=EventType.DRONE_RECOVERED,
            origin=origin,
            order_id=mission.order_id,
            mission_id=mission.id,
            flight_id=flight.mission_id,
            drone_id=drone.id,
            reason=f"Drone recovered by ground crew and moved to {chosen.name}",
            details={
                "hub_id": chosen.id,
                "from_position": [origin_point[0], origin_point[1]],
                "status": drone.status,
                "battery_pct": drone.battery_pct,
            },
            dedupe_key=recovery_event_key(mission.id),
            occurred_at=now,
        )
        if not recorded:  # the key exists although the checks passed: undo, never double-recover
            raise NotEligibleError(f"mission {mission_id} was already recovered")
        result = RecoveryResult(
            drone_id=drone.id,
            mission_id=mission.id,
            hub_id=chosen.id,
            status=DroneStatus(drone.status),
        )
        session.commit()
        return result
    except BaseException:
        session.rollback()
        raise


@dataclass
class RecoveryState:
    """The worker's memory between looks; it only keeps the log quiet, never any decision."""

    full_logged: bool = False
    failing: set[str] = field(default_factory=set)


def run_recovery_step(
    factory: sessionmaker[Session], settings: Settings, now: datetime, state: RecoveryState
) -> int:
    """Recover up to `drone_recovery_batch_size` due drones; returns how many were recovered.

    Never raises for one drone's problem: it is logged and the next candidate is tried, so one bad
    record cannot block the others. When every Hub is full the step stops (the next candidates
    would find the same) and the drones simply stay pending for the next look.
    """
    with factory() as session:
        candidates = due_mission_ids(session, now, settings)
    recovered = 0
    for mission_id in candidates:
        if recovered >= settings.drone_recovery_batch_size:
            break
        with factory() as session:
            try:
                result = recover_grounded_drone(session, mission_id, now, settings)
            except NotEligibleError:
                continue  # it changed since the candidate list was read
            except NoHubWithRoomError:
                if not state.full_logged:
                    logger.warning("Drone recovery is waiting: every Hub is full")
                    state.full_logged = True
                break
            except Exception:
                if mission_id not in state.failing:
                    state.failing.add(mission_id)
                    logger.exception("Drone recovery failed for mission %s", mission_id)
                continue
        state.full_logged = False
        state.failing.discard(mission_id)
        recovered += 1
        logger.info(
            "Drone %s recovered to %s (mission %s)",
            result.drone_id,
            result.hub_id,
            result.mission_id,
        )
    return recovered
