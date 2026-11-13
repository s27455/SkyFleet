from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.drones.seed import seed_drones
from app.hubs.seed import seed_hubs


def test_list_drones_is_empty_before_seeding(client: TestClient) -> None:
    response = client.get("/api/drones")

    assert response.status_code == 200
    assert response.json() == []


def test_list_drones_returns_the_fleet_in_stable_order(
    client: TestClient, session: Session
) -> None:
    seed_hubs(session)
    seed_drones(session)

    response = client.get("/api/drones")

    assert response.status_code == 200
    drones = response.json()
    assert [d["id"] for d in drones] == [f"DRN-{n:03d}" for n in range(1, 13)]
    assert client.get("/api/drones").json() == drones


def test_drone_detail_includes_state_hub_and_nested_model(
    client: TestClient, session: Session
) -> None:
    seed_hubs(session)
    seed_drones(session)

    response = client.get("/api/drones/DRN-001")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "DRN-001"
    assert body["hub_id"] == "hub-centrum-handlowe-osowa"
    assert body["status"] == "IDLE"
    assert body["battery_pct"] == 100
    assert (body["longitude"], body["latitude"]) == (18.49097, 54.42569)
    assert body["model"] == {
        "id": "SF-1",
        "name": "SkyFleet SF-1 Courier",
        "airframe_type": "quadcopter",
        "max_payload_kg": 3.0,
        "max_range_km": 20.0,
        "recommended_mission_range_km": 14.0,
        "cruise_speed_kmh": 45.0,
        "max_speed_kmh": 60.0,
        "nominal_flight_time_min": 32,
        "min_battery_reserve_pct": 20,
        "charge_to_80_minutes": 45,
        "max_wind_mps": 10.0,
        "empty_weight_kg": 9.0,
    }


def test_unknown_drone_returns_404_with_message(client: TestClient, session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)

    response = client.get("/api/drones/DRN-999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Drone 'DRN-999' not found"}


def test_hub_endpoints_are_unaffected(client: TestClient, session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)

    hubs = client.get("/api/hubs").json()

    assert len(hubs) == 4
    assert set(hubs[0]) == {"id", "name", "address", "longitude", "latitude", "drone_capacity"}
    assert client.get("/api/hubs/hub-forum-gdansk").status_code == 200
