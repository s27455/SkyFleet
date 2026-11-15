"""Automatic order generation: mode, schedule, backpressure, worker loop and API (feature 015B)."""

import logging
import random
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.common import clock
from app.config import Settings
from app.dispatch.models import DispatchAutoState
from app.missions.models import Mission
from app.orders import simulation
from app.orders.models import DeliveryOrder, OrderSimulationState, OrderStatus
from app.simulation import service as simulation_service
from app.simulation.heartbeat import record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
Factory = sessionmaker[Session]


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "order_sim_min_interval_seconds": 15,
        "order_sim_max_interval_seconds": 30,
        "order_sim_max_outstanding_orders": 50,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def live(seeded: Session) -> Session:
    """Seeded data (11 READY_FOR_PICKUP orders) and a fresh worker heartbeat at NOW."""
    record_heartbeat(seeded, NOW)
    return seeded


def _turn_on(factory: Factory, settings: Settings | None = None) -> None:
    with factory() as session:
        simulation.enable(session, NOW, settings or make_settings())


def _orders(session: Session) -> list[DeliveryOrder]:
    session.expire_all()
    return list(session.scalars(select(DeliveryOrder).order_by(DeliveryOrder.id)))


def _step(factory: Factory, settings: Settings, seed: int = 1) -> str | None:
    return simulation.run_generation_step(factory, settings, NOW, random.Random(seed))


# --- settings ---------------------------------------------------------------------------------


def test_default_generation_settings() -> None:
    settings = Settings()

    assert settings.order_sim_min_interval_seconds == 15
    assert settings.order_sim_max_interval_seconds == 30
    assert settings.order_sim_max_outstanding_orders == 20


def test_the_maximum_interval_must_not_be_below_the_minimum() -> None:
    with pytest.raises(ValidationError):
        Settings(order_sim_min_interval_seconds=20, order_sim_max_interval_seconds=10)


def test_generation_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORDER_SIM_MIN_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("ORDER_SIM_MAX_INTERVAL_SECONDS", "4")
    monkeypatch.setenv("ORDER_SIM_MAX_OUTSTANDING_ORDERS", "7")

    settings = Settings()

    assert (settings.order_sim_min_interval_seconds, settings.order_sim_max_interval_seconds) == (
        2,
        4,
    )
    assert settings.order_sim_max_outstanding_orders == 7


# --- mode: OFF by default, idempotent toggles -------------------------------------------------


def test_the_mode_is_off_by_default_and_a_step_then_does_nothing(
    live: Session, session_factory: Factory
) -> None:
    before = len(_orders(live))
    with session_factory() as session:
        status = simulation.get_status(session, NOW, make_settings())
    assert (status.enabled, status.last_check_at, status.last_outcome) == (False, None, None)

    for _ in range(3):
        assert _step(session_factory, make_settings()) is None

    assert len(_orders(live)) == before
    assert live.get(OrderSimulationState, "order-simulation") is None  # nothing was written


def test_enable_and_disable_are_idempotent(live: Session, session_factory: Factory) -> None:
    settings = make_settings()
    with session_factory() as session:
        assert simulation.enable(session, NOW, settings).enabled
        assert simulation.enable(session, NOW, settings).enabled
        assert not simulation.disable(session, NOW, settings).enabled
        assert not simulation.disable(session, NOW, settings).enabled
    assert len(live.scalars(select(OrderSimulationState)).all()) == 1


def test_enabling_is_refused_while_the_worker_heartbeat_is_stale(
    seeded: Session, session_factory: Factory
) -> None:
    record_heartbeat(seeded, NOW - timedelta(seconds=60))

    with session_factory() as session, pytest.raises(simulation_service.WorkerUnavailableError):
        simulation.enable(session, NOW, make_settings())

    assert not simulation.is_enabled(session_factory)


def test_a_worker_start_resets_the_mode_to_off_and_creates_nothing(
    live: Session, session_factory: Factory
) -> None:
    _turn_on(session_factory)
    before = len(_orders(live))

    with session_factory() as session:
        simulation.reset_to_off(session, NOW)

    assert not simulation.is_enabled(session_factory)
    assert _step(session_factory, make_settings()) is None
    assert len(_orders(live)) == before


def test_the_reported_mode_is_off_when_no_worker_is_alive(
    live: Session, session_factory: Factory
) -> None:
    _turn_on(session_factory)

    with session_factory() as session:
        status = simulation.get_status(session, NOW + timedelta(seconds=60), make_settings())

    assert (status.enabled, status.worker_running) == (False, False)


# --- schedule ---------------------------------------------------------------------------------


def test_enabling_never_produces_an_immediate_order() -> None:
    schedule = simulation.GenerationSchedule(make_settings(), random.Random(1))

    assert schedule.poll(False, 100.0) is False
    assert schedule.poll(True, 100.0) is False  # the first poll after turning ON only schedules
    assert schedule.poll(True, 100.0 + 14.9) is False  # still inside the minimum pause


