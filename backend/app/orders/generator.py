"""Generate one simulated delivery order on demand from the prevalidated route catalog.

The order is created through the existing `create_order` service, so it follows the normal
persistence path (Hub check, unique id, rollback on failure) and starts as `READY_FOR_PICKUP`.
Nothing here looks at drones, battery, Hub occupancy, missions or the Automatic Dispatch mode: the
order simply queues until the dispatcher can serve it.
"""

import random
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.orders import service
from app.orders.generator_catalog import ROUTE_CATALOG, CatalogRoute
from app.orders.models import DeliveryOrder
from app.orders.schemas import OrderCreateRequest

_rng = random.SystemRandom()


def pick_weight_kg(route: CatalogRoute, rng: random.Random) -> float:
    """A weight in the route's range, rounded to 0.1 kg and never outside the range."""
    weight = round(rng.uniform(route.min_weight_kg, route.max_weight_kg), 1)
    return min(max(weight, route.min_weight_kg), route.max_weight_kg)


def generate_one_order(
    session: Session,
    *,
    rng: random.Random | None = None,
    catalog: Sequence[CatalogRoute] = ROUTE_CATALOG,
) -> DeliveryOrder:
    """Create and return exactly one order; raises the order service's errors unchanged."""
    rng = rng or _rng
    route = rng.choice(catalog)
    return service.create_order(
        session,
        OrderCreateRequest(
            origin_hub_id=route.origin_hub_id,
            destination_address=route.destination_address,
            destination_longitude=route.longitude,
            destination_latitude=route.latitude,
            package_weight_kg=pick_weight_kg(route, rng),
        ),
    )
