"""Simplified geodesic routing: great-circle (haversine) distances, no airspace or road model."""

import math
from collections.abc import Sequence

from app.hubs.models import Hub

EARTH_RADIUS_KM = 6371.0

Point = tuple[float, float]  # (longitude, latitude)


def distance_km(a: Point, b: Point) -> float:
    """Great-circle distance in kilometres between two (longitude, latitude) points."""
    lat_a, lat_b = math.radians(a[1]), math.radians(b[1])
    d_lat = lat_b - lat_a
    d_lng = math.radians(b[0] - a[0])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def hub_point(hub: Hub) -> Point:
    return (hub.longitude, hub.latitude)


def hubs_by_distance(point: Point, hubs: Sequence[Hub]) -> list[tuple[Hub, float]]:
    """Hubs with their distance to `point`, nearest first; equal distances go to the lower id."""
    measured = [(hub, distance_km(point, hub_point(hub))) for hub in hubs]
    return sorted(measured, key=lambda item: (item[1], item[0].id))


def nearest_reachable_hub(
    point: Point,
    hubs: Sequence[Hub],
    battery_pct: float,
    rate_pct_per_km: float,
    floor_pct: float,
) -> Hub | None:
    """The nearest Hub the battery reaches at `rate_pct_per_km` and still stays above `floor_pct`.

    Capacity is not considered here: the landing decision rechecks it and diverts if needed. Used
    for a loaded return (recall, Feature 018B; failed handover, Feature 018D).
    """
    for hub, km in hubs_by_distance(point, hubs):
        if battery_pct - rate_pct_per_km * km >= floor_pct:
            return hub
    return None
