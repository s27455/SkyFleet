"""Manual relocation over HTTP (Feature 019A) and the APIs that now meet an order-less mission."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone
from app.simulation import clock, engine
from app.simulation.heartbeat import record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
DRONE = "DRN-010"  # docked at Galeria Bałtycka, 100%
BALTYCKA, FORUM = "hub-galeria-baltycka", "hub-forum-gdansk"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)


@pytest.fixture
def api(client: TestClient, seeded: Session) -> TestClient:
    record_heartbeat(seeded, NOW)
    return client


def relocate(client: TestClient, destination: str = FORUM, drone: str = DRONE):  # type: ignore[no-untyped-def]
    return client.post(f"/api/drones/{drone}/relocate", json={"destination_hub_id": destination})


def test_the_plan_endpoint_is_read_only(api: TestClient) -> None:
    response = api.get(f"/api/drones/{DRONE}/relocation-plan", params={"destination_hub_id": FORUM})

    assert response.status_code == 200
    body = response.json()
    assert body["eligible"] is True and body["origin_hub_id"] == BALTYCKA
    assert body["destination_hub_id"] == FORUM and body["distance_km"] > 0
    assert any("not reserved" in warning for warning in body["warnings"])
    assert api.get("/api/missions").json() == []


def test_the_plan_explains_why_a_relocation_is_not_possible(api: TestClient) -> None:
    body = api.get(
        f"/api/drones/{DRONE}/relocation-plan", params={"destination_hub_id": BALTYCKA}
    ).json()

    assert body["eligible"] is False
    assert [reason["code"] for reason in body["reasons"]] == ["SAME_HUB"]


def test_the_plan_warns_when_orders_are_waiting_at_the_source_hub(api: TestClient) -> None:
    body = api.get(
        f"/api/drones/{DRONE}/relocation-plan", params={"destination_hub_id": FORUM}
    ).json()

    assert any("waiting for pickup" in warning for warning in body["warnings"])  # ORD-001..003


def test_unknown_drone_and_hub_are_404_with_codes(api: TestClient) -> None:
    missing_drone = relocate(api, drone="DRN-999")
    missing_hub = relocate(api, destination="hub-nowhere")

    assert (missing_drone.status_code, missing_drone.json()["detail"]["code"]) == (
        404,
        "DRONE_NOT_FOUND",
    )
    assert (missing_hub.status_code, missing_hub.json()["detail"]["code"]) == (
        404,
        "HUB_NOT_FOUND",
    )
    assert (
        api.get(
            "/api/drones/DRN-999/relocation-plan", params={"destination_hub_id": FORUM}
        ).status_code
        == 404
    )


def test_relocating_starts_a_flight_that_the_read_apis_show_without_an_order(
    api: TestClient,
) -> None:
    response = relocate(api)

    assert response.status_code == 201
    body = response.json()
    assert (body["drone_id"], body["origin_hub_id"], body["destination_hub_id"]) == (
        DRONE,
        BALTYCKA,
        FORUM,
    )
    flights = api.get("/api/flights").json()["flights"]
    assert len(flights) == 1
    flight = flights[0]
    assert flight["mission_id"] == body["mission_id"] and flight["order_id"] is None
    assert flight["purpose"] == "RELOCATION" and flight["phase"] == "RELOCATING"
    assert flight["landing_target_hub_id"] == FORUM and flight["yielding_to_lpr"] is False
    missions = api.get("/api/missions").json()
    assert missions[0]["order_id"] is None and missions[0]["purpose"] == "RELOCATION"
    assert api.get(f"/api/missions/{body['mission_id']}").json()["order_id"] is None
    drone = api.get(f"/api/drones/{DRONE}").json()
    assert drone["status"] == "IN_FLIGHT" and drone["hub_id"] == BALTYCKA
    events = api.get("/api/events", params={"drone_id": DRONE}).json()
    assert [item["event_type"] for item in events] == ["DRONE_RELOCATION"]
    assert events[0]["order_id"] is None and events[0]["mission_id"] == body["mission_id"]


def test_the_delivery_apis_still_work_next_to_a_relocation(api: TestClient) -> None:
    relocate(api)
    mission = api.post("/api/missions", json={"order_id": "ORD-001", "drone_id": "DRN-011"})
    assert mission.status_code == 201
    assert api.post(f"/api/missions/{mission.json()['id']}/start").status_code == 200

    flights = api.get("/api/flights").json()["flights"]

    assert sorted(flight["purpose"] for flight in flights) == ["DELIVERY", "RELOCATION"]
    assert api.get("/api/dispatch/recommendations").status_code == 200
    assert api.get("/api/orders?active=true").status_code == 200


def test_an_ineligible_request_is_409_with_the_plan_and_creates_nothing(
    api: TestClient, seeded: Session
) -> None:
    assert relocate(api).status_code == 201

    again = relocate(api, destination="hub-centrum-handlowe-osowa")

    assert again.status_code == 409
    detail = again.json()["detail"]
    assert detail["code"] == "RELOCATION_NOT_ELIGIBLE"
    assert detail["plan"]["eligible"] is False and detail["plan"]["reasons"]
    assert len(api.get("/api/missions").json()) == 1


def test_without_the_worker_a_relocation_is_503_and_creates_nothing(
    client: TestClient, seeded: Session
) -> None:
    response = relocate(client)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    assert client.get("/api/missions").json() == []
    drone = seeded.scalars(select(Drone).where(Drone.id == DRONE)).one()
    assert drone.status == "IDLE"


def test_the_flight_lands_through_the_worker_and_the_drone_changes_hub(
    api: TestClient, session_factory: sessionmaker[Session], sim_settings: Settings
) -> None:
    mission_id = relocate(api).json()["mission_id"]

    engine.advance_flight(session_factory, sim_settings, mission_id, NOW + timedelta(seconds=120))

    drone = api.get(f"/api/drones/{DRONE}").json()
    assert (drone["status"], drone["hub_id"]) == ("IDLE", FORUM)
    assert api.get("/api/missions").json()[0]["status"] == "COMPLETED"
    events = api.get("/api/events", params={"drone_id": DRONE}).json()
    assert [item["details"]["phase"] for item in events] == ["STARTED", "COMPLETED"]