def test_the_pause_between_orders_stays_within_the_configured_bounds() -> None:
    schedule = simulation.GenerationSchedule(make_settings(), random.Random(5))
    now = 0.0
    schedule.poll(True, now)
    gaps: list[float] = []
    last_due = now
    while len(gaps) < 60:
        now += 0.5
        if schedule.poll(True, now):
            gaps.append(now - last_due)
            last_due = now

    assert all(15 <= gap <= 30.5 for gap in gaps)  # 0.5 s polling resolution
    assert len({round(gap) for gap in gaps}) > 3  # the pauses actually vary


def test_a_long_stall_yields_one_due_order_and_no_catch_up_burst() -> None:
    schedule = simulation.GenerationSchedule(make_settings(), random.Random(2))
    schedule.poll(True, 0.0)

    assert schedule.poll(True, 10_000.0) is True  # many intervals were missed
    assert schedule.poll(True, 10_000.0) is False
    assert schedule.poll(True, 10_014.0) is False  # the next one waits a full pause again


def test_turning_off_forgets_the_schedule() -> None:
    schedule = simulation.GenerationSchedule(make_settings(), random.Random(3))
    schedule.poll(True, 0.0)

    assert schedule.poll(False, 5.0) is False
    assert schedule.poll(True, 1_000.0) is False  # re-enabled later: scheduled, not due


# --- generating -------------------------------------------------------------------------------


def test_a_step_creates_one_ordinary_ready_order(live: Session, session_factory: Factory) -> None:
    _turn_on(session_factory)
    before = {o.id for o in _orders(live)}

    outcome = _step(session_factory, make_settings())

    created = [o for o in _orders(live) if o.id not in before]
    assert len(created) == 1
    assert created[0].status == OrderStatus.READY_FOR_PICKUP.value
    assert outcome is not None and outcome.startswith(f"Created {created[0].id}")
    row = live.get(OrderSimulationState, "order-simulation")
    assert row is not None and row.last_outcome == outcome and row.last_check_at is not None
    assert live.scalar(select(func.count()).select_from(Mission)) == 0  # no mission is started


def test_repeated_steps_create_distinct_orders_and_keep_existing_ones(
    live: Session, session_factory: Factory
) -> None:
    _turn_on(session_factory)
    before = {o.id: o.destination_address for o in _orders(live)}

    for seed in range(5):
        _step(session_factory, make_settings(), seed)

    after = {o.id: o.destination_address for o in _orders(live)}
    assert len(after) == len(before) + 5
    assert before.items() <= after.items()


def test_generation_pauses_at_the_limit_and_resumes_when_the_backlog_drops(
    live: Session, session_factory: Factory
) -> None:
    settings = make_settings(order_sim_max_outstanding_orders=12)  # 11 are already waiting
    _turn_on(session_factory, settings)

    assert (_step(session_factory, settings) or "").startswith("Created")  # 11 -> 12
    snapshot = {o.id: (o.status, o.package_weight_kg) for o in _orders(live)}

    paused = _step(session_factory, settings)

    assert paused == "Paused: 12 outstanding orders (limit 12)"
    assert {o.id: (o.status, o.package_weight_kg) for o in _orders(live)} == snapshot

    live.delete(live.get(DeliveryOrder, "ORD-001"))
    live.commit()
    assert (_step(session_factory, settings) or "").startswith("Created")


def test_only_ready_orders_count_towards_the_limit(live: Session, session_factory: Factory) -> None:
    settings = make_settings(order_sim_max_outstanding_orders=12)
    _turn_on(session_factory, settings)
    for order in _orders(live)[:3]:
        order.status = OrderStatus.DELIVERED.value
    live.commit()

    assert (_step(session_factory, settings) or "").startswith("Created")  # 8 waiting, room left


