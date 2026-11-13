"""Read-only dispatch decision: which drone should serve which waiting order.

Each origin Hub has its own FIFO queue (order `created_at`, then id). An order is recommended the
first drone (by id) that is physically docked at its origin Hub, `IDLE`, at exactly 100% battery,
has no active mission, is not already recommended in this pass, and that the existing mission
planner (`evaluate_plan`, used unchanged) accepts. An order that gets no drone stays pending and the
pass moves on, so one blocked order or Hub never holds up another.

Nothing is written, reserved or started. Return-Hub capacity is whatever the planner checks against
the current physical occupancy; recommendations within one pass do not reserve landing places (an
accepted MVP simplification; assignment, a later feature, re-plans under locks).
"""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dispatch.schemas import (
    PendingOrder,
    PendingReason,
    Recommendation,
    RecommendationsResponse,
)
from app.drones import repository as drone_repository
from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions import repository as mission_repository
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.missions.planning import evaluate_plan
from app.missions.presence import docked_hub
from app.missions.schemas import ReasonCode
from app.orders import repository as order_repository
from app.orders.models import DeliveryOrder, OrderStatus

# Dispatch only sends fully charged drones. This is in addition to the planner's own energy check.
DISPATCH_BATTERY_PCT = 100


def recommend(
    *,
    orders: Sequence[DeliveryOrder],
    drones: Sequence[Drone],
    hubs: Sequence[Hub],
    active_order_ids: set[str],
    active_drone_ids: set[str],
    payload_energy_factor: float,
    dock_proximity_m: float,
) -> RecommendationsResponse:
    """Pure decision over already-loaded data."""
    queues: dict[str, list[DeliveryOrder]] = defaultdict(list)
    for order in sorted(orders, key=lambda o: (o.created_at, o.id)):
        if order.status == OrderStatus.READY_FOR_PICKUP and order.id not in active_order_ids:
            queues[order.origin_hub_id].append(order)

    # Drones that may be dispatched, by the Hub they are physically docked at, in id order.
    available: dict[str, list[Drone]] = defaultdict(list)
    for drone in sorted(drones, key=lambda d: d.id):
        if (
            drone.status == DroneStatus.IDLE
            and drone.battery_pct == DISPATCH_BATTERY_PCT
            and drone.id not in active_drone_ids
        ):
            hub = docked_hub(drone, hubs, dock_proximity_m)
            if hub is not None:
                available[hub.id].append(drone)

    claimed: set[str] = set()
    recommendations: list[Recommendation] = []
    pending: list[PendingOrder] = []

    for hub in sorted(hubs, key=lambda h: h.id):
        for order in queues.get(hub.id, []):
            candidates = [d for d in available.get(hub.id, []) if d.id not in claimed]
            if not candidates:
                pending.append(
                    PendingOrder(
                        order_id=order.id,
                        origin_hub_id=hub.id,
                        reason=PendingReason.NO_ELIGIBLE_DRONE_AT_HUB,
                        planner_reasons=[],
                    )
                )
                continue

            seen: list[ReasonCode] = []
            for drone in candidates:
                plan = evaluate_plan(
                    order=order,
                    drone=drone,
                    hubs=hubs,
                    drones=drones,
                    order_has_active_mission=False,  # already excluded above
                    drone_has_active_mission=False,
                    payload_energy_factor=payload_energy_factor,
                    dock_proximity_m=dock_proximity_m,
                )
                if plan.eligible and plan.route.return_hub_id is not None:
                    claimed.add(drone.id)
                    recommendations.append(
                        Recommendation(
                            order_id=order.id,
                            drone_id=drone.id,
                            origin_hub_id=hub.id,
                            return_hub_id=plan.route.return_hub_id,
                        )
                    )
                    break
                seen.extend(r.code for r in plan.reasons if r.code not in seen)
            else:
                pending.append(
                    PendingOrder(
                        order_id=order.id,
                        origin_hub_id=hub.id,
                        reason=PendingReason.PLANNER_REJECTED,
                        planner_reasons=seen,
                    )
                )

    return RecommendationsResponse(recommendations=recommendations, pending=pending)


def recommend_for_session(session: Session, settings: Settings) -> RecommendationsResponse:
    """Load the current state (reads only) and decide."""
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    claims = session.execute(
        select(Mission.order_id, Mission.drone_id).where(Mission.status.in_(active))
    ).all()
    return recommend(
        orders=order_repository.list_orders(session),
        drones=drone_repository.list_drones(session),
        hubs=mission_repository.list_hubs(session),
        active_order_ids={order_id for order_id, _ in claims},
        active_drone_ids={drone_id for _, drone_id in claims},
        payload_energy_factor=settings.mission_payload_energy_factor,
        dock_proximity_m=settings.hub_dock_proximity_m,
    )
