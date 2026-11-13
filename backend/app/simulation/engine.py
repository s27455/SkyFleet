"""The flight simulation engine: one tick advances every active flight.

State is derived from each flight's stored schedule and the clock (see `flight.py`), so the engine
is restart-safe and idempotent: running a tick twice, or after a long downtime, applies every
milestone exactly once and in order. Each step runs in its own transaction under row locks.

Milestones:

* delivery stop finished -> the order becomes DELIVERED (the mission stays IN_FLIGHT); a recalled
  flight (Feature 018B, order cancelled in flight) never reaches this milestone: it flies back
  loaded to a Hub, and the landing decision below applies to it, with the loaded consumption rate;
* landing decision, `sim_landing_approach_m` before the target Hub -> under that Hub's row lock the
  engine counts the drones physically docked there. With a free place the drone docks atomically
  (mission COMPLETED, drone IDLE at the Hub). If the Hub is full it diverts to the nearest other
  Hub that the battery can reach with at least the critical floor and that has a place; if there is
  none the flight ends in a simulated EMERGENCY (mission EMERGENCY, drone MAINTENANCE at the stop
  point, order still DELIVERED). There is no reservation and no indefinite holding.

Only one Hub is locked per transaction, so concurrent landings cannot deadlock, and the
check-and-dock being atomic under that lock means a Hub never exceeds its capacity.

INVARIANT for later features: capacity is only guaranteed because every path that makes a drone
count as docked at a Hub takes that Hub's row lock first. Landing does. Charging, maintenance
release or repositioning (later features) must take the same lock before they dock a drone.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.hubs.models import Hub
from app.missions import repository
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import Point, distance_km, hub_point, nearest_reachable_hub
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation.clock import as_utc
from app.simulation.flight import (
    FlightState,
    Leg,
    diversion_leg,
    first_time_below,
    handover_failed_legs,
    landing_decision,
    leg_from_dict,
    leg_to_dict,
    state_at,
    stop_legs,
    truncate_leg,
)
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import (
    TERMINAL_PHASES,
    EmergencyReason,
    FlightPhase,
    MissionFlight,
)

logger = logging.getLogger("skyfleet.simulation")

# Per flight and tick: the delivery milestone plus at most one landing attempt per Hub.
MAX_STEPS_PER_FLIGHT = 12


class StateFor(Protocol):
    """The flight state at an offset in seconds, optionally for a replacement list of legs."""

    def __call__(self, at_s: float, leg_list: list[Leg] | None = None) -> FlightState: ...


class FlightInvariantError(RuntimeError):
    """A flight reached a state the simulation guarantees cannot happen."""


def rounded_pct(value: float) -> int:
    """Battery percent as stored on the drone: rounded half up, within 0..100."""
    return max(0, min(100, math.floor(value + 0.5)))


def run_step(factory: sessionmaker[Session], settings: Settings, now: datetime) -> int:
    """One simulation step: record the heartbeat, then advance every active flight."""
    with factory() as session:
        record_heartbeat(session, now)
        terminal = [phase.value for phase in TERMINAL_PHASES]
        statement = select(MissionFlight.mission_id).where(MissionFlight.phase.not_in(terminal))
        mission_ids = list(session.scalars(statement.order_by(MissionFlight.started_at)))
    for mission_id in mission_ids:
        try:
            advance_flight(factory, settings, mission_id, now)
        except Exception:
            # One failing flight must not stall the others; it is retried on the next tick.
            logger.exception("Could not advance flight %s; the other flights continue", mission_id)
    return len(mission_ids)


def advance_flight(
    factory: sessionmaker[Session], settings: Settings, mission_id: str, now: datetime
) -> None:
    """Apply every milestone of one flight that is due at `now`, in order."""
    for _ in range(MAX_STEPS_PER_FLIGHT):
        with factory() as session:
            if not advance_once(session, settings, mission_id, now):
                return


def advance_once(session: Session, settings: Settings, mission_id: str, now: datetime) -> bool:
    """One step for one flight. Returns True if a milestone was applied and more may be due."""
    try:
        terminal = [phase.value for phase in TERMINAL_PHASES]
        flight = session.scalars(
            select(MissionFlight)
            .where(MissionFlight.mission_id == mission_id, MissionFlight.phase.not_in(terminal))
            .with_for_update(skip_locked=True)  # another worker may hold this flight
            .execution_options(populate_existing=True)
        ).one_or_none()
        if flight is None:
            session.rollback()
            return False
        mission = repository.get_mission_for_update(session, mission_id)
        if mission is None:
            raise FlightInvariantError(f"Flight {mission_id} has no mission")
        order = repository.get_order(session, mission.order_id, lock=True)
        drone = repository.get_drone(session, mission.drone_id, lock=True)
        if order is None or drone is None:
            raise FlightInvariantError(f"Flight {mission_id} has no order or drone")
        hubs = {hub.id: hub for hub in repository.list_hubs(session)}

        started = as_utc(flight.started_at)
        elapsed = max((now - started).total_seconds(), 0.0)
        legs = [leg_from_dict(entry) for entry in flight.legs]
        empty, loaded = consumption_rates(
            weight_kg=order.package_weight_kg,
            model=drone.model,
            payload_energy_factor=settings.mission_payload_energy_factor,
        )

        def state_for(at_s: float, leg_list: list[Leg] | None = None) -> FlightState:
            return state_at(
                leg_list or legs,
                at_s,
                start_battery=flight.start_battery_pct,
                empty_rate=empty,
                loaded_rate=loaded,
            )

        # A failed flight (Feature 018C) only flies its emergency approach and is then grounded.
        if flight.failed_at is not None:
            return _advance_failed(
                session, flight, mission, drone, legs, started, elapsed, now, state_for
            )

        # A recalled flight (018B) or one whose handover failed (018D) is carrying its parcel
        # back: no delivery, and the loaded rate applies.
        recalled = flight.recalled_at is not None
        handover_failed = flight.handover_failed_at is not None
        loaded_return = recalled or handover_failed
        return_rate = loaded if loaded_return else empty

        # Milestone 1: the parcel is handed over at the destination (or, when the recipient was
        # reported unavailable, the handover fails and the drone turns back with the parcel).
        delivery_end = legs[1].end_s if not recalled else 0.0
        if not loaded_return and flight.delivered_at is None and elapsed >= delivery_end:
            if flight.recipient_unavailable_at is not None:
                _fail_handover(
                    session,
                    settings,
                    flight,
                    mission,
                    order,
                    drone,
                    hubs,
                    legs,
                    loaded,
                    started,
                    delivery_end,
                    now,
                    state_for,
                )
                return True
            order.status = OrderStatus.DELIVERED.value
            flight.delivered_at = started + timedelta(seconds=delivery_end)
            # The order's delivery time is the moment this transition is committed, in real UTC
            # (`now`), not the flight's scheduled instant: that stays the timeline event it was. A
            # worker that was stopped or late would otherwise stamp a time that is already past
            # the visibility window (Feature 017A) and the order would vanish at once.
            order.delivered_at = now
            write_snapshot(flight, drone, state_for(elapsed), now)
            session.commit()
            return True

        # Milestone 2: the landing decision (capacity recheck, docking, diversion or emergency).
        decision_s, decision_point = landing_decision(legs[-1], settings.sim_landing_approach_m)
        if flight.delivered_at is not None or loaded_return:
            # The battery falling below the critical floor before the landing decision is an
            # emergency at the exact crossing time, however late this tick runs (deterministic).
            crossing = first_time_below(
                legs,
                settings.sim_critical_battery_pct,
                start_battery=flight.start_battery_pct,
                empty_rate=empty,
                loaded_rate=loaded,
                after_s=(
                    max((as_utc(flight.recalled_at) - started).total_seconds(), 0.0)
                    if flight.recalled_at is not None
                    else delivery_end
                ),
            )
            if crossing is not None and crossing < decision_s and crossing <= elapsed:
                crossed = state_for(crossing)
                _end_in_emergency(
                    flight,
                    mission,
                    drone,
                    legs,
                    at_s=crossing,
                    point=crossed.position,
                    battery=crossed.battery_pct,
                    reason=EmergencyReason.BATTERY_CRITICAL,
                    started=started,
                    now=now,
                )
                session.commit()
                return False
        if (flight.delivered_at is not None or loaded_return) and elapsed >= decision_s:
            return _decide_landing(
                session,
                settings,
                flight,
                mission,
                drone,
                hubs,
                legs,
                (decision_s, decision_point),
                started,
                now,
                return_rate,
                state_for,
            )

        state = state_for(elapsed)
        if flight.delivered_at is None and not handover_failed and state.battery_pct < 0:
            raise FlightInvariantError(f"Flight {mission_id} ran out of battery before delivery")

        write_snapshot(flight, drone, state, now)
        session.commit()
        return False
    except BaseException:
        session.rollback()
        raise


def _fail_handover(
    session: Session,
    settings: Settings,
    flight: MissionFlight,
    mission: Mission,
    order: DeliveryOrder,
    drone: Drone,
    hubs: dict[str, Hub],
    legs: list[Leg],
    loaded_rate: float,
    started: datetime,
    delivery_end: float,
    now: datetime,
    state_for: StateFor,
) -> None:
    """Feature 018D: the recipient is unavailable, so the parcel is not handed over.

    The order becomes DELIVERY_FAILED (real UTC `now`, which starts its visibility window; never
    `delivered_at`) and the empty return is replaced by a loaded return to the nearest Hub the
    battery reaches with the parcel. The drone turns back where it stands: position and battery
    continue from the schedule. The existing landing logic then docks (or diverts) it; nothing
    here touches `drone.hub_id`. If no Hub were reachable (planned missions keep a reserve, so not
    expected) the planned return Hub is kept and the existing safeguards decide. One event, in the
    same transaction; the flight leaves the pending state at the same commit, so it runs once.
    """
    at_stop = state_for(delivery_end)
    target = (
        nearest_reachable_hub(
            legs[1].target,
            list(hubs.values()),
            at_stop.battery_pct,
            loaded_rate,
            settings.sim_critical_battery_pct,
        )
        or hubs[flight.planned_return_hub_id]
    )
    new_legs = handover_failed_legs(legs, hub_point(target), flight.pace_s_per_km)
    flight.legs = [leg_to_dict(leg) for leg in new_legs]
    flight.handover_failed_at = started + timedelta(seconds=delivery_end)
    flight.landing_target_hub_id = target.id
    flight.tried_hub_ids = []
    order.status = OrderStatus.DELIVERY_FAILED.value
    order.delivery_failed_at = now
    order.updated_at = now
    elapsed = max((now - started).total_seconds(), 0.0)
    write_snapshot(flight, drone, state_for(elapsed, new_legs), now)
    append_event(
        session,
        event_type=EventType.RECIPIENT_UNAVAILABLE,
        # The trigger's origin, kept on the flight; SYSTEM only if a marker predates it.
        origin=EventOrigin(flight.recipient_unavailable_origin or EventOrigin.SYSTEM.value),
        order_id=order.id,
        mission_id=mission.id,
        flight_id=flight.mission_id,
        drone_id=drone.id,
        reason=f"Recipient unavailable; drone {drone.id} returns to {target.name} with the parcel",
        details={"return_hub_id": target.id},
        dedupe_key=f"{EventType.RECIPIENT_UNAVAILABLE.value}:{mission.id}",
        occurred_at=now,
    )
    session.commit()


def _advance_failed(
    session: Session,
    flight: MissionFlight,
    mission: Mission,
    drone: Drone,
    legs: list[Leg],
    started: datetime,
    elapsed: float,
    now: datetime,
    state_for: StateFor,
) -> bool:
    """Feature 018C: fly the emergency approach, then ground the drone where it lands.

    No delivery milestone and no landing decision apply: the original mission never resumes. At
    the end of the approach the flight becomes EMERGENCY (reason DRONE_FAILURE), the mission
    EMERGENCY and the drone MAINTENANCE at the landing point (never counted as docked). The order
    is left as it is: an undelivered order is not DELIVERED, a delivered or cancelled one stays so.
    Idempotent: a finished flight is terminal and the engine no longer selects it.
    """
    end_s = legs[-1].end_s
    if elapsed < end_s:
        write_snapshot(flight, drone, state_for(elapsed), now)
        session.commit()
        return False
    landing = state_for(end_s)
    point = legs[-1].target
    flight.phase = FlightPhase.EMERGENCY.value
    flight.emergency_reason = EmergencyReason.DRONE_FAILURE.value
    # The real UTC time the grounding is committed, not the scheduled instant: the 120 s window in
    # which an interrupted delivery stays in the active views starts when it really ends.
    flight.emergency_at = now
    flight.ended_at = now
    flight.battery_pct = landing.battery_pct
    flight.longitude, flight.latitude = point
    flight.progress = 1.0
    flight.target_longitude = flight.target_latitude = flight.target_eta_s = None
    flight.updated_at = now
    drone.status = DroneStatus.MAINTENANCE.value
    drone.longitude, drone.latitude = point
    drone.battery_pct = rounded_pct(landing.battery_pct)
    mission.status = MissionStatus.EMERGENCY.value
    session.commit()
    return False


def write_snapshot(flight: MissionFlight, drone: Drone, state: FlightState, now: datetime) -> None:
    flight.phase = state.phase.value
    flight.longitude, flight.latitude = state.position
    flight.battery_pct = state.battery_pct
    flight.progress = state.progress
    flight.target_longitude, flight.target_latitude = state.target
    flight.target_eta_s = state.eta_s
    flight.updated_at = now
    # The drone row mirrors the flight so the fleet endpoint shows the flying drone's position.
    drone.longitude, drone.latitude = state.position
    drone.battery_pct = rounded_pct(state.battery_pct)


def _decide_landing(
    session: Session,
    settings: Settings,
    flight: MissionFlight,
    mission: Mission,
    drone: Drone,
    hubs: dict[str, Hub],
    legs: list[Leg],
    decision: tuple[float, Point],
    started: datetime,
    now: datetime,
    rate_pct_per_km: float,
    state_for: StateFor,
) -> bool:
    decision_s, decision_point = decision
    final = legs[-1]
    target = hubs[flight.landing_target_hub_id]

    # Lock this one Hub, then count the drones docked there as of the lock. A concurrent landing
    # at the same Hub waits here, so the check and the docking below are atomic.
    session.scalars(
        select(Hub)
        .where(Hub.id == target.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    fresh_drones = session.scalars(
        select(Drone).order_by(Drone.id).execution_options(populate_existing=True)
    ).all()
    occupancy = hub_occupancy(fresh_drones, list(hubs.values()), settings.hub_dock_proximity_m)

    if occupancy[target.id] < target.drone_capacity:
        landed = state_for(final.end_s)
        drone.status = DroneStatus.IDLE.value
        # Feature 017C: `hub_id` is the Hub where the drone last docked successfully. It changes
        # only here (a landing, a diversion that lands included), never in flight and never in an
        # emergency; the mission and flight keep the Hub the drone departed from.
        drone.hub_id = target.id
        drone.longitude, drone.latitude = hub_point(target)
        drone.battery_pct = rounded_pct(landed.battery_pct)
        mission.status = MissionStatus.COMPLETED.value
        flight.phase = FlightPhase.LANDED.value
        flight.ended_at = started + timedelta(seconds=final.end_s)
        flight.landed_hub_id = target.id
        flight.battery_pct = landed.battery_pct
        flight.longitude, flight.latitude = hub_point(target)
        flight.progress = 1.0
        flight.target_longitude = flight.target_latitude = flight.target_eta_s = None
        flight.updated_at = now
        session.commit()
        return False

    # The Hub is full. Look for the nearest other Hub the battery can reach, with a place now.
    battery_here = state_for(decision_s).battery_pct
    tried = [*flight.tried_hub_ids, target.id]
    candidates = sorted(
        (
            (hub, distance_km(decision_point, hub_point(hub)))
            for hub in hubs.values()
            if hub.id not in tried
        ),
        key=lambda item: (item[1], item[0].id),
    )
    reachable = [
        (hub, km)
        for hub, km in candidates
        if battery_here - rate_pct_per_km * km >= settings.sim_critical_battery_pct
    ]
    with_room = [(hub, km) for hub, km in reachable if occupancy[hub.id] < hub.drone_capacity]

    if with_room:
        chosen = with_room[0][0]
        new_legs = [
            *legs[:-1],
            truncate_leg(final, decision_s, decision_point),
            diversion_leg(
                decision_point,
                hub_point(chosen),
                decision_s,
                flight.pace_s_per_km,
                # a recalled drone, or one whose handover failed, still carries the parcel
                loaded=flight.recalled_at is not None or flight.handover_failed_at is not None,
            ),
        ]
        flight.legs = [leg_to_dict(leg) for leg in new_legs]
        flight.tried_hub_ids = tried
        flight.landing_target_hub_id = chosen.id
        elapsed = max((now - started).total_seconds(), 0.0)
        write_snapshot(flight, drone, state_for(elapsed, new_legs), now)
        session.commit()
        return True  # the diversion leg may already be due (catch-up); try the next Hub

    reason = (
        EmergencyReason.BATTERY_INSUFFICIENT
        if candidates and not reachable
        else EmergencyReason.NO_HUB_WITH_CAPACITY
    )
    _end_in_emergency(
        flight,
        mission,
        drone,
        legs,
        at_s=decision_s,
        point=decision_point,
        battery=battery_here,
        reason=reason,
        started=started,
        now=now,
    )
    flight.tried_hub_ids = tried
    session.commit()
    return False


def _end_in_emergency(
    flight: MissionFlight,
    mission: Mission,
    drone: Drone,
    legs: list[Leg],
    *,
    at_s: float,
    point: Point,
    battery: float,
    reason: EmergencyReason,
    started: datetime,
    now: datetime,
) -> None:
    """A simulated emergency: not a computed safe landing site and never a successful completion.

    The mission ends as EMERGENCY and the drone stops where it is as MAINTENANCE, which the
    occupancy rule never counts as docked. The order stays DELIVERED (the parcel was handed over
    before the return), which is why an emergency before delivery cannot be represented.
    """
    if (
        flight.delivered_at is None
        and flight.recalled_at is None
        and flight.handover_failed_at is None
    ):
        raise FlightInvariantError("An emergency before the delivery is not supported")
    stopped = stop_legs(legs, at_s, point)
    flight.legs = [leg_to_dict(leg) for leg in stopped]
    flight.phase = FlightPhase.EMERGENCY.value
    flight.emergency_reason = reason.value
    flight.emergency_at = started + timedelta(seconds=at_s)
    flight.ended_at = flight.emergency_at
    flight.battery_pct = battery
    flight.longitude, flight.latitude = point
    flight.progress = 1.0
    flight.target_longitude = flight.target_latitude = flight.target_eta_s = None
    flight.updated_at = now
    drone.status = DroneStatus.MAINTENANCE.value
    drone.longitude, drone.latitude = point
    drone.battery_pct = rounded_pct(battery)
    mission.status = MissionStatus.EMERGENCY.value
