"""Route feasibility for an order, from the planner's own rules (no second algorithm).

A parcel can be served from an origin Hub when a full-battery drone could fly origin → destination
and then to the nearest Hub: the whole route must fit the model's recommended mission distance and
the worst case (the parcel stays on board) plus the reserve must fit in 100 % battery, with the
payload at most the model's maximum. The distances come from `missions.routing` and the energy from
`missions.energy`; nothing is recalculated here. No drone, battery state or Hub capacity is looked
at: that is the dispatcher's concern.

Feature 021D: `choose_origin_hub` picks the origin Hub of a manual order that names none.
"""

from collections.abc import Sequence

from app.drones.models import DroneModel
from app.hubs.models import Hub
from app.missions.energy import estimate_energy, has_enough_battery
from app.missions.routing import Point, distance_km, hub_point, hubs_by_distance
from app.orders.models import MAX_PACKAGE_WEIGHT_KG

MIN_WEIGHT_KG = 0.2


def _battery_fits(
    outbound_km: float,
    return_km: float,
    weight_kg: float,
    model: DroneModel,
    payload_energy_factor: float,
) -> bool:
    estimate = estimate_energy(
        outbound_km=outbound_km,
        return_km=return_km,
        weight_kg=weight_kg,
        model=model,
        payload_energy_factor=payload_energy_factor,
    )
    return has_enough_battery(100, estimate)


def max_flyable_weight_kg(
    origin: Hub,
    destination: Point,
    hubs: Sequence[Hub],
    model: DroneModel,
    payload_energy_factor: float,
) -> float | None:
    """The heaviest parcel (0.1 kg steps) a full-battery drone can take on this route, or None."""
    outbound_km = distance_km(hub_point(origin), destination)
    return_km = hubs_by_distance(destination, hubs)[0][1]
    if outbound_km + return_km > model.recommended_mission_range_km:
        return None
    steps = round(MAX_PACKAGE_WEIGHT_KG * 10)
    for tenths in range(steps, round(MIN_WEIGHT_KG * 10) - 1, -1):
        weight = tenths / 10
        if _battery_fits(outbound_km, return_km, weight, model, payload_energy_factor):
            return weight
    return None


def route_problem(
    origin: Hub,
    destination: Point,
    weight_kg: float,
    hubs: Sequence[Hub],
    model: DroneModel,
    payload_energy_factor: float,
) -> str | None:
    """Why this origin cannot serve the parcel, or None when it can."""
    if weight_kg > model.max_payload_kg:
        return (
            f"the parcel weighs {weight_kg:g} kg; the drone model carries at most "
            f"{model.max_payload_kg:g} kg"
        )
    outbound_km = distance_km(hub_point(origin), destination)
    return_km = hubs_by_distance(destination, hubs)[0][1]
    budget_km = float(model.recommended_mission_range_km)
    if outbound_km + return_km > budget_km:
        return (
            f"the route of {outbound_km + return_km:.1f} km exceeds the {budget_km:g} km "
            "mission distance"
        )
    if not _battery_fits(outbound_km, return_km, weight_kg, model, payload_energy_factor):
        cap = max_flyable_weight_kg(origin, destination, hubs, model, payload_energy_factor)
        heaviest = f"the heaviest possible here is {cap:g} kg" if cap else "no weight is possible"
        return f"a full battery cannot cover this route with {weight_kg:g} kg ({heaviest})"
    return None


def choose_origin_hub(
    hubs: Sequence[Hub],
    model: DroneModel,
    destination: Point,
    weight_kg: float,
    payload_energy_factor: float,
) -> tuple[Hub | None, str | None]:
    """The nearest Hub (a tie goes to the lower id) that can serve the parcel, or why none can.

    The return distance is the destination's distance to its nearest Hub for every candidate and
    the outbound distance only grows with the candidate's distance, so when the nearest Hub cannot
    serve the parcel no other Hub can: the reason given is the nearest Hub's.
    """
    reason: str | None = None
    for hub, _km in hubs_by_distance(destination, hubs):
        problem = route_problem(hub, destination, weight_kg, hubs, model, payload_energy_factor)
        if problem is None:
            return hub, None
        reason = reason or problem
    return None, reason
