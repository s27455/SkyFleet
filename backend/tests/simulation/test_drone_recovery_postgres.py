"""Drone recovery and acknowledgements on PostgreSQL in a temporary database (Feature 022).

Opt-in (`uv run pytest -m postgres`). The `temp_engine` fixture applies the real migrations (0018
included) to a throwaway database, so the development database is never touched. The tests share
that database, so each uses its own orders and drones and restores any Hub capacity it changes. The
migration round trip is the last test of the module.
"""

import random
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.drones.schemas import DroneCreateRequest
from app.drones.service import HubFullError, create_drone
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.presence import hub_occupancy
from app.simulation import acknowledgements, engine, recovery
from app.simulation import service as simulation_service
from app.simulation.failure import trigger_drone_failure
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import IncidentAcknowledgement
from app.simulation.recovery import (
    NoHubWithRoomError,
    NotEligibleError,
    RecoveryState,
    recover_grounded_drone,
    run_recovery_step,
)

pytestmark = pytest.mark.postgres

BACKEND_DIR = Path(__file__).resolve().parents[2]
SETTINGS = Settings(
    mission_payload_energy_factor=0.5,
    hub_dock_proximity_m=50,
    sim_flight_min_seconds=30,
    sim_flight_max_seconds=90,
    sim_delivery_dwell_seconds=3,
    sim_landing_approach_m=60,
    sim_critical_battery_pct=5,
    sim_heartbeat_stale_seconds=3600,
)
DELAY = SETTINGS.drone_recovery_delay_seconds


def _factory(pg: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=pg, expire_on_commit=False)


def _ground(
    factory: sessionmaker[Session],
    pairs: list[tuple[str, str]],
    t0: datetime,
    origin: EventOrigin = EventOrigin.AUTOMATIC,
) -> list[str]:
    """Launch each (order, drone), fail them all and ground them with the engine (no waiting)."""
    mission_ids: list[str] = []
    with factory() as session:
        for order_id, drone_id in pairs:
            mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
            record_heartbeat(session, t0)
            simulation_service.start_mission(session, mission.id, t0, SETTINGS)
            mission_ids.append(mission.id)
        for n in range(len(pairs)):
            trigger_drone_failure(
                session,
                t0 + timedelta(seconds=8),
                SETTINGS,
                origin=origin,
                rng=random.Random(n),
            )
    for mission_id in mission_ids:
        engine.advance_flight(factory, SETTINGS, mission_id, t0 + timedelta(seconds=300))
    return mission_ids


def _due(t0: datetime) -> datetime:
    return t0 + timedelta(seconds=300 + DELAY)


@contextmanager
def _capacities(factory: sessionmaker[Session], *, free_place_at: str | None) -> Iterator[None]:
    """Make every Hub exactly full but `free_place_at` (one free place); restore afterwards."""
    with factory() as session:
        hubs = list(session.scalars(select(Hub)))
        original = {hub.id: hub.drone_capacity for hub in hubs}
        counts = hub_occupancy(
            list(session.scalars(select(Drone))), hubs, SETTINGS.hub_dock_proximity_m
        )
        for hub in hubs:
            hub.drone_capacity = max(counts[hub.id], 1) + (1 if hub.id == free_place_at else 0)
        session.commit()
    try:
        yield
    finally:
        with factory() as session:
            for hub in session.scalars(select(Hub)):
                hub.drone_capacity = original[hub.id]
            session.commit()


def _recovered_events(factory: sessionmaker[Session], mission_id: str) -> int:
    with factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(
                    OperationalEvent.event_type == EventType.DRONE_RECOVERED.value,
                    OperationalEvent.mission_id == mission_id,
                )
            )
            or 0
        )


def _state(factory: sessionmaker[Session], drone_id: str) -> tuple[str, str, float, float]:
    with factory() as session:
        drone = session.get(Drone, drone_id)
        assert drone is not None
        return (drone.status, drone.hub_id, drone.longitude, drone.latitude)


def _occupancy_ok(factory: sessionmaker[Session]) -> bool:
    with factory() as session:
        hubs = list(session.scalars(select(Hub)))
        counts = hub_occupancy(
            list(session.scalars(select(Drone))), hubs, SETTINGS.hub_dock_proximity_m
        )
        return all(counts[hub.id] <= hub.drone_capacity for hub in hubs)


