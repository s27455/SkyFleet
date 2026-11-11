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
