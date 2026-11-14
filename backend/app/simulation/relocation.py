"""Manual drone relocation (Feature 019A): an empty, timed hub-to-hub flight with no order.

`start_relocation` is a plain service function with no HTTP dependency, so the operator's
Relocate action and the future automatic fleet rebalancing (019B) call exactly the same logic.

A relocation is a mission with purpose `RELOCATION` and no order. It is created already `IN_FLIGHT`
together with its flight, in one transaction, under the drone's row lock and the destination Hub's
row lock (drone first, then Hub: the engine and drone management take them in the same order). The
partial unique index on active missions per drone is the final guarantee against two active
missions for one drone. The worker's flight engine then flies it like any other flight; the landing
decision rechecks the destination's capacity, so a destination that filled up meanwhile is handled
by the existing diversion logic and `drone.hub_id` changes only on landing.

Feasibility (`evaluate_relocation`) is a pure function shared by the read-only preview and the
start, reusing the existing energy model (empty rate), distance budget, battery reserve and
physical Hub occupancy.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.hubs.models import Hub
from app.missions import repository
from app.missions.energy import estimate_energy, has_enough_battery
from app.missions.models import Mission, MissionPurpose, MissionStatus, new_mission_id
from app.missions.presence import docked_hub, hub_occupancy
from app.missions.routing import distance_km, hub_point
from app.missions.service import DroneNotFoundError, MissionError
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import heartbeat
from app.simulation.flight import build_relocation_legs, flight_duration_s, leg_to_dict
from app.simulation.models import FlightPhase, MissionFlight
from app.simulation.schemas import (
    RelocationPlanResponse,
    RelocationReason,
    RelocationReasonCode,
)
from app.simulation.service import WorkerUnavailableError
from app.weather import service as weather

MAX_ID_ATTEMPTS = 5


class HubNotFoundError(MissionError):
    def __init__(self, hub_id: str) -> None:
        super().__init__(f"Hub '{hub_id}' not found")


class RelocationRejectedError(MissionError):
    """The drone cannot be relocated; `plan` lists every reason and nothing was written."""

    def __init__(self, plan: RelocationPlanResponse) -> None:
        super().__init__("; ".join(reason.message for reason in plan.reasons))
        self.plan = plan


class _IdCollisionError(Exception):
    """A generated mission id already exists (astronomically rare); retry with a new id."""


def evaluate_relocation(
    *,
    drone: Drone,
    destination: Hub,
    hubs: Sequence[Hub],
    drones: Sequence[Drone],
    drone_has_active_mission: bool,
    waiting_orders_at_origin: int,
    dock_proximity_m: float,
) -> RelocationPlanResponse:
    """Whether `drone` can fly to `destination` now, with every reason it cannot. Pure."""
    origin = docked_hub(drone, hubs, dock_proximity_m)
    origin_point = hub_point(origin) if origin is not None else (drone.longitude, drone.latitude)
    km = distance_km(origin_point, hub_point(destination))
    model = drone.model
    budget_km = float(model.recommended_mission_range_km)
    energy = estimate_energy(
        outbound_km=km,
        return_km=0.0,
        weight_kg=0.0,
        model=model,
        payload_energy_factor=0.0,
    )
    occupancy = hub_occupancy(drones, hubs, dock_proximity_m)

    reasons: list[RelocationReason] = []

    def reject(code: RelocationReasonCode, message: str) -> None:
        reasons.append(RelocationReason(code=code, message=message))

    if drone_has_active_mission:
        reject(
            RelocationReasonCode.DRONE_ALREADY_ASSIGNED, "The drone already has an active mission."
        )
    if drone.status != DroneStatus.IDLE:
        reject(
            RelocationReasonCode.DRONE_NOT_AVAILABLE,
            f"Drone is {drone.status}; it must be IDLE to be relocated.",
        )
    if origin is None:
        reject(
            RelocationReasonCode.DRONE_NOT_AT_HUB,
            f"Drone is not docked at a Hub (within {dock_proximity_m:g} m, not in flight).",
        )
    elif origin.id == destination.id:
        reject(
            RelocationReasonCode.SAME_HUB,
            f"Drone is already docked at '{destination.id}'; choose a different Hub.",
        )
    if origin is not None and origin.id != destination.id:
        if km > budget_km:
            reject(
                RelocationReasonCode.ROUTE_TOO_LONG,
                f"Route of {km:.2f} km exceeds the {budget_km:g} km mission budget.",
            )
        if not has_enough_battery(drone.battery_pct, energy):
            reject(
                RelocationReasonCode.INSUFFICIENT_BATTERY,
                f"Drone battery is {drone.battery_pct}%; the flight needs "
                f"{energy.required_battery_pct:.1f}% including the "
                f"{energy.reserve_pct:g}% reserve.",
            )
        if occupancy[destination.id] >= destination.drone_capacity:
            reject(
                RelocationReasonCode.DESTINATION_FULL,
                f"'{destination.id}' is at physical capacity ({destination.drone_capacity}).",
            )

    warnings: list[str] = []
    if origin is not None and waiting_orders_at_origin > 0:
        warnings.append(
            f"{waiting_orders_at_origin} order(s) are waiting for pickup at '{origin.id}'; "
            "relocating this drone leaves one fewer drone there."
        )
    warnings.append(
        "The destination is not reserved: if it is full when the drone arrives it lands at "
        "another reachable Hub."
    )

    return RelocationPlanResponse(
        drone_id=drone.id,
        eligible=not reasons,
        reasons=reasons,
        origin_hub_id=origin.id if origin is not None else None,
        destination_hub_id=destination.id,
        distance_km=km,
        distance_budget_km=budget_km,
        required_battery_pct=energy.required_battery_pct,
        expected_battery_use_pct=km * energy.empty_rate_pct_per_km,
        drone_battery_pct=drone.battery_pct,
        destination_docked_drones=occupancy[destination.id],
        destination_capacity=destination.drone_capacity,
        warnings=warnings,
    )


def _waiting_orders(session: Session, hub_id: str) -> int:
    statement = select(func.count(DeliveryOrder.id)).where(
        DeliveryOrder.origin_hub_id == hub_id,
        DeliveryOrder.status == OrderStatus.READY_FOR_PICKUP.value,
    )
    return int(session.scalar(statement) or 0)


def _plan(
    session: Session, drone: Drone, destination: Hub, settings: Settings
) -> RelocationPlanResponse:
    hubs = repository.list_hubs(session)
    origin = docked_hub(drone, hubs, settings.hub_dock_proximity_m)
    return evaluate_relocation(
        drone=drone,
        destination=destination,
        hubs=hubs,
        drones=repository.list_drones(session),
        drone_has_active_mission=repository.drone_has_active_mission(session, drone.id),
        waiting_orders_at_origin=0 if origin is None else _waiting_orders(session, origin.id),
        dock_proximity_m=settings.hub_dock_proximity_m,
    )


def _load(session: Session, drone_id: str, hub_id: str, *, lock: bool) -> tuple[Drone, Hub]:
    drone = repository.get_drone(session, drone_id, lock=lock)
    if drone is None:
        raise DroneNotFoundError(drone_id)
    statement = select(Hub).where(Hub.id == hub_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    hub = session.scalars(statement).one_or_none()
    if hub is None:
        raise HubNotFoundError(hub_id)
    return drone, hub


def preview_relocation(
    session: Session, drone_id: str, destination_hub_id: str, settings: Settings
) -> RelocationPlanResponse:
    """Read-only: evaluates the relocation and changes nothing."""
    drone, destination = _load(session, drone_id, destination_hub_id, lock=False)
    return _plan(session, drone, destination, settings)


def _start_once(
    session: Session,
    drone_id: str,
    destination_hub_id: str,
    now: datetime,
    settings: Settings,
    origin: EventOrigin,
    reason: str | None,
) -> Mission:
    mission_id: str | None = None
    try:
        # Feature 020: the rain warning gate, the first lock of the takeoff transaction.
        weather.lock_for_takeoff(session)
        drone, destination = _load(session, drone_id, destination_hub_id, lock=True)
        plan = _plan(session, drone, destination, settings)  # revalidated under the locks
        if not plan.eligible or plan.origin_hub_id is None:
            raise RelocationRejectedError(plan)
        hubs = {hub.id: hub for hub in repository.list_hubs(session)}
        source = hubs[plan.origin_hub_id]
        total_seconds = flight_duration_s(
            plan.distance_km,
            plan.distance_budget_km,
            settings.sim_flight_min_seconds,
            settings.sim_flight_max_seconds,
        )
        legs, pace = build_relocation_legs(
            hub_point(source), hub_point(destination), total_seconds=total_seconds
        )
        mission_id = new_mission_id()
        mission = Mission(
            id=mission_id,
            order_id=None,
            purpose=MissionPurpose.RELOCATION.value,
            drone_id=drone.id,
            origin_hub_id=source.id,
            return_hub_id=destination.id,
            status=MissionStatus.IN_FLIGHT.value,
            origin_to_destination_km=plan.distance_km,
            destination_to_return_km=0.0,
            total_km=plan.distance_km,
            expected_energy_pct=plan.expected_battery_use_pct,
            worst_case_energy_pct=plan.expected_battery_use_pct,
        )
        session.add(mission)
        session.flush()
        first = legs[0]
        drone.status = DroneStatus.IN_FLIGHT.value
        session.add(
            MissionFlight(
                mission_id=mission.id,
                phase=FlightPhase.RELOCATING.value,
                started_at=now,
                start_battery_pct=float(drone.battery_pct),
                battery_pct=float(drone.battery_pct),
                legs=[leg_to_dict(leg) for leg in legs],
                pace_s_per_km=pace,
                planned_return_hub_id=destination.id,
                landing_target_hub_id=destination.id,
                tried_hub_ids=[],
                longitude=source.longitude,
                latitude=source.latitude,
                progress=0.0,
                target_longitude=first.target[0],
                target_latitude=first.target[1],
                target_eta_s=first.duration_s,
                updated_at=now,
            )
        )
        session.flush()
        append_event(
            session,
            event_type=EventType.DRONE_RELOCATION,
            origin=origin,
            mission_id=mission.id,
            flight_id=mission.id,
            drone_id=drone.id,
            reason=f"Drone {drone.id} relocates from {source.name} to {destination.name}"
            + (f" ({reason})" if reason else ""),
            details={
                "phase": "STARTED",
                "origin_hub_id": source.id,
                "destination_hub_id": destination.id,
                "distance_km": round(plan.distance_km, 3),
                **({"trigger": reason} if reason else {}),
            },
            dedupe_key=f"{EventType.DRONE_RELOCATION.value}:STARTED:{mission.id}",
            occurred_at=now,
        )
        session.commit()
        return mission
    except IntegrityError:
        # A concurrent mission won the unique index, or the generated id collided. Look again from
        # a clean transaction and only retry a genuine id collision.
        session.rollback()
        id_taken = (
            mission_id is not None and repository.get_mission(session, mission_id) is not None
        )
        drone_row, destination_row = _load(session, drone_id, destination_hub_id, lock=False)
        plan = _plan(session, drone_row, destination_row, settings)
        session.rollback()
        if not plan.eligible:
            raise RelocationRejectedError(plan) from None
        if id_taken:
            raise _IdCollisionError from None
        raise
    except BaseException:
        session.rollback()  # also releases the row locks
        raise


def start_relocation(
    session: Session,
    drone_id: str,
    destination_hub_id: str,
    now: datetime,
    settings: Settings,
    *,
    origin: EventOrigin = EventOrigin.MANUAL,
    reason: str | None = None,
) -> Mission:
    """Revalidate and start a relocation flight atomically (mission, flight, drone, event).

    `reason` is an optional short explanation recorded in the STARTED event (the automatic fleet
    rebalancing, Feature 019B, says why it moved the drone).
    """
    # Nothing would fly it without the worker; refuse before taking any lock.
    beat = heartbeat.last_heartbeat(session)
    if not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds):
        session.rollback()
        raise WorkerUnavailableError(beat, settings.sim_heartbeat_stale_seconds)
    session.rollback()
    for _ in range(MAX_ID_ATTEMPTS):
        try:
            return _start_once(session, drone_id, destination_hub_id, now, settings, origin, reason)
        except _IdCollisionError:
            continue
    raise MissionError("Could not allocate a unique mission id")
