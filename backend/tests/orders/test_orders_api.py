from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.hubs.seed import seed_hubs
from app.orders.seed import seed_orders

ORDER_FIELDS = {
    "id",
    "origin_hub_id",
    "destination_address",
    "destination_longitude",
    "destination_latitude",
    "package_weight_kg",
    "status",
    "delivered_at",
    "cancelled_at",
    "delivery_failed_at",
    "created_at",
    "updated_at",
}


def test_list_orders_is_empty_before_seeding(client: TestClient) -> None:
    response = client.get("/api/orders")

    assert response.status_code == 200
    assert response.json() == []


def test_list_orders_returns_seeded_orders_in_stable_order(
    client: TestClient, session: Session
) -> None:
    seed_hubs(session)
    seed_orders(session)

    response = client.get("/api/orders")

    assert response.status_code == 200
    orders = response.json()
    assert [o["id"] for o in orders] == [f"ORD-{n:03d}" for n in range(1, 12)]
    assert all(set(o) == ORDER_FIELDS for o in orders)
    assert client.get("/api/orders").json() == orders


def test_order_detail_has_the_agreed_contract(client: TestClient, session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)

    response = client.get("/api/orders/ORD-006")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ORDER_FIELDS
    assert body["id"] == "ORD-006"
    assert body["origin_hub_id"] == "hub-forum-gdansk"
    assert body["status"] == "READY_FOR_PICKUP"
    assert body["package_weight_kg"] == 3.0
    assert isinstance(body["destination_longitude"], float)
    assert isinstance(body["destination_latitude"], float)
    assert "assigned_drone_id" not in body
    assert body["created_at"]
    assert body["updated_at"]


def test_unknown_order_returns_404(client: TestClient, session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)

    response = client.get("/api/orders/ORD-999")

    assert response.status_code == 404
    assert "ORD-999" in response.json()["detail"]


def test_hubs_and_drones_apis_still_work(client: TestClient, session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)

    assert len(client.get("/api/hubs").json()) == 4
    assert client.get("/api/drones").json() == []
    assert client.get("/api/health").status_code == 200
