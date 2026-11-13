"""Automatic dispatch mode and pass (feature 014C)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch import auto
from app.dispatch import service as dispatch_service
from app.dispatch.models import DispatchAutoState
from app.drones.models import Drone, DroneStatus
from app.missions.models import Mission, MissionStatus
from app.orders.models import DeliveryOrder
from app.simulation import clock
from app.simulation import service as simulation_service
from app.simulation.heartbeat import record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
# Seeded: one 100 % drone per Hub (DRN-001 Osowa, 004 Riviera, 007 Forum, 010 Bałtycka); the
# oldest ready order of each Hub is ORD-009, ORD-007, ORD-004 and ORD-001.
FOUR_PAIRS = {
    ("ORD-009", "DRN-001"),
    ("ORD-007", "DRN-004"),
    ("ORD-004", "DRN-007"),
    ("ORD-001", "DRN-010"),
}

Factory = sessionmaker[Session]


@pytest.fixture
def live(seeded: Session) -> Session:
    record_heartbeat(seeded, NOW)  # a fresh worker heartbeat at NOW
    return seeded


def _turn_on(factory: Factory) -> None:
    with factory() as session:
        auto.enable(session, NOW, Settings())


def _missions(session: Session) -> list[Mission]:
    session.expire_all()
    return list(session.scalars(select(Mission)))


def _pairs(session: Session) -> set[tuple[str, str]]:
    return {(m.order_id, m.drone_id) for m in _missions(session)}


def _drone(session: Session, drone_id: str) -> Drone:
    drone = session.get(Drone, drone_id)
    assert drone is not None
    return drone


def _pass(factory: Factory, settings: Settings) -> str | None:
    return auto.run_dispatch_pass(factory, settings, NOW)


# --- mode: OFF by default, idempotent toggles -------------------------------------------------


def test_the_mode_is_off_by_default_and_a_pass_then_does_nothing(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    with session_factory() as session:
        status = auto.get_status(session, NOW, sim_settings)
    assert (status.enabled, status.last_check_at, status.last_outcome) == (False, None, None)

    for _ in range(3):
        assert _pass(session_factory, sim_settings) is None

    assert _missions(live) == []
    assert live.get(DispatchAutoState, "auto-dispatch") is None  # nothing was even written


def test_enable_and_disable_are_idempotent(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    with session_factory() as session:
        assert auto.enable(session, NOW, sim_settings).enabled
        assert auto.enable(session, NOW, sim_settings).enabled
        assert not auto.disable(session, NOW, sim_settings).enabled
        assert not auto.disable(session, NOW, sim_settings).enabled
    assert len(live.scalars(select(DispatchAutoState)).all()) == 1


def test_enabling_is_refused_while_the_worker_heartbeat_is_stale(
    seeded: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    record_heartbeat(seeded, NOW - timedelta(seconds=60))

    with session_factory() as session, pytest.raises(simulation_service.WorkerUnavailableError):
        auto.enable(session, NOW, sim_settings)

    assert not auto.is_enabled(session_factory)


def test_a_worker_start_resets_the_mode_to_off(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _turn_on(session_factory)
    assert auto.is_enabled(session_factory)

    with session_factory() as session:
        auto.reset_to_off(session, NOW)

    assert not auto.is_enabled(session_factory)
    assert _pass(session_factory, sim_settings) is None
    assert _missions(live) == []


def test_the_reported_mode_is_off_when_no_worker_is_alive(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _turn_on(session_factory)
    later = NOW + timedelta(seconds=60)  # the heartbeat from NOW is now stale

    with session_factory() as session:
        status = auto.get_status(session, later, sim_settings)

    assert (status.enabled, status.worker_running) == (False, False)


# --- dispatching ------------------------------------------------------------------------------


def test_turning_it_on_dispatches_every_hub_independently(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _turn_on(session_factory)

    outcome = _pass(session_factory, sim_settings)

    assert outcome == "Started 4 mission(s)"
    assert _pairs(live) == FOUR_PAIRS
    assert {m.status for m in _missions(live)} == {MissionStatus.IN_FLIGHT}
    with session_factory() as session:
        status = auto.get_status(session, NOW, sim_settings)
    assert status.last_check_at == NOW and status.last_outcome == outcome


def test_repeated_passes_create_no_duplicates(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _turn_on(session_factory)
    _pass(session_factory, sim_settings)

    second = _pass(session_factory, sim_settings)
    third = _pass(session_factory, sim_settings)

    assert _pairs(live) == FOUR_PAIRS and len(_missions(live)) == 4
    assert second == third and second is not None and second.startswith("Nothing to dispatch")


def test_a_hub_without_a_ready_drone_does_not_stop_the_others(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _drone(live, "DRN-007").battery_pct = 99  # Forum has no 100 % drone
    live.commit()
    _turn_on(session_factory)

    _pass(session_factory, sim_settings)

    assert _pairs(live) == FOUR_PAIRS - {("ORD-004", "DRN-007")}


def test_an_unserviceable_oldest_order_does_not_block_a_newer_one(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    far = live.get(DeliveryOrder, "ORD-004")
    assert far is not None
    far.destination_longitude, far.destination_latitude = 19.9, 55.4
    live.commit()
    _turn_on(session_factory)

    _pass(session_factory, sim_settings)

    assert ("ORD-005", "DRN-007") in _pairs(live)
    assert "ORD-004" not in {order for order, _ in _pairs(live)}


def test_two_orders_and_two_drones_in_one_hub_get_distinct_assignments(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _drone(live, "DRN-008").battery_pct = 100
    live.commit()
    _turn_on(session_factory)

    _pass(session_factory, sim_settings)

    forum = {pair for pair in _pairs(live) if pair[0] in {"ORD-004", "ORD-005", "ORD-006"}}
    assert forum == {("ORD-004", "DRN-007"), ("ORD-005", "DRN-008")}


def _battery(drone: Drone) -> None:
    drone.battery_pct = 99


def _maintenance(drone: Drone) -> None:
    drone.status = DroneStatus.MAINTENANCE.value


def _charging(drone: Drone) -> None:
    drone.status = DroneStatus.CHARGING.value


def _in_flight(drone: Drone) -> None:
    drone.status = DroneStatus.IN_FLIGHT.value


@pytest.mark.parametrize("exclude", [_battery, _maintenance, _charging, _in_flight])
def test_an_ineligible_drone_is_never_dispatched_automatically(
    live: Session,
    session_factory: Factory,
    sim_settings: Settings,
    exclude: Callable[[Drone], None],
) -> None:
    exclude(_drone(live, "DRN-007"))
    live.commit()
    _turn_on(session_factory)

    for _ in range(2):
        _pass(session_factory, sim_settings)

    assert "DRN-007" not in {drone for _, drone in _pairs(live)}
    assert ("ORD-009", "DRN-001") in _pairs(live)  # the other Hubs are unaffected


# --- turning it off ---------------------------------------------------------------------------


def test_turning_it_off_stops_new_starts_but_not_flights(
    live: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    _turn_on(session_factory)
    _pass(session_factory, sim_settings)
    flying = {m.id for m in _missions(live)}
    order = live.get(DeliveryOrder, "ORD-005")
    assert order is not None

    with session_factory() as session:
        auto.disable(session, NOW, sim_settings)
    _drone(live, "DRN-008").battery_pct = 100  # would be dispatchable if the mode were ON
    live.commit()

    assert _pass(session_factory, sim_settings) is None
    assert {m.id for m in _missions(live)} == flying
    assert {m.status for m in _missions(live)} == {MissionStatus.IN_FLIGHT}  # flights continue


def test_the_mode_is_checked_before_every_execution(
    live: Session,
    session_factory: Factory,
    sim_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_execute = dispatch_service.execute_dispatch
    calls: list[str] = []

    def execute_then_disable(*args: object, **kwargs: object) -> Mission:
        mission = real_execute(*args, **kwargs)  # type: ignore[arg-type]
        calls.append(mission.id)
        with session_factory() as session:  # the operator switches it OFF meanwhile
            auto.disable(session, NOW, sim_settings)
        return mission

    monkeypatch.setattr(auto, "execute_dispatch", execute_then_disable)
    _turn_on(session_factory)

    outcome = _pass(session_factory, sim_settings)

    assert len(calls) == 1 and len(_missions(live)) == 1  # the running one finished, no more began
    assert outcome is not None and "turned OFF" in outcome


# --- failures are controlled outcomes ---------------------------------------------------------


def test_a_failed_start_is_reported_and_leaves_the_mission_assigned(
    live: Session,
    session_factory: Factory,
    sim_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_start(*_args: object, **_kwargs: object) -> Mission:
        raise simulation_service.WorkerUnavailableError(None, 10)

    monkeypatch.setattr(dispatch_service, "start_mission", failing_start)
    _turn_on(session_factory)

    outcome = _pass(session_factory, sim_settings)  # must not raise

    assert outcome is not None and "created but not started" in outcome
    assert {m.status for m in _missions(live)} == {MissionStatus.ASSIGNED}
    count = len(_missions(live))

    monkeypatch.undo()  # a later pass neither retries nor duplicates the assigned ones
    _pass(session_factory, sim_settings)
    assert len(_missions(live)) == count


def test_one_failing_pair_does_not_stop_the_others(
    live: Session,
    session_factory: Factory,
    sim_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_execute = dispatch_service.execute_dispatch

    def flaky(session: Session, order_id: str, *args: object, **kwargs: object) -> Mission:
        if order_id == "ORD-007":
            raise RuntimeError("boom")
        return real_execute(session, order_id, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(auto, "execute_dispatch", flaky)
    _turn_on(session_factory)

    outcome = _pass(session_factory, sim_settings)

    assert _pairs(live) == FOUR_PAIRS - {("ORD-007", "DRN-004")}
    assert outcome is not None and "unexpected error dispatching ORD-007" in outcome


def test_a_stale_worker_creates_nothing_and_the_pass_survives(
    seeded: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    record_heartbeat(seeded, NOW)
    _turn_on(session_factory)
    record_heartbeat(seeded, NOW - timedelta(seconds=60))  # the heartbeat goes stale

    outcome = _pass(session_factory, sim_settings)

    assert outcome is not None and "worker unavailable" in outcome
    assert _missions(seeded) == []


# --- API --------------------------------------------------------------------------------------


def test_the_api_reports_enables_and_disables_the_mode(client: TestClient, seeded: Session) -> None:
    record_heartbeat(seeded, clock.utcnow())

    off = client.get("/api/dispatch/auto/status").json()
    assert off == {
        "enabled": False,
        "worker_running": True,
        "last_check_at": None,
        "last_outcome": None,
    }

    on = client.post("/api/dispatch/auto/enable")
    assert on.status_code == 200 and on.json()["enabled"] is True
    assert client.post("/api/dispatch/auto/enable").json()["enabled"] is True
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is True

    assert client.post("/api/dispatch/auto/disable").json()["enabled"] is False
    assert client.post("/api/dispatch/auto/disable").json()["enabled"] is False
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is False


def test_the_api_refuses_to_enable_without_a_worker(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/dispatch/auto/enable")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    status = client.get("/api/dispatch/auto/status").json()
    assert (status["enabled"], status["worker_running"]) == (False, False)


def test_existing_dispatch_and_mission_endpoints_still_work(
    client: TestClient, seeded: Session
) -> None:
    record_heartbeat(seeded, clock.utcnow())

    assert client.get("/api/dispatch/recommendations").status_code == 200
    assert client.get("/api/missions").status_code == 200
    created = client.post(
        "/api/dispatch/execute", json={"order_id": "ORD-004", "drone_id": "DRN-007"}
    )
    assert created.status_code == 201
