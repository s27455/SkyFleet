"""Order generator core (feature 015A): catalog validity, generation and the API action."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dispatch.models import DispatchAutoState
from app.drones.models import DroneModel
from app.hubs.models import Hub
from app.missions.energy import estimate_energy, has_enough_battery
from app.missions.models import Mission
from app.missions.routing import distance_km, hub_point, hubs_by_distance
from app.orders.generator import generate_one_order, pick_weight_kg
from app.orders.generator_catalog import ROUTE_CATALOG, CatalogRoute
from app.orders.models import MAX_PACKAGE_WEIGHT_KG, DeliveryOrder, OrderStatus
from app.orders.service import HubNotFoundError

SETTINGS = Settings()
BAD_ROUTE = CatalogRoute("hub-does-not-exist", "ul. Testowa 1, Gdańsk", 18.6, 54.37, 0.5, 1.0)


def _order_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(DeliveryOrder)) or 0


# --- catalog ----------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTE_CATALOG, ids=lambda r: r.destination_address)
def test_catalog_route_is_flyable_at_both_weight_bounds(
    route: CatalogRoute, seeded: Session
) -> None:
    """Same rules as the planner: mission budget to the nearest return Hub plus a full battery."""
    hubs = list(seeded.scalars(select(Hub)))
    model = seeded.get(DroneModel, "SF-1")
    assert model is not None
    origin = next(hub for hub in hubs if hub.id == route.origin_hub_id)
    destination = (route.longitude, route.latitude)
    outbound = distance_km(hub_point(origin), destination)
    return_km = hubs_by_distance(destination, hubs)[0][1]

    assert 0 < route.min_weight_kg <= route.max_weight_kg <= MAX_PACKAGE_WEIGHT_KG
    assert outbound + return_km <= model.recommended_mission_range_km
    for weight in (route.min_weight_kg, route.max_weight_kg):
        estimate = estimate_energy(
            outbound_km=outbound,
            return_km=return_km,
            weight_kg=weight,
            model=model,
            payload_energy_factor=SETTINGS.mission_payload_energy_factor,
        )
        assert has_enough_battery(100, estimate), f"{route.destination_address} at {weight} kg"


def test_catalog_is_unique_and_covers_every_hub(seeded: Session) -> None:
    addresses = [(r.origin_hub_id, r.destination_address) for r in ROUTE_CATALOG]
    assert len(set(addresses)) == len(addresses)
    assert {r.origin_hub_id for r in ROUTE_CATALOG} == set(seeded.scalars(select(Hub.id)))


# --- service ----------------------------------------------------------------------------------


def _route_of(order: DeliveryOrder) -> CatalogRoute:
    return next(
        r
        for r in ROUTE_CATALOG
        if (r.origin_hub_id, r.destination_address)
        == (order.origin_hub_id, order.destination_address)
    )


def test_generate_creates_one_ready_order_from_a_catalog_route(seeded: Session) -> None:
    before = _order_count(seeded)

    order = generate_one_order(seeded, rng=random.Random(1))

    assert _order_count(seeded) == before + 1
    assert order.status == OrderStatus.READY_FOR_PICKUP.value
    assert order.id.startswith("ORD-")
    route = _route_of(
        order
    )  # the address, its coordinates and the origin Hub are one catalog entry
    assert (order.destination_longitude, order.destination_latitude) == (
        route.longitude,
        route.latitude,
    )
    assert route.min_weight_kg <= order.package_weight_kg <= route.max_weight_kg
    assert not order.destination_address.startswith("Delivery Point")


def test_no_catalog_route_uses_a_synthetic_label() -> None:
    for route in ROUTE_CATALOG:
        assert not route.destination_address.startswith("Delivery Point")


def _place(order: DeliveryOrder) -> tuple[float, float]:
    return (round(order.destination_longitude, 6), round(order.destination_latitude, 6))


def test_unused_routes_are_preferred_and_a_repeat_comes_only_when_all_are_in_use(
    seeded: Session,
) -> None:
    rng = random.Random(5)
    in_use = {_place(o) for o in seeded.scalars(select(DeliveryOrder))}
    all_places = {(round(r.longitude, 6), round(r.latitude, 6)) for r in ROUTE_CATALOG}
    free_count = len(all_places - in_use)
    assert 0 < free_count < len(all_places)  # the seed already uses part of the catalog

    created = [generate_one_order(seeded, rng=rng) for _ in range(free_count)]

    assert {_place(o) for o in created} == all_places - in_use  # each new order took a free route
    repeat = generate_one_order(seeded, rng=rng)  # every route is now in use: a repeat is allowed
    assert _place(repeat) in all_places


def test_a_route_of_a_closed_order_is_offered_again(seeded: Session) -> None:
    for order in seeded.scalars(select(DeliveryOrder)):
        order.status = OrderStatus.DELIVERED.value  # nothing is open any more
    seeded.commit()
    only = ROUTE_CATALOG[0]

    order = generate_one_order(seeded, rng=random.Random(1), catalog=[only])

    assert order.destination_address == only.destination_address


def test_legacy_synthetic_labels_are_left_alone(seeded: Session) -> None:
    legacy = seeded.scalars(select(DeliveryOrder)).first()
    assert legacy is not None
    legacy.destination_address = "Delivery Point TC-0042"
    seeded.commit()

    generate_one_order(seeded, rng=random.Random(2))

    seeded.refresh(legacy)
    assert legacy.destination_address == "Delivery Point TC-0042"


def test_weights_stay_in_each_routes_range() -> None:
    rng = random.Random(3)
    for route in ROUTE_CATALOG:
        for _ in range(200):
            assert route.min_weight_kg <= pick_weight_kg(route, rng) <= route.max_weight_kg


def test_generation_preserves_existing_orders(seeded: Session) -> None:
    before = {
        o.id: (o.destination_address, o.package_weight_kg)
        for o in seeded.scalars(select(DeliveryOrder))
    }

    for seed in range(5):
        generate_one_order(seeded, rng=random.Random(seed))

    after = {
        o.id: (o.destination_address, o.package_weight_kg)
        for o in seeded.scalars(select(DeliveryOrder))
    }
    assert before.items() <= after.items()
    assert len(after) == len(before) + 5


def test_failed_generation_leaves_no_order(seeded: Session) -> None:
    before = _order_count(seeded)

    with pytest.raises(HubNotFoundError):
        generate_one_order(seeded, catalog=[BAD_ROUTE])

    assert _order_count(seeded) == before


def test_generation_works_without_any_drone_and_creates_no_mission(session: Session) -> None:
    from app.hubs.seed import seed_hubs

    seed_hubs(session)  # Hubs only: no drones, no drone model

    order = generate_one_order(session, rng=random.Random(2))

    assert order.status == OrderStatus.READY_FOR_PICKUP.value
    assert session.scalar(select(func.count()).select_from(Mission)) == 0


# --- API --------------------------------------------------------------------------------------


def test_generate_endpoint_creates_one_order_visible_in_reads(
    client: TestClient, seeded: Session
) -> None:
    before = len(client.get("/api/orders").json())

    response = client.post("/api/orders/generate")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "READY_FOR_PICKUP"
    assert body["id"].startswith("ORD-")
    assert 0 < body["package_weight_kg"] <= MAX_PACKAGE_WEIGHT_KG
    assert client.get(f"/api/orders/{body['id']}").json() == body
    assert len(client.get("/api/orders").json()) == before + 1


def test_repeated_generate_requests_create_distinct_orders(
    client: TestClient, seeded: Session
) -> None:
    ids = {client.post("/api/orders/generate").json()["id"] for _ in range(10)}

    assert len(ids) == 10


def test_generate_does_not_change_dispatch_mode_or_start_missions(
    client: TestClient, seeded: Session
) -> None:
    assert client.post("/api/orders/generate").status_code == 201

    assert seeded.scalar(select(func.count()).select_from(Mission)) == 0
    assert seeded.scalar(select(func.count()).select_from(DispatchAutoState)) == 0
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is False


def test_generated_order_is_considered_by_dispatch_recommendations(
    client: TestClient, seeded: Session
) -> None:
    order_id = client.post("/api/orders/generate").json()["id"]

    result = client.get("/api/dispatch/recommendations").json()

    listed = {r["order_id"] for r in result["recommendations"]} | {
        p["order_id"] for p in result["pending"]
    }
    assert order_id in listed


def test_existing_manual_create_still_works(client: TestClient, seeded: Session) -> None:
    response = client.post(
        "/api/orders",
        json={
            "origin_hub_id": "hub-forum-gdansk",
            "destination_address": "ul. Testowa 1, Gdańsk",
            "destination_longitude": 18.65,
            "destination_latitude": 54.35,
            "package_weight_kg": 1.5,
        },
    )

    assert response.status_code == 201