def test_concurrent_recoveries_of_one_mission_recover_it_exactly_once(temp_engine: Engine) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-001", "DRN-010")], t0)
    barrier = threading.Barrier(8)

    def attempt(_: int) -> str:
        barrier.wait()
        with factory() as session:
            try:
                recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
            except NotEligibleError:
                return "late"
        return "recovered"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [f.result(timeout=60) for f in [pool.submit(attempt, n) for n in range(8)]]

    assert outcomes.count("recovered") == 1 and outcomes.count("late") == 7
    assert _recovered_events(factory, mission_id) == 1
    assert _state(factory, "DRN-010")[0] != DroneStatus.MAINTENANCE.value


def test_two_recoveries_racing_for_the_last_free_place_cannot_overfill_the_hub(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    first, second = _ground(factory, [("ORD-002", "DRN-011"), ("ORD-003", "DRN-012")], t0)
    barrier = threading.Barrier(2)

    def attempt(mission_id: str) -> str:
        barrier.wait()
        with factory() as session:
            try:
                recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
            except NoHubWithRoomError:
                return "full"
        return "recovered"

    with _capacities(factory, free_place_at="hub-galeria-baltycka"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [
                f.result(timeout=60) for f in [pool.submit(attempt, m) for m in (first, second)]
            ]
        assert sorted(outcomes) == ["full", "recovered"]
        assert _occupancy_ok(factory)

    waiting = first if _recovered_events(factory, first) == 0 else second
    assert _recovered_events(factory, first) + _recovered_events(factory, second) == 1
    assert _recovered_events(factory, waiting) == 0  # it stays pending for a later look


def test_a_recovery_racing_a_normal_docking_for_the_last_place_cannot_overfill(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-004", "DRN-007")], t0)
    barrier = threading.Barrier(2)

    def recover() -> str:
        barrier.wait()
        with factory() as session:
            try:
                recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
            except NoHubWithRoomError:
                return "full"
        return "recovered"

    def dock() -> str:
        barrier.wait()
        with factory() as session:
            try:  # a normal docking: a new drone created at the Hub, checked under the Hub lock
                create_drone(session, DroneCreateRequest(hub_id="hub-forum-gdansk"), SETTINGS)
            except HubFullError:
                return "full"
        return "docked"

    with _capacities(factory, free_place_at="hub-forum-gdansk"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(recover), pool.submit(dock)
            outcomes = (a.result(timeout=60), b.result(timeout=60))
        assert sorted(outcomes) in (["full", "recovered"], ["docked", "full"]), outcomes
        assert _occupancy_ok(factory)  # exactly one of them got the place

    # clean up the extra drone so the shared database keeps its 12-drone fleet for the next tests
    with factory() as session:
        extra = [
            d
            for d in session.scalars(select(Drone))
            if d.id not in {f"DRN-{n:03d}" for n in range(1, 13)}
        ]
        for drone in extra:
            session.delete(drone)
        session.commit()


def test_a_failure_while_recovering_rolls_back_on_postgres_and_releases_the_locks(
    temp_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-005", "DRN-008")], t0)
    before = _state(factory, "DRN-008")

    def broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("event store unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(recovery, "append_event", broken)
        with factory() as session, pytest.raises(RuntimeError):
            recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
    assert _state(factory, "DRN-008") == before
    assert _recovered_events(factory, mission_id) == 0

    with factory() as session:  # the rolled-back attempt left no lock behind
        recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
    assert _recovered_events(factory, mission_id) == 1


def test_the_recovery_is_durable_and_a_restarted_worker_does_nothing_more(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-006", "DRN-009")], t0)

    assert run_recovery_step(factory, SETTINGS, _due(t0), RecoveryState()) >= 1

    # a brand-new connection pool, as after a worker restart
    fresh = create_engine(temp_engine.url)
    try:
        restarted = _factory(fresh)
        assert _state(restarted, "DRN-009")[0] != DroneStatus.MAINTENANCE.value
        assert _recovered_events(restarted, mission_id) == 1
        assert run_recovery_step(restarted, SETTINGS, _due(t0), RecoveryState()) == 0
        assert _recovered_events(restarted, mission_id) == 1
    finally:
        fresh.dispose()


def test_a_manual_failure_is_recovered_after_the_delay_and_not_before_on_postgres(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-007", "DRN-004")], t0, origin=EventOrigin.MANUAL)

    run_recovery_step(factory, SETTINGS, _due(t0) - timedelta(seconds=1), RecoveryState())
    assert _state(factory, "DRN-004")[0] == DroneStatus.MAINTENANCE.value  # 119 s after landing
    assert _recovered_events(factory, mission_id) == 0

    run_recovery_step(factory, SETTINGS, _due(t0), RecoveryState())  # 120 s after landing
    run_recovery_step(factory, SETTINGS, _due(t0), RecoveryState())  # and a second look

    assert _state(factory, "DRN-004")[0] != DroneStatus.MAINTENANCE.value
    assert _recovered_events(factory, mission_id) == 1
    with factory() as session:  # the failure keeps its origin; the recovery is the worker's
        origins = {
            e.event_type: e.origin
            for e in session.scalars(
                select(OperationalEvent).where(OperationalEvent.mission_id == mission_id)
            )
        }
    assert origins[EventType.DRONE_FAILURE.value] == EventOrigin.MANUAL.value
    assert origins[EventType.DRONE_RECOVERED.value] == EventOrigin.AUTOMATIC.value


def test_an_automatic_and_a_manual_failure_racing_for_the_last_place_cannot_overfill(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (automatic,) = _ground(factory, [("ORD-009", "DRN-001")], t0, origin=EventOrigin.AUTOMATIC)
    (manual,) = _ground(factory, [("ORD-010", "DRN-002")], t0, origin=EventOrigin.MANUAL)
    barrier = threading.Barrier(2)

    def attempt(mission_id: str) -> str:
        barrier.wait()
        with factory() as session:
            try:
                recover_grounded_drone(session, mission_id, _due(t0), SETTINGS)
            except NoHubWithRoomError:
                return "full"
        return "recovered"

    with _capacities(factory, free_place_at="hub-centrum-handlowe-osowa"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [
                f.result(timeout=60) for f in [pool.submit(attempt, m) for m in (automatic, manual)]
            ]
        assert sorted(outcomes) == ["full", "recovered"]  # exactly one place, exactly one winner
        assert _occupancy_ok(factory)

    assert _recovered_events(factory, automatic) + _recovered_events(factory, manual) == 1
    # the one left waiting is picked up by the next look once a place exists (capacities restored)
    assert run_recovery_step(factory, SETTINGS, _due(t0), RecoveryState()) >= 1
    assert _recovered_events(factory, automatic) == 1 and _recovered_events(factory, manual) == 1


def test_concurrent_acknowledgements_store_one_row_and_return_one_time(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    t0 = datetime.now(UTC)
    (mission_id,) = _ground(factory, [("ORD-008", "DRN-005")], t0, origin=EventOrigin.MANUAL)
    barrier = threading.Barrier(8)

    def acknowledge(n: int) -> datetime:
        barrier.wait()
        with factory() as session:
            return acknowledgements.acknowledge_emergency(
                session, mission_id, t0 + timedelta(seconds=n)
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        times = [f.result(timeout=60) for f in [pool.submit(acknowledge, n) for n in range(8)]]

    assert len(set(times)) == 1  # every request sees the one stored time
    with factory() as session:  # and the flights read returns exactly that time
        stored = acknowledgements.acknowledged_at_by_mission(session, [mission_id])
        assert stored == {mission_id: times[0]}
    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(IncidentAcknowledgement)
                .where(IncidentAcknowledgement.mission_id == mission_id)
            )
            == 1
        )


def test_the_migration_round_trips_and_leaves_other_tables_alone(temp_engine: Engine) -> None:
    """Last: downgrade to 0017 and upgrade again on the throwaway database."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", temp_engine.url.render_as_string(hide_password=False))
    columns = {c["name"] for c in inspect(temp_engine).get_columns("incident_acknowledgements")}
    assert columns == {"mission_id", "acknowledged_at"}
    # Migration 0019 (Feature 024) sits above 0017, so its AI tables go with the same downgrade.
    tables_before = set(inspect(temp_engine).get_table_names()) - {
        "incident_acknowledgements",
        "ai_budget_state",
        "ai_request_log",
    }

    with temp_engine.begin() as connection:  # the downgrade refuses while such events exist
        connection.execute(text("DELETE FROM incident_acknowledgements"))
        connection.execute(
            text("DELETE FROM operational_events WHERE event_type = 'DRONE_RECOVERED'")
        )
    command.downgrade(config, "0017")
    assert "incident_acknowledgements" not in inspect(temp_engine).get_table_names()
    with _factory(temp_engine)() as session, pytest.raises(ProgrammingError):
        acknowledgements.acknowledged_at_by_mission(session, ["MIS-ANY"])  # no table at 0017
    assert set(inspect(temp_engine).get_table_names()) == tables_before
    command.upgrade(config, "head")

    assert "incident_acknowledgements" in inspect(temp_engine).get_table_names()
    with _factory(temp_engine)() as session:  # and at 0018 it reads the (empty) table again
        assert acknowledgements.acknowledged_at_by_mission(session, ["MIS-ANY"]) == {}
