"""Deterministic mission feasibility for one order and one drone.

`evaluate_plan` is a pure function over already-loaded data: it reads nothing and writes nothing,
so the read-only preview and the confirmation step share exactly the same rules. It reports every
reason an assignment is not possible, plus the route, energy estimate and Hub occupancy.

Simplifications (MVP, simulation only): geodesic distances, no airspace or weather; a transparent
payload-aware energy estimate (see `energy.py`); presence at a Hub is approximated from status and
position (see `presence.py`). The planned return Hub is a planning-time choice that is not reserved.
"""

from collections.abc import Sequence

from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions.capacity import SkipReason, choose_return_hub
from app.missions.energy import EnergyEstimate, estimate_energy, has_enough_battery
from app.missions.presence import docked_hub, hub_occupancy
from app.missions.routing import distance_km, hub_point, hubs_by_distance
from app.missions.schemas import (
    HubOccupancy,
    PlanEnergy,
    PlanReason,
    PlanResponse,
    PlanRoute,
    ReasonCode,
    SkippedHub,
)
from app.orders.models import DeliveryOrder, OrderStatus

NOTES = [
    "The return Hub is planned, not reserved: Hub occupancy may change before landing.",
    "Distances use a simplified great-circle model and energy figures are simulation "
    "assumptions, not certified flight performance.",
    "Presence at a Hub is approximated from drone status and position.",
]


def evaluate_plan(
    *,
    order: DeliveryOrder,
    drone: Drone,
    hubs: Sequence[Hub],
    drones: Sequence[Drone],
    order_has_active_mission: bool,
    drone_has_active_mission: bool,
    payload_energy_factor: float,
    dock_proximity_m: float,
) -> PlanResponse:
    origin = next((hub for hub in hubs if hub.id == order.origin_hub_id), None)
    if origin is None:  # unreachable while the foreign key holds; fail loudly rather than guess
        raise ValueError(f"Origin Hub '{order.origin_hub_id}' is not among the known Hubs")

    model = drone.model
    destination = (order.destination_longitude, order.destination_latitude)
    outbound_km = distance_km(hub_point(origin), destination)
    candidates = hubs_by_distance(destination, hubs)
    nearest, nearest_km = candidates[0]
    budget_km = float(model.recommended_mission_range_km)
    occupancy = hub_occupancy(drones, hubs, dock_proximity_m)
    docked = docked_hub(drone, hubs, dock_proximity_m)

    def energy_for(return_km: float) -> EnergyEstimate:
        return estimate_energy(
            outbound_km=outbound_km,
            return_km=return_km,
            weight_kg=order.package_weight_kg,
            model=model,
            payload_energy_factor=payload_energy_factor,
        )

    def reachable(return_km: float) -> bool:
        within_budget = outbound_km + return_km <= budget_km
        return within_budget and has_enough_battery(drone.battery_pct, energy_for(return_km))

    reasons: list[PlanReason] = []

    def reject(code: ReasonCode, message: str) -> None:
        reasons.append(PlanReason(code=code, message=message))

    if order.status != OrderStatus.READY_FOR_PICKUP:
        reject(
            ReasonCode.ORDER_NOT_READY,
            f"Order is {order.status}; the parcel must be confirmed at the origin Hub "
            f"({OrderStatus.READY_FOR_PICKUP.value}).",
        )
    if order_has_active_mission:
        reject(ReasonCode.ORDER_ALREADY_ASSIGNED, "The order already has an active mission.")
    if drone_has_active_mission:
        reject(ReasonCode.DRONE_ALREADY_ASSIGNED, "The drone already has an active mission.")
    if drone.status != DroneStatus.IDLE:
        reject(ReasonCode.DRONE_NOT_AVAILABLE, f"Drone is {drone.status}; it must be IDLE.")
    if docked is None or docked.id != origin.id:
        reject(
            ReasonCode.DRONE_NOT_AT_ORIGIN_HUB,
            f"Drone is not docked at the origin Hub '{origin.id}' "
            f"(within {dock_proximity_m:g} m, not in flight).",
        )
    if order.package_weight_kg > model.max_payload_kg:
        reject(
            ReasonCode.OVERWEIGHT,
            f"Parcel weighs {order.package_weight_kg} kg; the drone model carries at most "
            f"{model.max_payload_kg} kg.",
        )

    # Every other Hub is at least as far from the destination as the nearest one, so if the
    # nearest Hub is out of range, no return Hub can be reached.
    nearest_total = outbound_km + nearest_km
    nearest_energy = energy_for(nearest_km)
    range_ok = True
    if nearest_total > budget_km:
        range_ok = False
        reject(
            ReasonCode.ROUTE_TOO_LONG,
            f"Route of {nearest_total:.2f} km exceeds the {budget_km:g} km mission budget.",
        )
    if not has_enough_battery(drone.battery_pct, nearest_energy):
        range_ok = False
        reject(
            ReasonCode.INSUFFICIENT_BATTERY,
            f"Drone battery is {drone.battery_pct}%; the worst case needs "
            f"{nearest_energy.required_battery_pct:.1f}% including the "
            f"{nearest_energy.reserve_pct:g}% reserve.",
        )

    chosen: Hub | None = None
    skipped: list[tuple[Hub, SkipReason]] = []
    if range_ok:
        choice = choose_return_hub(candidates, occupancy, docked_at=docked, is_reachable=reachable)
        chosen, skipped = choice.hub, choice.skipped
        if chosen is None:
            # The nearest Hub passed the range checks, so it can only have been skipped for being
            # full; every farther Hub is either full too or out of range.
            reject(
                ReasonCode.RETURN_HUBS_FULL,
                "Every reachable return Hub is at physical capacity.",
            )

    basis = chosen or nearest
    basis_km = {hub.id: distance for hub, distance in candidates}[basis.id]
    energy = energy_for(basis_km)

    return PlanResponse(
        order_id=order.id,
        drone_id=drone.id,
        eligible=not reasons,
        reasons=reasons,
        route=PlanRoute(
            origin_hub_id=origin.id,
            return_hub_id=chosen.id if chosen else None,
            basis_hub_id=basis.id,
            origin_to_destination_km=outbound_km,
            destination_to_return_km=basis_km,
            total_km=outbound_km + basis_km,
        ),
        energy=PlanEnergy(
            empty_rate_pct_per_km=energy.empty_rate_pct_per_km,
            loaded_rate_pct_per_km=energy.loaded_rate_pct_per_km,
            payload_energy_factor=payload_energy_factor,
            expected_pct=energy.expected_pct,
            worst_case_pct=energy.worst_case_pct,
            reserve_pct=energy.reserve_pct,
            required_battery_pct=energy.required_battery_pct,
            drone_battery_pct=drone.battery_pct,
        ),
        distance_budget_km=budget_km,
        hub_occupancy=[
            HubOccupancy(
                hub_id=hub.id, docked_drones=occupancy[hub.id], capacity=hub.drone_capacity
            )
            for hub in sorted(hubs, key=lambda h: h.id)
        ],
        skipped_return_hubs=[SkippedHub(hub_id=hub.id, reason=why) for hub, why in skipped],
        notes=list(NOTES),
    )
