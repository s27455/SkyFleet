"""Starting a mission (takeoff).

`start_mission` is a plain service function with no HTTP dependency, so the manual "Start Mission"
control, and later the autonomous dispatcher (Feature 011), call exactly the same logic.

A mission starts only if the simulation worker has a recent heartbeat (otherwise nothing would fly
it), it is `ASSIGNED`, and the full Feature 009 plan, rechecked with the *actual* current state of
the order, the drone, its battery and the Hubs, is still eligible. Takeoff then moves the mission
and the drone to IN_FLIGHT and the order to OUT_FOR_DELIVERY in one transaction. The drone stops
counting at its origin Hub immediately (an in-flight drone is never docked). Nothing is reserved.

Locks are taken in a fixed order (mission, order, drone), the same order as cancellation and the
engine, so concurrent starts, cancels and ticks cannot deadlock and a mission starts exactly once.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import DroneStatus
from app.missions import repository
from app.missions.models import Mission, MissionStatus
from app.missions.routing import hub_point
from app.missions.service import (
    MissionError,
    MissionNotFoundError,
    PlanRejectedError,
    load_order_and_drone,
    plan_for,
)
from app.orders.models import OrderStatus
from app.simulation import heartbeat
from app.simulation.flight import build_legs, flight_duration_s, leg_to_dict
from app.simulation.models import FlightPhase, MissionFlight


class WorkerUnavailableError(MissionError):
    """The simulation worker has no recent heartbeat, so a started mission would not fly."""

    def __init__(self, last_heartbeat_at: datetime | None, max_age_seconds: float) -> None:
        super().__init__(
            "The simulation worker is not running (no recent heartbeat); start it with "
            "`uv run python -m app.worker` and try again"
        )
        self.last_heartbeat_at = last_heartbeat_at
        self.max_age_seconds = max_age_seconds


class MissionNotStartableError(MissionError):
    def __init__(self, mission_id: str, status: str) -> None:
        super().__init__(f"Mission '{mission_id}' is {status}; only ASSIGNED missions can start")
        self.status = status


def start_mission(session: Session, mission_id: str, now: datetime, settings: Settings) -> Mission:
    # An unknown or already started mission is reported as such even when the worker is down;
    # the status is checked again under the row lock below.
    known = repository.get_mission(session, mission_id)
    if known is None:
        session.rollback()
        raise MissionNotFoundError(mission_id)
    if known.status != MissionStatus.ASSIGNED.value:
        session.rollback()
        raise MissionNotStartableError(known.id, known.status)

    beat = heartbeat.last_heartbeat(session)
    if not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds):
        session.rollback()
        raise WorkerUnavailableError(beat, settings.sim_heartbeat_stale_seconds)

    try:
        mission = repository.get_mission_for_update(session, mission_id)
        if mission is None:
            raise MissionNotFoundError(mission_id)
        if mission.status != MissionStatus.ASSIGNED.value:
            raise MissionNotStartableError(mission.id, mission.status)
        if mission.order_id is None:  # a relocation is created already in flight (Feature 019A)
            raise MissionNotStartableError(mission.id, mission.status)
        order, drone = load_order_and_drone(session, mission.order_id, mission.drone_id, lock=True)

        # Recheck everything with the actual current state; the mission's own claim is ignored.
        plan = plan_for(session, order, drone, settings, exclude_mission_id=mission.id)
        if not plan.eligible or plan.route.return_hub_id is None:
            raise PlanRejectedError(plan)

        hubs = {hub.id: hub for hub in repository.list_hubs(session)}
        origin = hubs[plan.route.origin_hub_id]
        return_hub = hubs[plan.route.return_hub_id]
        total_seconds = flight_duration_s(
            plan.route.total_km,
            drone.model.recommended_mission_range_km,
            settings.sim_flight_min_seconds,
            settings.sim_flight_max_seconds,
        )
        legs, pace = build_legs(
            hub_point(origin),
            (order.destination_longitude, order.destination_latitude),
            hub_point(return_hub),
            total_seconds=total_seconds,
            dwell_s=settings.sim_delivery_dwell_seconds,
        )
        first = legs[0]
        mission.status = MissionStatus.IN_FLIGHT.value
        order.status = OrderStatus.OUT_FOR_DELIVERY.value
        drone.status = DroneStatus.IN_FLIGHT.value
        session.add(
            MissionFlight(
                mission_id=mission.id,
                phase=FlightPhase.OUTBOUND.value,
                started_at=now,
                start_battery_pct=float(drone.battery_pct),
                battery_pct=float(drone.battery_pct),
                legs=[leg_to_dict(leg) for leg in legs],
                pace_s_per_km=pace,
                planned_return_hub_id=return_hub.id,
                landing_target_hub_id=return_hub.id,
                tried_hub_ids=[],
                longitude=origin.longitude,
                latitude=origin.latitude,
                progress=0.0,
                target_longitude=first.target[0],
                target_latitude=first.target[1],
                target_eta_s=first.duration_s,
                updated_at=now,
            )
        )
        session.commit()
        return mission
    except BaseException:
        session.rollback()  # also releases the row locks
        raise
