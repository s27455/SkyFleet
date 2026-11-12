"""Administrative drone management API (feature 011)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.models import Mission, MissionStatus

FORUM = "hub-forum-gdansk"
OSOWA = "hub-centrum-handlowe-osowa"


def _fill_hub(session: Session, hub_id: str, make_drone: Callable[..., Drone]) -> None:
    """Dock extra IDLE drones at the Hub until it holds its full capacity."""
    hub = session.get(Hub, hub_id)
    assert hub is not None
    docked = len(
        [
            d
            for d in session.scalars(select(Drone))
            if d.hub_id == hub_id and d.status == DroneStatus.IDLE.value
        ]
    )
    for n in range(hub.drone_capacity - docked):
        session.add(
            make_drone(
                id=f"DRN-{500 + n}",
                hub_id=hub_id,
                longitude=hub.longitude,
                latitude=hub.latitude,
            )
        )
    session.commit()


def _mission(seeded: Session, drone_id: str = "DRN-007") -> Mission:
    return missions_service.confirm_mission(seeded, "ORD-004", drone_id, Settings())


# --- create -----------------------------------------------------------------------------------


def test_create_drone_is_visible_in_reads(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/drones", json={"id": "DRN-100", "hub_id": FORUM})

    assert response.status_code == 201
    body = response.json()
    assert (body["id"], body["hub_id"], body["status"], body["battery_pct"]) == (
        "DRN-100",
        FORUM,
        "IDLE",
        100,
    )
    assert body["model"]["id"] == "SF-1"
    hub = seeded.get(Hub, FORUM)
    assert hub is not None
    assert (body["longitude"], body["latitude"]) == (hub.longitude, hub.latitude)
    assert client.get("/api/drones/DRN-100").json() == body
    assert "DRN-100" in [d["id"] for d in client.get("/api/drones").json()]


def test_create_drone_with_battery(client: TestClient, seeded: Session) -> None:
    response = client.post(
        "/api/drones", json={"id": "DRN-101", "hub_id": FORUM, "battery_pct": 42}
    )

    assert response.status_code == 201
    assert response.json()["battery_pct"] == 42


def test_create_rejects_duplicate_id(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/drones", json={"id": "DRN-001", "hub_id": FORUM})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DRONE_ALREADY_EXISTS"


def test_create_rejects_unknown_hub(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/drones", json={"id": "DRN-100", "hub_id": "hub-nowhere"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "HUB_NOT_FOUND"


def test_create_rejects_invalid_values(client: TestClient, seeded: Session) -> None:
    for payload in (
        {"id": "DRN-100", "hub_id": FORUM, "battery_pct": 101},
        {"id": "DRN-100", "hub_id": FORUM, "battery_pct": -1},
        {"id": "bad id", "hub_id": FORUM},
        {"id": "DRN-100", "hub_id": FORUM, "status": "IN_FLIGHT"},
        {"id": "DRN-100", "hub_id": FORUM, "longitude": 18.0},
        {"hub_id": FORUM},
    ):
        assert client.post("/api/drones", json=payload).status_code == 422, payload
    assert client.get("/api/drones/DRN-100").status_code == 404


def test_create_rejects_full_hub(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    _fill_hub(seeded, FORUM, make_drone)

    response = client.post("/api/drones", json={"id": "DRN-100", "hub_id": FORUM})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HUB_FULL"
    assert client.post("/api/drones", json={"id": "DRN-100", "hub_id": OSOWA}).status_code == 201


# --- update -----------------------------------------------------------------------------------


def test_patch_unknown_drone_is_404(client: TestClient, seeded: Session) -> None:
    response = client.patch("/api/drones/DRN-999", json={"battery_pct": 50})

    assert response.status_code == 404


def test_patch_rejects_non_whitelisted_fields(client: TestClient, seeded: Session) -> None:
    for payload in (
        {"longitude": 18.0},
        {"model_id": "SF-2"},
        {"status": "IN_FLIGHT"},
        {"status": "CHARGING"},
        {"battery_pct": 101},
        {"id": "DRN-777"},
    ):
        assert client.patch("/api/drones/DRN-001", json=payload).status_code == 422, payload


def test_patch_battery(client: TestClient, seeded: Session) -> None:
    response = client.patch("/api/drones/DRN-001", json={"battery_pct": 55})

    assert response.status_code == 200
    assert response.json()["battery_pct"] == 55
    assert client.get("/api/drones/DRN-001").json()["battery_pct"] == 55


def test_idle_to_maintenance_and_back(client: TestClient, seeded: Session) -> None:
    out = client.patch("/api/drones/DRN-001", json={"status": "MAINTENANCE"})
    back = client.patch("/api/drones/DRN-001", json={"status": "IDLE"})

    assert out.status_code == 200 and out.json()["status"] == "MAINTENANCE"
    assert back.status_code == 200 and back.json()["status"] == "IDLE"


def test_return_to_idle_is_rejected_when_hub_filled_meanwhile(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    assert client.patch("/api/drones/DRN-007", json={"status": "MAINTENANCE"}).status_code == 200
    _fill_hub(seeded, FORUM, make_drone)  # fills the place the maintenance drone vacated

    response = client.patch("/api/drones/DRN-007", json={"status": "IDLE"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HUB_FULL"
    assert client.get("/api/drones/DRN-007").json()["status"] == "MAINTENANCE"


def test_cannot_set_idle_when_not_at_a_hub(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    seeded.add(
        make_drone(
            id="DRN-800", status=DroneStatus.MAINTENANCE.value, longitude=18.7, latitude=54.5
        )
    )
    seeded.commit()

    response = client.patch("/api/drones/DRN-800", json={"status": "IDLE"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_CHANGE"


def test_reassign_idle_docked_drone_moves_it_to_the_new_hub(
    client: TestClient, seeded: Session
) -> None:
    target = seeded.get(Hub, OSOWA)
    assert target is not None

    response = client.patch("/api/drones/DRN-007", json={"hub_id": OSOWA})

    assert response.status_code == 200
    body = response.json()
    assert body["hub_id"] == OSOWA
    assert (body["longitude"], body["latitude"]) == (target.longitude, target.latitude)


def test_reassign_unknown_hub_is_404(client: TestClient, seeded: Session) -> None:
    response = client.patch("/api/drones/DRN-007", json={"hub_id": "hub-nowhere"})

    assert response.status_code == 404
    assert client.get("/api/drones/DRN-007").json()["hub_id"] == FORUM


def test_reassign_to_full_hub_is_rejected(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    _fill_hub(seeded, OSOWA, make_drone)

    response = client.patch("/api/drones/DRN-007", json={"hub_id": OSOWA})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "HUB_FULL"
    assert client.get("/api/drones/DRN-007").json()["hub_id"] == FORUM


def test_reassign_maintenance_drone_is_rejected(client: TestClient, seeded: Session) -> None:
    client.patch("/api/drones/DRN-007", json={"status": "MAINTENANCE"})

    response = client.patch("/api/drones/DRN-007", json={"hub_id": OSOWA})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_CHANGE"


def test_active_mission_blocks_every_update(client: TestClient, seeded: Session) -> None:
    _mission(seeded)

    for payload in ({"battery_pct": 50}, {"status": "MAINTENANCE"}, {"hub_id": OSOWA}):
        response = client.patch("/api/drones/DRN-007", json=payload)
        assert response.status_code == 409, payload
        assert response.json()["detail"]["code"] == "DRONE_BUSY"


def test_in_flight_drone_cannot_be_updated(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    seeded.add(make_drone(id="DRN-801", status=DroneStatus.IN_FLIGHT.value))
    seeded.commit()

    response = client.patch("/api/drones/DRN-801", json={"battery_pct": 50})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DRONE_BUSY"


# --- delete -----------------------------------------------------------------------------------


def test_delete_drone_without_dependencies(client: TestClient, seeded: Session) -> None:
    response = client.delete("/api/drones/DRN-001")

    assert response.status_code == 204
    assert client.get("/api/drones/DRN-001").status_code == 404
    assert "DRN-001" not in [d["id"] for d in client.get("/api/drones").json()]


def test_delete_unknown_drone_is_404(client: TestClient, seeded: Session) -> None:
    assert client.delete("/api/drones/DRN-999").status_code == 404


def test_delete_rejects_drone_with_active_mission(client: TestClient, seeded: Session) -> None:
    mission = _mission(seeded)

    response = client.delete("/api/drones/DRN-007")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DRONE_BUSY"
    assert seeded.get(Mission, mission.id) is not None


def test_delete_rejects_drone_with_mission_history(client: TestClient, seeded: Session) -> None:
    mission = _mission(seeded)
    missions_service.cancel_mission(seeded, mission.id)

    response = client.delete("/api/drones/DRN-007")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DRONE_HAS_HISTORY"
    kept = seeded.get(Mission, mission.id)
    assert kept is not None and kept.status == MissionStatus.CANCELLED.value
    assert client.get("/api/drones/DRN-007").status_code == 200


def test_delete_rejects_in_flight_drone(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    seeded.add(make_drone(id="DRN-801", status=DroneStatus.IN_FLIGHT.value))
    seeded.commit()

    assert client.delete("/api/drones/DRN-801").status_code == 409


# --- review follow-ups ------------------------------------------------------------------------


def test_battery_edit_works_for_idle_drone_outside_a_hub(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    seeded.add(make_drone(id="DRN-802", longitude=18.7, latitude=54.5))
    seeded.commit()

    response = client.patch("/api/drones/DRN-802", json={"battery_pct": 50})

    assert response.status_code == 200
    assert response.json()["battery_pct"] == 50


def test_charging_drone_cannot_be_updated_or_deleted(
    client: TestClient, seeded: Session, make_drone: Callable[..., Drone]
) -> None:
    seeded.add(make_drone(id="DRN-803", status=DroneStatus.CHARGING.value))
    seeded.commit()

    assert client.patch("/api/drones/DRN-803", json={"battery_pct": 50}).status_code == 409
    assert client.delete("/api/drones/DRN-803").status_code == 409
