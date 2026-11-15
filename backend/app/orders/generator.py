"""Generate one simulated delivery order on demand.

Feature 021D: every generated order is one of the curated routes of the catalog
(`generator_catalog.py`): a real street address with its own coordinates, the route's origin Hub and
a weight inside the route's range, so the displayed address always matches the destination
coordinates. Nothing is made up from arbitrary coordinates and no external geocoder is used. A
route that no open order uses is preferred; once every route is in use a repeat is allowed (the map
already spreads markers that share a place). The earlier organic generator (Feature 017C, synthetic
"Delivery Point TC-0042" labels) is no longer used here; orders created by it keep their labels.

Feature 021E: the catalog holds verified official address points (see `generator_catalog.py`) and
the choice is made in two simple steps so that no small area dominates: first a district that still
has a free route (every district equally likely, however many routes it has), then a free route of
that district. A district is an editorial label of the catalog, not an official boundary.

The order is created through the existing `create_order` service, so it follows the normal
persistence path (Hub check, unique id, rollback on failure) and starts as `READY_FOR_PICKUP`.
Nothing here looks at drones, battery state, Hub occupancy, missions or the Automatic Dispatch
mode: the order simply queues until the dispatcher can serve it. Manual orders never come through
here, and existing orders are never changed.
"""

import random
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import EventOrigin
from app.orders import service
from app.orders.generator_catalog import ROUTE_CATALOG, CatalogRoute
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.schemas import OrderCreateRequest

_rng = random.SystemRandom()


def _pick_weight(low: float, high: float, rng: random.Random) -> float:
    """A weight in [low, high], rounded to 0.1 kg and never outside the range."""
    return min(max(round(rng.uniform(low, high), 1), low), high)


def pick_weight_kg(route: CatalogRoute, rng: random.Random) -> float:
    """A weight in the route's range, rounded to 0.1 kg and never outside the range."""
    return _pick_weight(route.min_weight_kg, route.max_weight_kg, rng)


# Orders in these states no longer hold their destination: their route may be offered again.
_CLOSED_STATUSES = (
    OrderStatus.DELIVERED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.DELIVERY_FAILED.value,
)


def _place(longitude: float, latitude: float) -> tuple[float, float]:
    return (round(longitude, 6), round(latitude, 6))


def pick_route(routes: Sequence[CatalogRoute], rng: random.Random) -> CatalogRoute:
    """A district chosen uniformly among the districts of `routes`, then one of its routes.

    Districts are visited in sorted order so a seeded `rng` always gives the same result.
    """
    by_district: dict[tuple[str, str], list[CatalogRoute]] = {}
    for route in routes:
        by_district.setdefault((route.city, route.district), []).append(route)
    district = rng.choice(sorted(by_district))
    return rng.choice(by_district[district])


def _route_request(
    session: Session, rng: random.Random, catalog: Sequence[CatalogRoute]
) -> OrderCreateRequest:
    """One catalog route as an order, preferring a destination no open order uses."""
    taken = {
        _place(lon, lat)
        for lon, lat in session.execute(
            select(DeliveryOrder.destination_longitude, DeliveryOrder.destination_latitude).where(
                DeliveryOrder.status.notin_(_CLOSED_STATUSES)
            )
        )
    }
    free = [route for route in catalog if _place(route.longitude, route.latitude) not in taken]
    route = pick_route(free or list(catalog), rng)
    return OrderCreateRequest(
        origin_hub_id=route.origin_hub_id,
        destination_address=route.destination_address,
        destination_longitude=route.longitude,
        destination_latitude=route.latitude,
        package_weight_kg=pick_weight_kg(route, rng),
    )


def generate_one_order(
    session: Session,
    *,
    rng: random.Random | None = None,
    catalog: Sequence[CatalogRoute] = ROUTE_CATALOG,
) -> DeliveryOrder:
    """Create and return exactly one order; raises the order service's errors unchanged."""
    request = _route_request(session, rng or _rng, catalog)
    return service.create_order(session, request, EventOrigin.AUTOMATIC)
