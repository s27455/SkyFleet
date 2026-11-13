"""Organic delivery-point sampling for the order generator (Feature 017C).

Pure and seeded: everything random comes from the `random.Random` the caller passes, so a seeded
run is reproducible. Nothing here reads the database or knows about drones or batteries; whether a
point is flyable is decided by the `is_flyable` callback, which the generator builds from the
mission planner's own routing and energy helpers (no battery maths is repeated here).

A point is made by choosing an origin Hub, a style, a distance and a free bearing, then moving that
far from an anchor Hub. The styles are target proportions, not guarantees (feasibility comes first):

* local (about 60 %): close to the origin Hub;
* medium (about 30 %): farther out from the origin Hub;
* cross-hub (about 10 %): close to a different Hub, so the drone is likely to return there.

The polygon in `operating_area.py` is only an approximate operating area, not a land mask.
"""

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.hubs.models import Hub
from app.missions.routing import Point, distance_km, hub_point
from app.orders.operating_area import contains

LOCAL_SHARE = 0.60
MEDIUM_SHARE = 0.30  # the rest (about 10 %) is cross-hub

LOCAL_KM = (0.35, 2.0)
MEDIUM_KM = (2.0, 4.5)
CROSS_HUB_KM = (0.3, 1.8)  # around the other Hub

MIN_HUB_CLEARANCE_KM = 0.06  # never on top of a Hub
MIN_POINT_SEPARATION_KM = 0.05  # never on top of another open order
MAX_ATTEMPTS = 40
KM_PER_DEGREE_LAT = 111.32


@dataclass(frozen=True)
class Sample:
    origin: Hub
    point: Point
    style: str  # "local" | "medium" | "cross-hub"


def offset_point(anchor: Point, distance: float, bearing_rad: float) -> Point:
    """Move `distance` km from `anchor` along a bearing (flat-earth, fine at a few km)."""
    lon, lat = anchor
    d_lat = distance * math.cos(bearing_rad) / KM_PER_DEGREE_LAT
    d_lon = distance * math.sin(bearing_rad) / (KM_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return (lon + d_lon, lat + d_lat)


def _style(rng: random.Random, hub_count: int) -> str:
    roll = rng.random()
    if roll < LOCAL_SHARE:
        return "local"
    if roll < LOCAL_SHARE + MEDIUM_SHARE:
        return "medium"
    return "cross-hub" if hub_count > 1 else "medium"


def _skewed(rng: random.Random, low: float, high: float) -> float:
    """A distance in [low, high], more often nearer the low end so most drops stay close."""
    return low + (high - low) * float(rng.random() ** 1.4)


def sample_delivery(
    rng: random.Random,
    hubs: Sequence[Hub],
    taken: Sequence[Point],
    is_flyable: Callable[[Hub, Point], bool],
) -> Sample | None:
    """One organic delivery point, or None if no acceptable point was found in the attempts.

    `taken` are the destinations of orders still open; a new point keeps clear of them and of every
    Hub. `is_flyable(origin, point)` is the planner-based feasibility check.
    """
    if not hubs:
        return None
    ordered = sorted(hubs, key=lambda hub: hub.id)  # a stable base, so a seed gives one result
    for _ in range(MAX_ATTEMPTS):
        origin = rng.choice(ordered)
        style = _style(rng, len(ordered))
        if style == "cross-hub":
            anchor_hub = rng.choice([hub for hub in ordered if hub.id != origin.id])
            span = CROSS_HUB_KM
        else:
            anchor_hub = origin
            span = LOCAL_KM if style == "local" else MEDIUM_KM
        bearing = rng.uniform(0.0, 2 * math.pi)
        point = offset_point(hub_point(anchor_hub), _skewed(rng, *span), bearing)
        if not contains(point):
            continue
        if any(distance_km(point, hub_point(hub)) < MIN_HUB_CLEARANCE_KM for hub in ordered):
            continue
        if any(distance_km(point, other) < MIN_POINT_SEPARATION_KM for other in taken):
            continue
        if not is_flyable(origin, point):
            continue
        return Sample(origin=origin, point=point, style=style)
    return None
