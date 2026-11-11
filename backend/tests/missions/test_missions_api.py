import re
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions.models import Mission, MissionStatus
from app.orders.models import DeliveryOrder

OrderFactory = Callable[..., DeliveryOrder]

# ORD-001 starts at Galeria Bałtycka, where DRN-010 (100 %), DRN-011 (90 %) and DRN-012 (80 %) sit.
ORDER, DRONE = "ORD-001", "DRN-010"


def preview(client: TestClient, order_id: str = ORDER, drone_id: str = DRONE) -> Any:
    return client.get("/api/missions/plan", params={"order_id": order_id, "drone_id": drone_id})


def confirm(client: TestClient, order_id: str = ORDER, drone_id: str = DRONE) -> Any:
    return client.post("/api/missions", json={"order_id": order_id, "drone_id": drone_id})


def snapshot(client: TestClient) -> dict[str, Any]:
    """Everything the mission feature must never change."""
    return {
        "orders": client.get("/api/orders").json(),
        "drones": client.get("/api/drones").json(),
        "hubs": client.get("/api/hubs").json(),
    }


def same_mission(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Equal apart from the time-zone suffix (SQLite drops it on read, PostgreSQL keeps it)."""
    keys = a.keys() - {"created_at", "updated_at"}
    return (
        a.keys() == b.keys()
        and all(a[k] == b[k] for k in keys)
        and all(a[t].rstrip("Z") == b[t].rstrip("Z") for t in ("created_at", "updated_at"))
    )


def occupancy(plan: dict[str, Any]) -> dict[str, int]:
    return {h["hub_id"]: h["docked_drones"] for h in plan["hub_occupancy"]}


# --- preview -------------------------------------------------------------------------------------


def test_preview_returns_a_plan_and_changes_nothing(client: TestClient, seeded: Session) -> None:
    before = snapshot(client)

    response = preview(client)

    assert response.status_code == 200
    plan = response.json()
    assert plan["eligible"] is True
    assert plan["reasons"] == []
    assert plan["route"]["origin_hub_id"] == "hub-galeria-baltycka"
    assert plan["route"]["return_hub_id"] == "hub-galeria-baltycka"  # nearest Hub to the address
    assert plan["route"]["total_km"] > 0
    assert plan["energy"]["required_battery_pct"] < plan["energy"]["drone_battery_pct"]
    assert plan["distance_budget_km"] == 14.0
    assert occupancy(plan) == {
        "hub-centrum-handlowe-osowa": 3,
        "hub-centrum-riviera": 3,
        "hub-forum-gdansk": 3,
        "hub-galeria-baltycka": 3,
    }
    assert client.get("/api/missions").json() == []
    assert snapshot(client) == before
    assert preview(client).json() == plan  # deterministic


def test_preview_explains_why_a_pair_is_not_possible(client: TestClient, seeded: Session) -> None:
    plan = preview(client, ORDER, "DRN-001").json()  # DRN-001 is docked at Osowa

    assert plan["eligible"] is False
    assert [r["code"] for r in plan["reasons"]] == ["DRONE_NOT_AT_ORIGIN_HUB"]
    assert client.get("/api/missions").json() == []


def test_preview_of_unknown_ids_is_404_and_missing_parameters_are_422(
    client: TestClient, seeded: Session
) -> None:
    assert preview(client, "ORD-999").status_code == 404
    assert preview(client, ORDER, "DRN-999").status_code == 404
    assert client.get("/api/missions/plan", params={"order_id": ORDER}).status_code == 422
    assert client.get("/api/missions/plan").status_code == 422


def test_in_flight_drones_and_assignments_do_not_change_physical_occupancy(
    client: TestClient, seeded: Session
) -> None:
    drone = seeded.get(Drone, "DRN-007")  # docked at Forum Gdańsk
    assert drone is not None
    drone.status = DroneStatus.IN_FLIGHT.value
    seeded.commit()

    plan = preview(client).json()

    assert occupancy(plan)["hub-forum-gdansk"] == 2  # the flying drone counts at no Hub
    assert sum(occupancy(plan).values()) == 11


def test_a_full_nearest_hub_is_excluded_from_return_hub_selection(
    client: TestClient, seeded: Session, make_order: OrderFactory
) -> None:
    # From Galeria Bałtycka to a point beside Forum Gdańsk, whose Hub is nearest but now full.
    seeded.add(
        make_order(
            id="ORD-950",
            origin_hub_id="hub-galeria-baltycka",
            destination_longitude=18.6420,
            destination_latitude=54.3500,
            package_weight_kg=1.0,
        )
    )
    forum = seeded.get(Hub, "hub-forum-gdansk")
    assert forum is not None
    forum.drone_capacity = 3  # DRN-007..009 already fill it
    seeded.commit()

    plan = preview(client, "ORD-950", "DRN-010").json()

    assert plan["eligible"] is True
    assert plan["route"]["return_hub_id"] == "hub-galeria-baltycka"
    assert plan["skipped_return_hubs"] == [{"hub_id": "hub-forum-gdansk", "reason": "HUB_FULL"}]


# --- confirmation --------------------------------------------------------------------------------


def test_confirming_creates_one_active_mission_and_changes_no_physical_state(
    client: TestClient, seeded: Session
) -> None:
    before = snapshot(client)
    plan = preview(client).json()

    response = confirm(client)

    assert response.status_code == 201
    mission = response.json()
    assert re.fullmatch(r"MIS-[0-9A-F]{8}", mission["id"])
    assert mission["status"] == "ASSIGNED"
    assert (mission["order_id"], mission["drone_id"]) == (ORDER, DRONE)
    assert mission["origin_hub_id"] == plan["route"]["origin_hub_id"]
    assert mission["return_hub_id"] == plan["route"]["return_hub_id"]
    assert mission["total_km"] == plan["route"]["total_km"]
    assert mission["expected_energy_pct"] == plan["energy"]["expected_pct"]
    assert mission["worst_case_energy_pct"] == plan["energy"]["worst_case_pct"]
    reread = client.get(f"/api/missions/{mission['id']}").json()
    assert same_mission(reread, mission)
    assert [m["id"] for m in client.get("/api/missions").json()] == [mission["id"]]
    # No flight, no movement, no battery drain, no order status change, no reservation.
    assert snapshot(client) == before
    assert occupancy(preview(client, "ORD-002", "DRN-011").json()) == occupancy(plan)


def test_an_assigned_order_or_drone_cannot_be_assigned_again(
    client: TestClient, seeded: Session
) -> None:
    assert confirm(client).status_code == 201

    same_order = confirm(client, ORDER, "DRN-011")
    same_drone = confirm(client, "ORD-002", DRONE)

    for response, code in (
        (same_order, "ORDER_ALREADY_ASSIGNED"),
        (same_drone, "DRONE_ALREADY_ASSIGNED"),
    ):
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "MISSION_NOT_ELIGIBLE"
        assert code in [r["code"] for r in detail["plan"]["reasons"]]
    assert len(client.get("/api/missions").json()) == 1
    assert [r["code"] for r in preview(client).json()["reasons"]] == [
        "ORDER_ALREADY_ASSIGNED",
        "DRONE_ALREADY_ASSIGNED",
    ]


def test_an_ineligible_confirmation_is_rejected_with_reasons_and_changes_nothing(
    client: TestClient, seeded: Session
) -> None:
    before = snapshot(client)

    response = confirm(client, ORDER, "DRN-001")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "MISSION_NOT_ELIGIBLE"
    assert detail["plan"]["eligible"] is False
    assert client.get("/api/missions").json() == []
    assert snapshot(client) == before


def test_confirmation_revalidates_instead_of_trusting_an_earlier_preview(
    client: TestClient, seeded: Session
) -> None:
    assert preview(client).json()["eligible"] is True
    drone = seeded.get(Drone, DRONE)
    assert drone is not None
    drone.status = DroneStatus.CHARGING.value  # changes between preview and confirm
    seeded.commit()

    response = confirm(client)

    assert response.status_code == 409
    assert "DRONE_NOT_AVAILABLE" in [
        r["code"] for r in response.json()["detail"]["plan"]["reasons"]
    ]
    assert client.get("/api/missions").json() == []


def test_an_order_that_is_not_ready_cannot_be_assigned(client: TestClient, seeded: Session) -> None:
    order = seeded.get(DeliveryOrder, ORDER)
    assert order is not None
    order.status = "AWAITING_HANDOVER"
    seeded.commit()

    response = confirm(client)

    assert response.status_code == 409
    assert [r["code"] for r in response.json()["detail"]["plan"]["reasons"]] == ["ORDER_NOT_READY"]


def test_confirming_unknown_ids_is_404_and_a_malformed_body_is_422(
    client: TestClient, seeded: Session
) -> None:
    assert confirm(client, "ORD-999").status_code == 404
    assert confirm(client, ORDER, "DRN-999").status_code == 404
    assert client.post("/api/missions", json={"order_id": ORDER}).status_code == 422
    assert client.post("/api/missions", json={}).status_code == 422
    assert client.get("/api/missions").json() == []


# --- reads ---------------------------------------------------------------------------------------


def test_list_is_empty_before_any_mission_and_an_unknown_id_is_404(
    client: TestClient, seeded: Session
) -> None:
    assert client.get("/api/missions").json() == []
    assert client.get("/api/missions/MIS-00000000").status_code == 404


def test_missions_are_listed_in_a_stable_order(client: TestClient, seeded: Session) -> None:
    first = confirm(client, "ORD-001", "DRN-010").json()
    second = confirm(client, "ORD-002", "DRN-011").json()

    listed = client.get("/api/missions").json()

    assert [m["id"] for m in listed] == [first["id"], second["id"]]
    assert client.get("/api/missions").json() == listed


# --- cancellation --------------------------------------------------------------------------------


def test_cancelling_an_assigned_mission_releases_the_order_and_the_drone(
    client: TestClient, seeded: Session
) -> None:
    mission = confirm(client).json()
    before = snapshot(client)
    occupied = occupancy(preview(client, "ORD-002", "DRN-011").json())

    response = client.post(f"/api/missions/{mission['id']}/cancel")

    assert response.status_code == 200
    cancelled = response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["id"] == mission["id"]
    assert client.get(f"/api/missions/{mission['id']}").json()["status"] == "CANCELLED"
    assert snapshot(client) == before  # cancelling changes nothing physical
    assert occupancy(preview(client).json()) == occupied  # and no occupancy
    assert preview(client).json()["eligible"] is True  # both are free again
    assert confirm(client).status_code == 201  # and can be reassigned
    statuses = [m["status"] for m in client.get("/api/missions").json()]
    assert statuses == ["CANCELLED", "ASSIGNED"]


def test_a_cancelled_mission_cannot_be_cancelled_again(client: TestClient, seeded: Session) -> None:
    mission = confirm(client).json()
    assert client.post(f"/api/missions/{mission['id']}/cancel").status_code == 200

    response = client.post(f"/api/missions/{mission['id']}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MISSION_NOT_CANCELLABLE"
    assert response.json()["detail"]["status"] == "CANCELLED"


def test_a_mission_in_flight_cannot_be_cancelled(client: TestClient, seeded: Session) -> None:
    mission = confirm(client).json()
    row = seeded.get(Mission, mission["id"])
    assert row is not None
    row.status = MissionStatus.IN_FLIGHT.value  # Feature 010 will do this; 009 never does
    seeded.commit()

    response = client.post(f"/api/missions/{mission['id']}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "IN_FLIGHT"
    assert client.get(f"/api/missions/{mission['id']}").json()["status"] == "IN_FLIGHT"
    # An in-flight mission still claims its order and drone.
    assert "ORDER_ALREADY_ASSIGNED" in [r["code"] for r in preview(client).json()["reasons"]]


def test_cancelling_an_unknown_mission_is_404(client: TestClient, seeded: Session) -> None:
    assert client.post("/api/missions/MIS-00000000/cancel").status_code == 404


def test_existing_apis_are_unchanged(client: TestClient, seeded: Session) -> None:
    assert len(client.get("/api/hubs").json()) == 4
    assert len(client.get("/api/drones").json()) == 12
    assert len(client.get("/api/orders").json()) == 10
    assert set(client.get("/api/orders").json()[0]) == {
        "id",
        "origin_hub_id",
        "destination_address",
        "destination_longitude",
        "destination_latitude",
        "package_weight_kg",
        "status",
        "created_at",
        "updated_at",
    }


def test_the_plan_reports_full_return_hubs_when_the_only_reachable_one_is_full(
    client: TestClient, seeded: Session, make_order: OrderFactory
) -> None:
    # From Osowa to a point beside Centrum Riviera (about 9 km): Riviera is the only Hub in reach.
    seeded.add(
        make_order(
            id="ORD-951",
            origin_hub_id="hub-centrum-handlowe-osowa",
            destination_longitude=18.5330,
            destination_latitude=54.5050,
            package_weight_kg=1.0,
        )
    )
    riviera = seeded.get(Hub, "hub-centrum-riviera")
    assert riviera is not None
    riviera.drone_capacity = 3  # DRN-004..006 already fill it
    seeded.commit()

    plan = preview(client, "ORD-951", "DRN-001").json()
    rejected = confirm(client, "ORD-951", "DRN-001")

    assert plan["eligible"] is False
    assert [r["code"] for r in plan["reasons"]] == ["RETURN_HUBS_FULL"]
    assert plan["route"]["return_hub_id"] is None
    skipped = {s["hub_id"]: s["reason"] for s in plan["skipped_return_hubs"]}
    assert skipped["hub-centrum-riviera"] == "HUB_FULL"
    assert "OUT_OF_RANGE" in skipped.values()
    assert rejected.status_code == 409
    assert client.get("/api/missions").json() == []


def test_a_confirmation_with_an_empty_id_is_422_like_the_preview(
    client: TestClient, seeded: Session
) -> None:
    assert client.post("/api/missions", json={"order_id": "", "drone_id": DRONE}).status_code == 422
    assert client.post("/api/missions", json={"order_id": ORDER, "drone_id": ""}).status_code == 422
    assert preview(client, "", DRONE).status_code == 422


def test_an_active_mission_reserves_no_landing_capacity_at_its_return_hub(
    client: TestClient, seeded: Session, make_order: OrderFactory
) -> None:
    # Two parcels from Galeria Bałtycka to the same spot beside Forum Gdańsk. Forum has one free
    # place (4 places, 3 docked). A confirmed mission returning there must not take that place.
    for order_id in ("ORD-950", "ORD-951"):
        seeded.add(
            make_order(
                id=order_id,
                origin_hub_id="hub-galeria-baltycka",
                destination_longitude=18.6420,
                destination_latitude=54.3500,
                package_weight_kg=1.0,
            )
        )
    forum = seeded.get(Hub, "hub-forum-gdansk")
    assert forum is not None
    forum.drone_capacity = 4
    seeded.commit()
    first_plan = preview(client, "ORD-950", "DRN-010").json()
    assert first_plan["route"]["return_hub_id"] == "hub-forum-gdansk"

    mission = confirm(client, "ORD-950", "DRN-010")

    assert mission.status_code == 201
    assert mission.json()["return_hub_id"] == "hub-forum-gdansk"
    second_plan = preview(client, "ORD-951", "DRN-011").json()
    assert second_plan["eligible"] is True
    assert second_plan["route"]["return_hub_id"] == "hub-forum-gdansk"  # still planned there
    assert second_plan["skipped_return_hubs"] == []
    assert occupancy(second_plan) == occupancy(first_plan)  # physical occupancy is unchanged
    assert occupancy(second_plan)["hub-forum-gdansk"] == 3
