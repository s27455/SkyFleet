"""Starting a mission and reading flights over HTTP, with a controlled clock."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone
from app.hubs.models import Hub
from app.missions.presence import hub_occupancy
from app.orders.models import DeliveryOrder
from app.simulation import clock, engine
from app.simulation.heartbeat import record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
ORDER, DRONE = "ORD-001", "DRN-010"
BALTYCKA = "hub-galeria-baltycka"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)


def assign(client: TestClient, order: str = ORDER, drone: str = DRONE) -> str:
    response = client.post("/api/missions", json={"order_id": order, "drone_id": drone})
    assert response.status_code == 201
    mission_id: str = response.json()["id"]
    return mission_id


def beat(session: Session, seconds_ago: float = 0.0) -> None:
    record_heartbeat(session, NOW - timedelta(seconds=seconds_ago))


def start(client: TestClient, mission_id: str) -> Any:
    return client.post(f"/api/missions/{mission_id}/start")


def run(
    factory: sessionmaker[Session], settings: Settings, mission_id: str, seconds: float
) -> None:
    engine.advance_flight(factory, settings, mission_id, NOW + timedelta(seconds=seconds))


def snapshot(client: TestClient) -> dict[str, Any]:
    return {name: client.get(f"/api/{name}").json() for name in ("orders", "drones", "hubs")}


# --- the worker heartbeat -------------------------------------------------------------------------


def test_starting_without_a_worker_heartbeat_is_refused_with_a_clear_error(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    before = snapshot(client)

    response = start(client, mission_id)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    assert "worker" in detail["message"] and "app.worker" in detail["message"]
    assert detail["last_heartbeat_at"] is None
    assert detail["max_age_seconds"] == 10
    assert client.get(f"/api/missions/{mission_id}").json()["status"] == "ASSIGNED"
    assert snapshot(client) == before


def test_a_stale_heartbeat_is_refused_and_a_recent_one_is_accepted(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    beat(seeded, seconds_ago=11)

    stale = start(client, mission_id)

    assert stale.status_code == 503
    assert stale.json()["detail"]["last_heartbeat_at"].startswith("2026-11-12T09:59:49")
    beat(seeded, seconds_ago=9)
    assert start(client, mission_id).status_code == 200


# --- start ----------------------------------------------------------------------------------------


def test_start_takes_off_and_changes_the_mission_drone_and_order(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    beat(seeded)

    response = start(client, mission_id)

    assert response.status_code == 200
    assert response.json()["status"] == "IN_FLIGHT"
    assert client.get(f"/api/missions/{mission_id}").json()["status"] == "IN_FLIGHT"
    orders = {o["id"]: o for o in client.get("/api/orders").json()}
    drones = {d["id"]: d for d in client.get("/api/drones").json()}
    assert orders[ORDER]["status"] == "OUT_FOR_DELIVERY"
    assert drones[DRONE]["status"] == "IN_FLIGHT"
    assert len(client.get("/api/hubs").json()) == 4  # the Hubs API is unchanged


def test_a_mission_starts_exactly_once(client: TestClient, seeded: Session) -> None:
    mission_id = assign(client)
    beat(seeded)
    assert start(client, mission_id).status_code == 200

    again = start(client, mission_id)

    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "MISSION_NOT_STARTABLE"
    assert again.json()["detail"]["status"] == "IN_FLIGHT"
    assert len(client.get("/api/flights").json()["flights"]) == 1


def test_a_cancelled_or_unknown_mission_cannot_start(client: TestClient, seeded: Session) -> None:
    mission_id = assign(client)
    assert client.post(f"/api/missions/{mission_id}/cancel").status_code == 200
    beat(seeded)

    cancelled = start(client, mission_id)

    assert cancelled.status_code == 409
    assert cancelled.json()["detail"]["status"] == "CANCELLED"
    assert start(client, "MIS-00000000").status_code == 404


def test_start_rechecks_the_actual_state_and_changes_nothing_when_refused(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    beat(seeded)
    seeded.execute(update(Drone).where(Drone.id == DRONE).values(battery_pct=10))  # drained since
    seeded.commit()
    before = snapshot(client)

    response = start(client, mission_id)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "MISSION_NOT_ELIGIBLE"
    assert "INSUFFICIENT_BATTERY" in [r["code"] for r in detail["plan"]["reasons"]]
    assert client.get(f"/api/missions/{mission_id}").json()["status"] == "ASSIGNED"
    assert snapshot(client) == before


def test_an_order_that_is_no_longer_ready_blocks_the_start(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    beat(seeded)
    seeded.execute(
        update(DeliveryOrder).where(DeliveryOrder.id == ORDER).values(status="AWAITING_HANDOVER")
    )
    seeded.commit()

    response = start(client, mission_id)

    assert response.status_code == 409
    assert "ORDER_NOT_READY" in [r["code"] for r in response.json()["detail"]["plan"]["reasons"]]


def test_cancellation_is_refused_once_the_mission_has_started(
    client: TestClient, seeded: Session
) -> None:
    mission_id = assign(client)
    beat(seeded)
    assert start(client, mission_id).status_code == 200

    response = client.post(f"/api/missions/{mission_id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "IN_FLIGHT"


# --- flights endpoint -----------------------------------------------------------------------------


def test_flights_are_empty_and_the_worker_stale_before_anything_runs(
    client: TestClient, seeded: Session
) -> None:
    body = client.get("/api/flights").json()

    assert body["flights"] == []
    assert body["worker_heartbeat_at"] is None
    assert body["worker_stale"] is True
    assert body["server_time"].startswith("2026-11-12T10:00:00")


def test_an_active_flight_reports_phase_progress_position_battery_and_target(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
) -> None:
    mission_id = assign(client)
    beat(seeded)
    start(client, mission_id)
    run(session_factory, sim_settings, mission_id, 8.0)

    body = client.get("/api/flights").json()

    assert body["worker_stale"] is False
    (flight,) = body["flights"]
    assert flight["mission_id"] == mission_id
    assert (flight["order_id"], flight["drone_id"]) == (ORDER, DRONE)
    assert flight["mission_status"] == "IN_FLIGHT"
    assert flight["phase"] == "OUTBOUND"
    assert 0 < flight["progress"] < 0.5
    assert len(flight["position"]) == 2
    assert flight["battery_pct"] == round(flight["battery_exact_pct"]) < 100
    assert flight["target"]["eta_s"] > 0 and len(flight["target"]["position"]) == 2
    assert flight["origin_hub_id"] == flight["planned_return_hub_id"] == BALTYCKA
    assert flight["landing_target_hub_id"] == BALTYCKA
    assert flight["delivered_at"] is None and flight["emergency"] is None
    assert flight["started_at"].startswith("2026-11-12T10:00:00")


def test_the_worker_going_stale_after_a_start_is_visible_to_the_frontend(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_id = assign(client)
    beat(seeded)
    start(client, mission_id)
    run(session_factory, sim_settings, mission_id, 5.0)
    monkeypatch.setattr(clock, "utcnow", lambda: NOW + timedelta(seconds=60))

    body = client.get("/api/flights").json()

    assert body["worker_stale"] is True  # the flight is listed, but no longer being updated
    assert len(body["flights"]) == 1
    assert body["flights"][0]["updated_at"].startswith("2026-11-12T10:00:05")


def test_delivery_and_landing_show_through_the_existing_endpoints(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
) -> None:
    mission_id = assign(client)
    beat(seeded)
    start(client, mission_id)

    run(session_factory, sim_settings, mission_id, 21.0)
    flight = client.get("/api/flights").json()["flights"][0]
    orders = {o["id"]: o for o in client.get("/api/orders").json()}
    assert flight["phase"] == "RETURNING" and flight["delivered_at"] is not None
    assert orders[ORDER]["status"] == "DELIVERED"
    assert client.get(f"/api/missions/{mission_id}").json()["status"] == "IN_FLIGHT"

    run(session_factory, sim_settings, mission_id, 60.0)
    assert client.get("/api/flights").json()["flights"] == []  # landed flights are not listed
    assert client.get(f"/api/missions/{mission_id}").json()["status"] == "COMPLETED"
    drones = {d["id"]: d for d in client.get("/api/drones").json()}
    assert drones[DRONE]["status"] == "IDLE"
    assert drones[DRONE]["battery_pct"] == 93


def test_an_emergency_flight_stays_listed_with_its_reason(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
) -> None:
    mission_id = assign(client)
    beat(seeded)
    start(client, mission_id)
    drones = seeded.scalars(select(Drone)).all()
    counts = hub_occupancy(drones, seeded.scalars(select(Hub)).all(), 50)
    for hub_id, count in counts.items():
        capacity = 2 if hub_id == BALTYCKA else count  # Bałtycka: DRN-011 and DRN-012 fill it
        seeded.execute(update(Hub).where(Hub.id == hub_id).values(drone_capacity=capacity))
    seeded.commit()

    run(session_factory, sim_settings, mission_id, 100.0)

    (flight,) = client.get("/api/flights").json()["flights"]
    assert flight["phase"] == "EMERGENCY"
    assert flight["mission_status"] == "EMERGENCY"
    assert flight["emergency"]["reason"] == "NO_HUB_WITH_CAPACITY"
    assert flight["emergency"]["position"] == flight["position"]
    assert flight["target"] is None
    drones_by_id = {d["id"]: d for d in client.get("/api/drones").json()}
    assert drones_by_id[DRONE]["status"] == "MAINTENANCE"
    orders = {o["id"]: o for o in client.get("/api/orders").json()}
    assert orders[ORDER]["status"] == "DELIVERED"


def test_an_unknown_or_started_mission_is_reported_as_such_even_without_a_worker(
    client: TestClient, seeded: Session
) -> None:
    unknown = start(client, "MIS-00000000")  # no heartbeat has ever been recorded
    assert unknown.status_code == 404

    mission_id = assign(client)
    assert client.post(f"/api/missions/{mission_id}/cancel").status_code == 200
    cancelled = start(client, mission_id)

    assert cancelled.status_code == 409
    assert cancelled.json()["detail"]["code"] == "MISSION_NOT_STARTABLE"
