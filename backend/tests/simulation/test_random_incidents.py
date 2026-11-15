"""Random Incidents mode: persisted state, status and the API (Feature 021D-2)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch import auto
from app.dispatch.models import DispatchAutoState
from app.events.models import OperationalEvent
from app.orders import simulation as order_simulation
from app.orders.models import OrderSimulationState
from app.simulation import random_incidents
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import RANDOM_INCIDENTS, IncidentSchedulerState
from app.simulation.service import WorkerUnavailableError

SETTINGS = Settings(sim_heartbeat_stale_seconds=10)
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


def _row(session: Session) -> IncidentSchedulerState | None:
    session.expire_all()
    return session.get(IncidentSchedulerState, RANDOM_INCIDENTS)


# --- state ------------------------------------------------------------------------------------


def test_a_missing_row_means_off(session: Session) -> None:
    record_heartbeat(session, NOW)

    status = random_incidents.get_status(session, NOW, SETTINGS)

    assert status.enabled is False
    assert status.worker_running is True
    assert (status.last_check_at, status.last_outcome) == (None, None)
    assert _row(session) is None


def test_enable_needs_a_live_worker_and_creates_nothing_without_one(session: Session) -> None:
    with pytest.raises(WorkerUnavailableError):
        random_incidents.enable(session, NOW, SETTINGS)
    assert _row(session) is None

    record_heartbeat(session, NOW - timedelta(seconds=60))  # stale
    with pytest.raises(WorkerUnavailableError):
        random_incidents.enable(session, NOW, SETTINGS)
    assert _row(session) is None


def test_enable_and_disable_are_idempotent(session: Session) -> None:
    record_heartbeat(session, NOW)

    first = random_incidents.enable(session, NOW, SETTINGS)
    second = random_incidents.enable(session, NOW, SETTINGS)
    assert first.enabled and second.enabled

    first_off = random_incidents.disable(session, NOW, SETTINGS)
    second_off = random_incidents.disable(session, NOW, SETTINGS)
    assert not first_off.enabled and not second_off.enabled
    row = _row(session)
    assert row is not None and row.enabled is False


def test_disable_without_a_row_is_harmless(session: Session) -> None:
    status = random_incidents.disable(session, NOW, SETTINGS)

    assert status.enabled is False


def test_enabled_is_reported_only_while_the_worker_is_alive(session: Session) -> None:
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)

    later = random_incidents.get_status(session, NOW + timedelta(seconds=60), SETTINGS)

    assert later.enabled is False  # no stale ON is shown for a dead worker
    assert later.worker_running is False
    row = _row(session)
    assert row is not None and row.enabled is True  # the stored mode itself is untouched


def test_reset_to_off_clears_the_mode_and_says_why(session: Session) -> None:
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)

    random_incidents.reset_to_off(session, NOW)

    row = _row(session)
    assert row is not None and row.enabled is False
    assert row.last_outcome == "Reset to OFF when the simulation worker started"


def test_reset_to_off_works_without_a_row(session: Session) -> None:
    random_incidents.reset_to_off(session, NOW)

    row = _row(session)
    assert row is not None and row.enabled is False


def test_is_enabled_reads_the_stored_mode(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    assert random_incidents.is_enabled(session_factory) is False
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)
    assert random_incidents.is_enabled(session_factory) is True
    random_incidents.disable(session, NOW, SETTINGS)
    assert random_incidents.is_enabled(session_factory) is False


def test_record_attempt_stores_only_the_state_row(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)
    events_before = session.scalar(select(func.count()).select_from(OperationalEvent))

    changed = random_incidents.record_attempt(session_factory, NOW, "Skipped: x")
    again = random_incidents.record_attempt(session_factory, NOW, "Skipped: x")

    assert (changed, again) == (True, False)
    row = _row(session)
    assert row is not None
    assert (row.last_outcome, row.last_check_at is not None) == ("Skipped: x", True)
    assert session.scalar(select(func.count()).select_from(OperationalEvent)) == events_before


def test_record_attempt_does_not_create_a_row(session_factory: sessionmaker[Session]) -> None:
    assert random_incidents.record_attempt(session_factory, NOW, "Skipped: x") is False


def test_an_outcome_is_cut_to_the_column_length(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)

    random_incidents.record_attempt(session_factory, NOW, "x" * 400)

    row = _row(session)
    assert row is not None and row.last_outcome is not None and len(row.last_outcome) == 255


# --- independence from the other automatic modes ----------------------------------------------


def test_the_mode_is_independent_of_auto_dispatch_and_order_simulation(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    record_heartbeat(session, NOW)
    random_incidents.enable(session, NOW, SETTINGS)
    # Neither of the other modes sees this feature's row (and it must not create theirs).
    assert auto.is_enabled(session_factory) is False
    assert order_simulation.is_enabled(session_factory) is False
    assert session.scalar(select(func.count()).select_from(DispatchAutoState)) == 0
    assert session.scalar(select(func.count()).select_from(OrderSimulationState)) == 0

    auto.reset_to_off(session, NOW)
    order_simulation.reset_to_off(session, NOW)
    assert random_incidents.is_enabled(session_factory) is True  # their writes do not touch it

    random_incidents.disable(session, NOW, SETTINGS)
    assert auto.is_enabled(session_factory) is False


def test_other_modes_being_on_does_not_turn_random_incidents_on(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    session.add(DispatchAutoState(name="auto-dispatch", enabled=True, updated_at=NOW))
    session.add(OrderSimulationState(name="order-simulation", enabled=True, updated_at=NOW))
    session.commit()

    assert random_incidents.is_enabled(session_factory) is False


# --- API --------------------------------------------------------------------------------------


def _beat(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        record_heartbeat(session, datetime.now(UTC))


def test_api_status_is_off_by_default(client: TestClient) -> None:
    response = client.get("/api/incidents/random")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "worker_running": False,
        "last_check_at": None,
        "last_outcome": None,
    }


def test_api_enable_is_refused_without_a_worker(client: TestClient) -> None:
    response = client.post("/api/incidents/random/enable")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    assert client.get("/api/incidents/random").json()["enabled"] is False


def test_api_enable_and_disable_are_confirmed_by_the_response_and_idempotent(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _beat(session_factory)

    on = client.post("/api/incidents/random/enable")
    on_again = client.post("/api/incidents/random/enable")
    assert (on.status_code, on.json()["enabled"]) == (200, True)
    assert on_again.json()["enabled"] is True
    assert client.get("/api/incidents/random").json()["enabled"] is True

    off = client.post("/api/incidents/random/disable")
    off_again = client.post("/api/incidents/random/disable")
    assert (off.status_code, off.json()["enabled"]) == (200, False)
    assert off_again.json()["enabled"] is False


def test_api_disable_works_without_a_worker(client: TestClient) -> None:
    response = client.post("/api/incidents/random/disable")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_api_never_shows_internal_details(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _beat(session_factory)
    client.post("/api/incidents/random/enable")
    random_incidents.record_attempt(
        session_factory,
        datetime.now(UTC),
        "Error: the incident attempt failed (see the worker log)",
    )

    body = client.get("/api/incidents/random").json()

    assert body["last_outcome"] == "Error: the incident attempt failed (see the worker log)"
    assert set(body) == {"enabled", "worker_running", "last_check_at", "last_outcome"}
