"""Generate one simulated delivery order on demand.

Feature 017C: the destination is sampled organically (`locations.py`) inside the approximate
operating area, labelled with a synthetic "Delivery Point TC-0042" identifier, and checked with the
mission planner's own routing and energy helpers (distance budget to the nearest Hub and a full
battery at the chosen weight). If no flyable point is found in a bounded number of attempts, or the
database holds no Hub or drone model to check against, it falls back to a random route from the
prevalidated catalog (`generator_catalog.py`), as Feature 015A did.

The order is created through the existing `create_order` service, so it follows the normal
persistence path (Hub check, unique id, rollback on failure) and starts as `READY_FOR_PICKUP`.
Nothing here looks at drones, battery state, Hub occupancy, missions or the Automatic Dispatch
mode: the order simply queues until the dispatcher can serve it. Manual orders never come through
here, and existing orders are never changed.
"""

import random
import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.drones.models import DroneModel
from app.events.models import EventOrigin
from app.hubs.models import Hub
from app.missions.energy import estimate_energy, has_enough_battery
from app.missions.routing import Point, distance_km, hub_point, hubs_by_distance
from app.orders import service
from app.orders.generator_catalog import ROUTE_CATALOG, CatalogRoute
from app.orders.locations import sample_delivery
from app.orders.models import MAX_PACKAGE_WEIGHT_KG, DeliveryOrder, OrderStatus
from app.orders.schemas import OrderCreateRequest

_rng = random.SystemRandom()

MIN_WEIGHT_KG = 0.2
POINT_LABEL = "Delivery Point TC-"  # TC: Tricity. A synthetic id, not a street address.
_POINT_PATTERN = re.compile(r"Delivery Point TC-(\d+)")


def _pick_weight(low: float, high: float, rng: random.Random) -> float:
    """A weight in [low, high], rounded to 0.1 kg and never outside the range."""
    return min(max(round(rng.uniform(low, high), 1), low), high)


def pick_weight_kg(route: CatalogRoute, rng: random.Random) -> float:
    """A weight in the route's range, rounded to 0.1 kg and never outside the range."""
    return _pick_weight(route.min_weight_kg, route.max_weight_kg, rng)


def max_flyable_weight_kg(
    origin: Hub,
    destination: Point,
    hubs: Sequence[Hub],
    model: DroneModel,
    payload_energy_factor: float,
) -> float | None:
    """The heaviest parcel (0.1 kg steps) a full-battery drone can take on this route, or None.

    Uses the planner's own rules: the route to the nearest Hub must be inside the mission budget and
    the worst case (parcel stays on board) plus the reserve must fit in 100 % battery. The energy
    figures come from `estimate_energy` / `has_enough_battery`; nothing is recalculated here.
    """
    outbound_km = distance_km(hub_point(origin), destination)
    return_km = hubs_by_distance(destination, hubs)[0][1]
    if outbound_km + return_km > model.recommended_mission_range_km:
        return None
    steps = round(MAX_PACKAGE_WEIGHT_KG * 10)
    for tenths in range(steps, round(MIN_WEIGHT_KG * 10) - 1, -1):
        weight = tenths / 10
        estimate = estimate_energy(
            outbound_km=outbound_km,
            return_km=return_km,
            weight_kg=weight,
            model=model,
            payload_energy_factor=payload_energy_factor,
        )
        if has_enough_battery(100, estimate):
            return weight
    return None


def _next_point_number(session: Session) -> int:
    """One more than the highest existing point number, so labels keep counting up."""
    addresses = session.scalars(
        select(DeliveryOrder.destination_address).where(
            DeliveryOrder.destination_address.like(f"{POINT_LABEL}%")
        )
    )
    numbers = [int(m.group(1)) for a in addresses if (m := _POINT_PATTERN.fullmatch(a))]
    return max(numbers, default=0) + 1


def _organic_request(
    session: Session, rng: random.Random, payload_energy_factor: float
) -> OrderCreateRequest | None:
    hubs = list(session.scalars(select(Hub).order_by(Hub.id)))
    model = session.scalars(select(DroneModel).order_by(DroneModel.id)).first()
    if not hubs or model is None:
        return None
    taken = [
        (lon, lat)
        for lon, lat in session.execute(
            select(DeliveryOrder.destination_longitude, DeliveryOrder.destination_latitude).where(
                DeliveryOrder.status != OrderStatus.DELIVERED.value
            )
        )
    ]

    def is_flyable(origin: Hub, point: Point) -> bool:
        return max_flyable_weight_kg(origin, point, hubs, model, payload_energy_factor) is not None

    sample = sample_delivery(rng, hubs, taken, is_flyable)
    if sample is None:
        return None
    cap = max_flyable_weight_kg(sample.origin, sample.point, hubs, model, payload_energy_factor)
    if cap is None:  # cannot happen: is_flyable just accepted this point
        return None
    longitude, latitude = sample.point
    return OrderCreateRequest(
        origin_hub_id=sample.origin.id,
        destination_address=f"{POINT_LABEL}{_next_point_number(session):04d}",
        destination_longitude=longitude,
        destination_latitude=latitude,
        package_weight_kg=_pick_weight(MIN_WEIGHT_KG, cap, rng),
    )


def generate_one_order(
    session: Session,
    *,
    rng: random.Random | None = None,
    catalog: Sequence[CatalogRoute] = ROUTE_CATALOG,
    payload_energy_factor: float | None = None,
) -> DeliveryOrder:
    """Create and return exactly one order; raises the order service's errors unchanged."""
    rng = rng or _rng
    factor = (
        get_settings().mission_payload_energy_factor
        if payload_energy_factor is None
        else payload_energy_factor
    )
    request = _organic_request(session, rng, factor)
    if request is None:  # no flyable point found, or nothing to check against: use the catalog
        route = rng.choice(catalog)
        request = OrderCreateRequest(
            origin_hub_id=route.origin_hub_id,
            destination_address=route.destination_address,
            destination_longitude=route.longitude,
            destination_latitude=route.latitude,
            package_weight_kg=pick_weight_kg(route, rng),
        )
    return service.create_order(session, request, EventOrigin.AUTOMATIC)
