"""Administrative order management API (feature 012)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.missions import service as missions_service
from app.missions.models import Mission
from app.orders.models import DeliveryOrder, OrderStatus

FORUM = "hub-forum-gdansk"
OSOWA = "hub-centrum-handlowe-osowa"

VALID = {
    "origin_hub_id": FORUM,
    "destination_address": "ul. Testowa 1, Gdańsk",
    "destination_longitude": 18.65,
    "destination_latitude": 54.35,
    "package_weight_kg": 1.5,
}


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/orders", json={**VALID, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


# --- create -----------------------------------------------------------------------------------


def test_create_order_is_ready_and_visible_in_reads(client: TestClient, seeded: Session) -> None:
    body = _create(client)

    assert str(body["id"]).startswith("ORD-")
    assert body["status"] == "READY_FOR_PICKUP"
    assert body["origin_hub_id"] == FORUM
    assert (body["destination_longitude"], body["destination_latitude"]) == (18.65, 54.35)
    assert body["package_weight_kg"] == 1.5
    assert client.get(f"/api/orders/{body['id']}").json() == body
    assert body["id"] in [o["id"] for o in client.get("/api/orders").json()]


def test_create_trims_address_and_does_not_snap_to_hub(client: TestClient, seeded: Session) -> None:
    body = _create(client, destination_address="  ul. Morska 5, Gdynia  ")

    assert body["destination_address"] == "ul. Morska 5, Gdynia"
    assert (body["destination_longitude"], body["destination_latitude"]) == (18.65, 54.35)


def test_created_order_can_be_planned_with_an_eligible_drone(
    client: TestClient, seeded: Session
) -> None:
    body = _create(client)

    response = client.get(
        "/api/missions/plan", params={"order_id": str(body["id"]), "drone_id": "DRN-007"}
    )

    assert response.status_code == 200
    assert response.json()["eligible"] is True


def test_create_does_not_create_a_mission(client: TestClient, seeded: Session) -> None:
    _create(client)

    assert client.get("/api/missions").json() == []


def test_create_rejects_unknown_hub(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/orders", json={**VALID, "origin_hub_id": "hub-nowhere"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "HUB_NOT_FOUND"


def test_create_rejects_invalid_values(client: TestClient, seeded: Session) -> None:
    before = len(client.get("/api/orders").json())
    invalid: list[dict[str, object]] = [
        {"destination_address": ""},
        {"destination_address": "   "},
        {"destination_longitude": 181},
        {"destination_longitude": -181},
        {"destination_latitude": 91},
        {"destination_latitude": -91},
        {"package_weight_kg": 0},
        {"package_weight_kg": -1},
        {"package_weight_kg": 3.01},
        {"status": "DELIVERED"},
        {"id": "ORD-001"},
    ]
    for overrides in invalid:
        response = client.post("/api/orders", json={**VALID, **overrides})
        assert response.status_code == 422, overrides
    missing = {k: v for k, v in VALID.items() if k != "package_weight_kg"}
    assert client.post("/api/orders", json=missing).status_code == 422
    assert len(client.get("/api/orders").json()) == before


def test_create_accepts_the_maximum_weight(client: TestClient, seeded: Session) -> None:
    assert _create(client, package_weight_kg=3.0)["package_weight_kg"] == 3.0


# --- update -----------------------------------------------------------------------------------


def test_patch_unknown_order_is_404(client: TestClient, seeded: Session) -> None:
    response = client.patch("/api/orders/ORD-999", json={"package_weight_kg": 1})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ORDER_NOT_FOUND"


def test_patch_changes_fields_and_is_visible_in_reads(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]

    response = client.patch(
        f"/api/orders/{order_id}",
        json={
            "origin_hub_id": OSOWA,
            "destination_address": "ul. Nowa 2, Gdynia",
            "destination_longitude": 18.5,
            "destination_latitude": 54.45,
            "package_weight_kg": 2.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["origin_hub_id"] == OSOWA
    assert body["destination_address"] == "ul. Nowa 2, Gdynia"
    assert (body["destination_longitude"], body["destination_latitude"]) == (18.5, 54.45)
    assert body["package_weight_kg"] == 2.0
    assert body["status"] == "READY_FOR_PICKUP"
    reread = client.get(f"/api/orders/{order_id}").json()
    # SQLite returns naive timestamps on a fresh read, so compare the other fields.
    assert {k: v for k, v in reread.items() if k != "updated_at"} == {
        k: v for k, v in body.items() if k != "updated_at"
    }


def test_patch_partial_leaves_other_fields_unchanged(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]

    body = client.patch(f"/api/orders/{order_id}", json={"package_weight_kg": 0.5}).json()

    assert body["package_weight_kg"] == 0.5
    assert body["destination_address"] == VALID["destination_address"]
    assert body["origin_hub_id"] == FORUM


def test_patch_is_reflected_in_planning(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]
    plan = {"order_id": str(order_id), "drone_id": "DRN-007"}
    before = client.get("/api/missions/plan", params=plan).json()

    client.patch(f"/api/orders/{order_id}", json={"destination_longitude": 18.7})
    after = client.get("/api/missions/plan", params=plan).json()

    assert after["route"]["origin_to_destination_km"] > before["route"]["origin_to_destination_km"]


def test_patch_rejects_forbidden_and_invalid_input(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]
    invalid: list[dict[str, object]] = [
        {},
        {"status": "DELIVERED"},
        {"id": "ORD-777"},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"destination_address": ""},
        {"destination_address": None},
        {"package_weight_kg": 3.5},
        {"destination_latitude": 95},
    ]
    for payload in invalid:
        assert client.patch(f"/api/orders/{order_id}", json=payload).status_code == 422, payload


def test_patch_rejects_unknown_hub(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]

    response = client.patch(f"/api/orders/{order_id}", json={"origin_hub_id": "hub-nowhere"})

    assert response.status_code == 404
    assert client.get(f"/api/orders/{order_id}").json()["origin_hub_id"] == FORUM


def test_patch_rejects_order_with_a_mission_of_any_status(
    client: TestClient, seeded: Session
) -> None:
    mission = missions_service.confirm_mission(seeded, "ORD-004", "DRN-007", Settings())

    active = client.patch("/api/orders/ORD-004", json={"package_weight_kg": 1})
    missions_service.cancel_mission(seeded, mission.id)
    cancelled = client.patch("/api/orders/ORD-004", json={"package_weight_kg": 1})

    for response in (active, cancelled):
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ORDER_HAS_MISSIONS"
    order = seeded.get(DeliveryOrder, "ORD-004")
    assert order is not None and order.package_weight_kg != 1


def test_patch_rejects_order_that_is_not_ready(
    client: TestClient, seeded: Session, make_order: Callable[..., DeliveryOrder]
) -> None:
    seeded.add(make_order(id="ORD-800", status=OrderStatus.AWAITING_HANDOVER.value))
    seeded.commit()

    response = client.patch("/api/orders/ORD-800", json={"package_weight_kg": 1})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_NOT_EDITABLE"


# --- delete -----------------------------------------------------------------------------------


def test_delete_mission_free_order(client: TestClient, seeded: Session) -> None:
    order_id = _create(client)["id"]

    response = client.delete(f"/api/orders/{order_id}")

    assert response.status_code == 204
    assert client.get(f"/api/orders/{order_id}").status_code == 404
    assert order_id not in [o["id"] for o in client.get("/api/orders").json()]


def test_delete_unknown_order_is_404(client: TestClient, seeded: Session) -> None:
    assert client.delete("/api/orders/ORD-999").status_code == 404


def test_delete_rejects_order_with_mission_history(client: TestClient, seeded: Session) -> None:
    mission = missions_service.confirm_mission(seeded, "ORD-004", "DRN-007", Settings())
    missions_service.cancel_mission(seeded, mission.id)

    response = client.delete("/api/orders/ORD-004")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_HAS_MISSIONS"
    assert client.get("/api/orders/ORD-004").status_code == 200
    assert seeded.get(Mission, mission.id) is not None


def test_delete_rejects_order_that_is_not_ready(
    client: TestClient, seeded: Session, make_order: Callable[..., DeliveryOrder]
) -> None:
    seeded.add(make_order(id="ORD-801", status=OrderStatus.OUT_FOR_DELIVERY.value))
    seeded.commit()

    response = client.delete("/api/orders/ORD-801")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_NOT_EDITABLE"
    assert client.get("/api/orders/ORD-801").status_code == 200
