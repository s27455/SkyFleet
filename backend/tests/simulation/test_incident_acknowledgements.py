"""Acknowledging emergency alerts (Feature 022): idempotent, hides only the alert."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, Table, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone
from app.events.models import EventOrigin, OperationalEvent
from app.missions.models import Mission
from app.simulation import acknowledgements, engine
from app.simulation.acknowledgements import EmergencyNotFoundError
from app.simulation.failure import trigger_drone_failure
from app.simulation.models import IncidentAcknowledgement, MissionFlight

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def _emergency(
    session: Session,
    factory: sessionmaker[Session],
    settings: Settings,
    launch: Launch,
    order: str = "ORD-001",
    drone: str = "DRN-010",
) -> str:
    mission_id = launch(order, drone)
    trigger_drone_failure(session, at(8), settings, origin=EventOrigin.AUTOMATIC)
    engine.advance_flight(factory, settings, mission_id, at(300))
    session.expire_all()
    return mission_id


def _snapshot(session: Session) -> tuple[object, ...]:
    session.expire_all()
    missions = [(m.id, m.status) for m in session.scalars(select(Mission).order_by(Mission.id))]
    drones = [(d.id, d.status, d.hub_id) for d in session.scalars(select(Drone).order_by(Drone.id))]
    events = session.scalar(select(func.count()).select_from(OperationalEvent))
    flights = [
        (f.mission_id, f.phase, f.emergency_reason)
        for f in session.scalars(select(MissionFlight).order_by(MissionFlight.mission_id))
    ]
    return (missions, drones, events, flights)


def test_the_first_acknowledgement_is_stored_and_a_repeat_returns_the_same_time(
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    mission_id = _emergency(seeded, session_factory, sim_settings, launch)

    first = acknowledgements.acknowledge_emergency(seeded, mission_id, at(400))
    again = acknowledgements.acknowledge_emergency(seeded, mission_id, at(900))

    assert first == at(400) and again == first  # idempotent: the original time is kept
    assert seeded.scalar(select(func.count()).select_from(IncidentAcknowledgement)) == 1


def test_acknowledging_changes_nothing_else(
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    mission_id = _emergency(seeded, session_factory, sim_settings, launch)
    before = _snapshot(seeded)

    acknowledgements.acknowledge_emergency(seeded, mission_id, at(400))

    assert _snapshot(seeded) == before  # incident, events, mission, flight, drone: untouched


def test_only_the_acknowledged_alert_is_marked_and_a_later_incident_is_a_new_alert(
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    first = _emergency(seeded, session_factory, sim_settings, launch)
    second = launch("ORD-002", "DRN-011")
    trigger_drone_failure(seeded, at(8), sim_settings, origin=EventOrigin.AUTOMATIC)
    engine.advance_flight(session_factory, sim_settings, second, at(300))
    seeded.expire_all()

    acknowledgements.acknowledge_emergency(seeded, first, at(400))

    marked = acknowledgements.acknowledged_at_by_mission(seeded, [first, second])
    assert marked == {first: at(400)}  # the second alert (another mission) is still open
    assert acknowledgements.acknowledged_at_by_mission(seeded, []) == {}


def test_an_alert_that_does_not_exist_cannot_be_acknowledged(
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    flying = launch("ORD-001", "DRN-010")  # a normal flight: no emergency, so no alert
    with pytest.raises(EmergencyNotFoundError):
        acknowledgements.acknowledge_emergency(seeded, flying, at(10))
    with pytest.raises(EmergencyNotFoundError):
        acknowledgements.acknowledge_emergency(seeded, "MIS-NOPE", at(10))
    assert seeded.scalar(select(func.count()).select_from(IncidentAcknowledgement)) == 0


def test_the_api_acknowledges_idempotently_and_reports_a_missing_alert(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    mission_id = _emergency(seeded, session_factory, sim_settings, launch)
    before = _snapshot(seeded)
    url = f"/api/incidents/emergencies/{mission_id}/acknowledge"

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == second.status_code == 200
    assert first.json()["mission_id"] == mission_id
    assert first.json()["acknowledged_at"] == second.json()["acknowledged_at"]
    assert _snapshot(seeded) == before

    missing = client.post("/api/incidents/emergencies/MIS-NOPE/acknowledge")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "EMERGENCY_NOT_FOUND"


def test_the_flights_response_model_carries_the_acknowledgement_time() -> None:
    from app.simulation.schemas import FlightEmergency

    plain = FlightEmergency.model_validate(
        {"reason": "DRONE_FAILURE", "at": at(300), "position": (18.6, 54.4)}
    )
    marked = FlightEmergency.model_validate(
        {
            "reason": "DRONE_FAILURE",
            "at": at(300),
            "position": (18.6, 54.4),
            "acknowledged_at": at(400),
        }
    )
    assert plain.acknowledged_at is None and marked.acknowledged_at == at(400)


# --- GET /api/flights carries the acknowledgement (Feature 022, Gate C) ------------------------


def _drop_acknowledgements_table(engine: Engine) -> None:
    """Leave the database as it is before migration 0018 (no acknowledgements table)."""
    cast(Table, IncidentAcknowledgement.__table__).drop(engine)


def _flights_emergencies(client: TestClient) -> dict[str, dict[str, object]]:
    response = client.get("/api/flights")
    assert response.status_code == 200, response.text
    return {f["mission_id"]: f["emergency"] for f in response.json()["flights"] if f["emergency"]}


def test_the_flights_endpoint_marks_only_the_acknowledged_alert(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
) -> None:
    first = _emergency(seeded, session_factory, sim_settings, launch)
    second = launch("ORD-002", "DRN-011")
    trigger_drone_failure(seeded, at(8), sim_settings, origin=EventOrigin.AUTOMATIC)
    engine.advance_flight(session_factory, sim_settings, second, at(300))
    seeded.expire_all()
    assert {e["acknowledged_at"] for e in _flights_emergencies(client).values()} == {None}

    ack = client.post(f"/api/incidents/emergencies/{first}/acknowledge").json()

    emergencies = _flights_emergencies(client)
    assert set(emergencies) == {first, second}  # the alert stays in the data: history is kept
    assert emergencies[first]["acknowledged_at"] == ack["acknowledged_at"]
    assert emergencies[second]["acknowledged_at"] is None
    assert client.post(f"/api/incidents/emergencies/{first}/acknowledge").json() == ack


def test_flights_without_an_emergency_never_carry_an_acknowledgement(
    client: TestClient, seeded: Session, launch: Launch
) -> None:
    launch("ORD-001", "DRN-010")

    (flight,) = client.get("/api/flights").json()["flights"]

    assert flight["emergency"] is None


def test_a_missing_acknowledgements_table_is_an_error_not_a_silent_empty_answer(
    client: TestClient,
    seeded: Session,
    session_factory: sessionmaker[Session],
    sim_settings: Settings,
    launch: Launch,
    engine: Engine,
) -> None:
    mission_id = _emergency(seeded, session_factory, sim_settings, launch)
    seeded.commit()
    _drop_acknowledgements_table(engine)  # a database that was never migrated to 0018

    with pytest.raises(OperationalError):  # acknowledging fails loudly: it was not stored
        acknowledgements.acknowledge_emergency(seeded, mission_id, at(400))
    with pytest.raises(OperationalError):  # reading is not softened
        acknowledgements.acknowledged_at_by_mission(seeded, [mission_id])
    with pytest.raises(OperationalError):  # and neither is the flights endpoint
        client.get("/api/flights")


def test_the_flights_endpoint_without_any_emergency_does_not_touch_the_table(
    client: TestClient, seeded: Session, launch: Launch, engine: Engine
) -> None:
    launch("ORD-001", "DRN-010")
    _drop_acknowledgements_table(engine)

    response = client.get("/api/flights")  # no emergency flight: nothing to look up

    assert response.status_code == 200
    assert [f["emergency"] for f in response.json()["flights"]] == [None]
