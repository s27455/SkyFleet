"""Physical presence of drones at Hubs and Hub occupancy.

MVP simulation approximation (mirrors the frontend rule in `fleetPlacement.ts`): a drone is docked
at a Hub when its status is not `IN_FLIGHT` and its stored position is within the proximity radius
of that Hub (the nearest Hub wins; equal distances go to the lower Hub id). `Drone.hub_id` is the
administrative assignment and is deliberately not used. Docking and charging hardware will be the
authoritative source later.

Occupancy is the number of drones docked at a Hub right now. Missions never count: assigning or
cancelling a mission does not change it, and an in-flight drone counts at no Hub.
"""

from collections import Counter
from collections.abc import Sequence

from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions.routing import distance_km, hub_point


def docked_hub(drone: Drone, hubs: Sequence[Hub], radius_m: float) -> Hub | None:
    """The Hub the drone is docked at, or None (in flight, or not within range of any Hub)."""
    if drone.status == DroneStatus.IN_FLIGHT:
        return None
    position = (drone.longitude, drone.latitude)
    nearest: Hub | None = None
    nearest_distance = float("inf")
    for hub in hubs:
        distance_m = distance_km(position, hub_point(hub)) * 1000
        if distance_m > radius_m:
            continue
        if distance_m < nearest_distance or (
            distance_m == nearest_distance and nearest is not None and hub.id < nearest.id
        ):
            nearest, nearest_distance = hub, distance_m
    return nearest


def hub_occupancy(drones: Sequence[Drone], hubs: Sequence[Hub], radius_m: float) -> Counter[str]:
    """Docked drones per Hub id (Hubs with none are simply absent from the counter)."""
    counts: Counter[str] = Counter()
    for drone in drones:
        hub = docked_hub(drone, hubs, radius_m)
        if hub is not None:
            counts[hub.id] += 1
    return counts
