"""Random Incidents on PostgreSQL in a temporary database (Feature 021D-2).

Opt-in (`uv run pytest -m postgres`). The `temp_engine` fixture applies the real migrations (0017
included) to a throwaway database, so the development database is never touched. The migration
round trip is the last test of the module.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.missions import service as missions_service
from app.simulation import random_incidents
from app.simulation import service as simulation_service
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import RANDOM_INCIDENTS, IncidentSchedulerState, MissionFlight

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


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def _launch(factory: sessionmaker[Session], order_id: str, drone_id: str) -> str:
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission.id, now, SETTINGS)
        return mission.id


def test_the_mode_is_shared_across_sessions_and_idempotent_under_concurrency(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    with factory() as session:
        record_heartbeat(session, datetime.now(UTC))
    assert random_incidents.is_enabled(factory) is False  # no row: OFF

    barrier = threading.Barrier(8)

    def toggle(n: int) -> bool:
        barrier.wait()  # the first-ever writes race to create the row
        with factory() as session:
            status = (
                random_incidents.enable(session, datetime.now(UTC), SETTINGS)
                if n % 2 == 0
                else random_incidents.disable(session, datetime.now(UTC), SETTINGS)
            )
            return status.enabled

    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in [pool.submit(toggle, n) for n in range(8)]:
            future.result(timeout=60)  # no error from the race

    with factory() as session:
        rows = list(session.scalars(select(IncidentSchedulerState)))
        assert [row.name for row in rows] == [RANDOM_INCIDENTS]  # one row, never a second
    with factory() as session:
        random_incidents.enable(session, datetime.now(UTC), SETTINGS)
    assert random_incidents.is_enabled(_factory(temp_engine)) is True  # another session sees it
    with factory() as session:
        random_incidents.reset_to_off(session, datetime.now(UTC))  # what the worker does at start
    assert random_incidents.is_enabled(factory) is False


def test_a_manual_and_automatic_failure_racing_on_one_mission_fail_it_once(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    mission_id = _launch(factory, "ORD-001", "DRN-010")

    def attempt(automatic: bool) -> str:
        with factory() as session:
            try:
                trigger_drone_failure(
                    session,
                    datetime.now(UTC),
                    SETTINGS,
                    origin=EventOrigin.AUTOMATIC if automatic else EventOrigin.MANUAL,
                    automatic_safety=automatic,
                )
            except NoEligibleTargetError:
                return "none"
        return "failed"

    barrier = threading.Barrier(8)

    def run(n: int) -> str:
        barrier.wait()
        return attempt(n % 2 == 0)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [f.result(timeout=60) for f in [pool.submit(run, n) for n in range(8)]]

    assert outcomes.count("failed") == 1 and outcomes.count("none") == 7  # no duplicate incident
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None and flight.failed_at is not None
        events = list(
            session.scalars(
                select(OperationalEvent).where(
                    OperationalEvent.event_type == EventType.DRONE_FAILURE.value
                )
            )
        )
        assert len(events) == 1


def test_an_automatic_failure_and_a_recipient_report_never_overlap_on_one_mission(
    temp_engine: Engine,
) -> None:
    factory = _factory(temp_engine)
    mission_id = _launch(factory, "ORD-004", "DRN-007")

    def fail() -> str:
        with factory() as session:
            try:
                trigger_drone_failure(
                    session,
                    datetime.now(UTC),
                    SETTINGS,
                    origin=EventOrigin.AUTOMATIC,
                    automatic_safety=True,
                )
            except NoEligibleTargetError:
                return "none"
        return "failed"

    def recipient() -> str:
        with factory() as session:
            try:
                trigger_recipient_unavailable(
                    session, datetime.now(UTC), SETTINGS, origin=EventOrigin.AUTOMATIC
                )
            except NoEligibleTargetError:
                return "none"
        return "marked"

    barrier = threading.Barrier(8)

    def run(n: int) -> str:
        barrier.wait()
        return fail() if n % 2 == 0 else recipient()

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [f.result(timeout=60) for f in [pool.submit(run, n) for n in range(8)]]

    assert (outcomes.count("failed"), outcomes.count("marked")) in {(1, 0), (0, 1)}
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        assert (flight.failed_at is not None) != (flight.recipient_unavailable_at is not None)


def test_the_migration_round_trips_and_leaves_the_other_modes_alone(temp_engine: Engine) -> None:
    """Last: downgrade to 0016 and upgrade again on the throwaway database."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", temp_engine.url.render_as_string(hide_password=False))
    columns = {c["name"] for c in inspect(temp_engine).get_columns("incident_scheduler_state")}
    assert columns == {"name", "enabled", "last_check_at", "last_outcome", "updated_at"}
    tables_before = set(inspect(temp_engine).get_table_names()) - {"incident_scheduler_state"}

    command.downgrade(config, "0016")
    assert "incident_scheduler_state" not in inspect(temp_engine).get_table_names()
    assert set(inspect(temp_engine).get_table_names()) == tables_before  # nothing else changed
    command.upgrade(config, "head")

    assert "incident_scheduler_state" in inspect(temp_engine).get_table_names()
    assert random_incidents.is_enabled(_factory(temp_engine)) is False  # a fresh table is OFF