def test_a_mode_switched_off_meanwhile_creates_nothing(
    live: Session, session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    _turn_on(session_factory)
    before = len(_orders(live))
    answers = iter([True, False])  # ON at the start, OFF just before the order would be created
    monkeypatch.setattr(simulation, "is_enabled", lambda _factory: next(answers))

    assert _step(session_factory, make_settings()) is None

    assert len(_orders(live)) == before


# --- failures ---------------------------------------------------------------------------------


def test_a_generation_error_is_reported_without_raising_or_leaving_an_order(
    live: Session,
    session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _turn_on(session_factory)
    before = len(_orders(live))

    def boom(*_args: object, **_kwargs: object) -> DeliveryOrder:
        raise RuntimeError("database exploded")

    monkeypatch.setattr(simulation, "generate_one_order", boom)
    with caplog.at_level(logging.INFO, logger="skyfleet.orders"):
        first = _step(session_factory, make_settings())
        second = _step(session_factory, make_settings())

    assert first == second == "Generation failed (RuntimeError); will retry"
    assert len(_orders(live)) == before
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1  # no log flood
    monkeypatch.undo()
    assert (_step(session_factory, make_settings()) or "").startswith("Created")  # next try works


# --- worker loop ------------------------------------------------------------------------------


class StopLoopError(Exception):
    pass


def _run_worker(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    settings: Settings,
    ticks: int,
    after_tick: dict[int, object] | None = None,
) -> None:
    """Run the real `run_forever` for a fixed number of ticks with a fake clock and no waiting."""
    count = {"ticks": 0}
    fake_clock = {"now": 0.0}

    def monotonic() -> float:
        fake_clock["now"] += 100.0  # every call is far later than any scheduled time
        return fake_clock["now"]

    def sleep(_seconds: float) -> None:
        count["ticks"] += 1
        hook = (after_tick or {}).get(count["ticks"])
        if callable(hook):
            hook()
        if count["ticks"] >= ticks:
            raise StopLoopError

    monkeypatch.setattr(worker, "get_engine", lambda: engine)
    monkeypatch.setattr("app.worker.time.sleep", sleep)
    monkeypatch.setattr("app.worker.time.monotonic", monotonic)
    with pytest.raises(StopLoopError):
        worker.run_forever(settings)


def test_the_worker_resets_the_mode_then_schedules_then_generates(
    live: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings()
    _turn_on(factory, settings)  # left ON by an earlier worker run
    before = len(_orders(live))

    def operator_enables() -> None:
        with factory() as session:
            simulation.enable(session, clock.utcnow(), settings)

    # tick 1 resets to OFF; the operator then enables; tick 2 only schedules; tick 3 creates one
    _run_worker(monkeypatch, engine, settings, ticks=3, after_tick={1: operator_enables})

    assert len(_orders(live)) == before + 1
    row = live.get(OrderSimulationState, "order-simulation")
    assert row is not None and row.enabled and (row.last_outcome or "").startswith("Created")


def test_an_order_generation_failure_never_stops_the_worker_or_dispatch_reset(
    live: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_factory: Factory) -> bool:
        raise RuntimeError("generation broke")

    monkeypatch.setattr("app.worker.order_simulation.is_enabled", boom)

    _run_worker(monkeypatch, engine, make_settings(), ticks=3)  # no exception except StopLoopError

    dispatch_row = live.get(DispatchAutoState, "auto-dispatch")
    assert dispatch_row is not None and not dispatch_row.enabled


# --- API --------------------------------------------------------------------------------------


def test_the_api_reports_enables_and_disables_the_mode(client: TestClient, seeded: Session) -> None:
    record_heartbeat(seeded, clock.utcnow())

    off = client.get("/api/orders/simulation/status").json()
    assert off["enabled"] is False and off["worker_running"] is True
    assert off["last_check_at"] is None and off["last_outcome"] is None
    assert off["outstanding_orders"] == 11 and off["max_outstanding_orders"] == 20

    assert client.post("/api/orders/simulation/enable").json()["enabled"] is True
    assert client.post("/api/orders/simulation/enable").json()["enabled"] is True
    assert client.get("/api/orders/simulation/status").json()["enabled"] is True
    assert client.post("/api/orders/simulation/disable").json()["enabled"] is False
    assert client.post("/api/orders/simulation/disable").json()["enabled"] is False
    assert client.get("/api/orders/simulation/status").json()["enabled"] is False


def test_the_api_refuses_to_enable_without_a_worker(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/orders/simulation/enable")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    status = client.get("/api/orders/simulation/status").json()
    assert (status["enabled"], status["worker_running"]) == (False, False)


def test_order_simulation_and_automatic_dispatch_are_independent(
    client: TestClient, seeded: Session
) -> None:
    record_heartbeat(seeded, clock.utcnow())

    client.post("/api/orders/simulation/enable")
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is False

    client.post("/api/dispatch/auto/enable")
    client.post("/api/orders/simulation/disable")
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is True
    assert client.get("/api/orders/simulation/status").json()["enabled"] is False

    client.post("/api/dispatch/auto/disable")
    client.post("/api/orders/simulation/enable")
    assert client.get("/api/orders/simulation/status").json()["enabled"] is True
    assert client.get("/api/dispatch/auto/status").json()["enabled"] is False


def test_existing_order_and_dispatch_endpoints_still_work(
    client: TestClient, seeded: Session
) -> None:
    assert client.get("/api/orders/ORD-001").status_code == 200
    assert client.get("/api/orders/simulation").status_code == 404  # an unknown order id
    assert client.post("/api/orders/generate").status_code == 201
    assert client.get("/api/dispatch/auto/status").status_code == 200
    assert client.get("/api/dispatch/recommendations").status_code == 200
