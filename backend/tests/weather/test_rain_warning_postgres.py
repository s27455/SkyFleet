"""Rain warning on PostgreSQL in a temporary database (Feature 020).

Opt-in (`uv run pytest -m postgres`). The `temp_engine` fixture applies the real migrations (0016
included) to a throwaway database, so the development database is never touched.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone
from app.events.models import OperationalEvent
from app.missions.models import Mission, MissionStatus
from app.missions.service import confirm_mission
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import MissionFlight
from app.simulation.service import start_mission
from app.weather import service as weather
from app.weather.service import RainWarningActiveError

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
    sim_heartbeat_stale_seconds=10,
)
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
PAIRS = [
    ("ORD-009", "DRN-001"),
    ("ORD-007", "DRN-004"),
    ("ORD-004", "DRN-007"),
    ("ORD-001", "DRN-010"),
]


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_the_migration_seeds_an_inactive_warning_and_accepts_the_new_events(
    temp_engine: Engine,
) -> None:
    assert "weather_state" in inspect(temp_engine).get_table_names()
    with _factory(temp_engine)() as session:
        assert weather.get_status(session).active is False
        with temp_engine.connect() as connection:
            row = connection.execute(text("SELECT name, active FROM weather_state")).one()
        assert tuple(row) == ("rain-warning", False)
        weather.activate(session, NOW)
        weather.clear(session, NOW)
        types = set(session.scalars(select(OperationalEvent.event_type)))
    assert {"RAIN_WARNING_ACTIVATED", "RAIN_WARNING_CLEARED"} <= types


def test_the_event_check_rejects_unknown_types_after_the_migration(temp_engine: Engine) -> None:
    with pytest.raises(IntegrityError), temp_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO operational_events (event_type, origin, occurred_at) "
                "VALUES ('RAIN_STARTED', 'MANUAL', now())"
            )
        )


def test_activation_waits_for_a_takeoff_that_already_holds_the_gate(temp_engine: Engine) -> None:
    factory = _factory(temp_engine)
    takeoff = factory()
    weather.lock_for_takeoff(takeoff)  # a takeoff transaction past the gate, not yet committed
    finished = threading.Event()

    def activate() -> None:
        with factory() as session:
            weather.activate(session, NOW)
        finished.set()

    thread = threading.Thread(target=activate)
    thread.start()
    assert not finished.wait(1.0)  # blocked: the takeoff is serialised before the warning
    takeoff.commit()  # the takeoff completes ...
    assert finished.wait(15)  # ... and only then does the warning become active
    thread.join()

    with factory() as session, pytest.raises(RainWarningActiveError):
        weather.lock_for_takeoff(session)  # every later takeoff sees it
    with factory() as session:
        weather.clear(session, NOW)


def test_takeoffs_racing_the_activation_leave_no_partial_state(temp_engine: Engine) -> None:
    factory = _factory(temp_engine)
    with factory() as session:
        record_heartbeat(session, NOW)
        for order_id, drone_id in PAIRS:
            confirm_mission(session, order_id, drone_id, SETTINGS)

    def start(mission_id: str) -> str:
        with factory() as session:
            try:
                start_mission(session, mission_id, NOW, SETTINGS)
            except RainWarningActiveError:
                return "blocked"
            return "started"

    def activate() -> str:
        with factory() as session:
            weather.activate(session, NOW)
        return "activated"

    with factory() as session:
        ids = [m.id for m in session.scalars(select(Mission).where(Mission.status == "ASSIGNED"))]
    assert len(ids) == len(PAIRS)
    with ThreadPoolExecutor(max_workers=len(ids) + 1) as pool:
        futures = [pool.submit(start, mission_id) for mission_id in ids] + [pool.submit(activate)]
        results = [future.result() for future in futures]

    assert results[-1] == "activated"
    with factory() as session:
        for mission_id in ids:
            mission = session.get(Mission, mission_id)
            flight = session.get(MissionFlight, mission_id)
            drone = session.get(Drone, mission.drone_id)  # type: ignore[union-attr]
            assert mission is not None and drone is not None
            if mission.status == MissionStatus.IN_FLIGHT.value:  # won the race: a whole takeoff
                assert flight is not None and drone.status == "IN_FLIGHT"
            else:  # refused: still ASSIGNED, no flight, drone untouched
                assert mission.status == MissionStatus.ASSIGNED.value
                assert flight is None and drone.status == "IDLE"
    # After the activation committed, no further takeoff can start.
    with factory() as session:
        remaining = [
            m.id for m in session.scalars(select(Mission).where(Mission.status == "ASSIGNED"))
        ]
    assert all(start(mission_id) == "blocked" for mission_id in remaining)

    with factory() as session:  # recoverable: after clearing, the existing start works
        weather.clear(session, NOW)
    for mission_id in remaining:
        assert start(mission_id) == "started"


def test_the_migration_round_trips_on_postgres(temp_engine: Engine) -> None:
    """Last: downgrade to 0015 and upgrade again on the throwaway database."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", temp_engine.url.render_as_string(hide_password=False))
    with temp_engine.begin() as connection:  # the downgrade refuses while rain events exist
        connection.execute(text("DELETE FROM operational_events WHERE event_type LIKE 'RAIN_%'"))

    command.downgrade(config, "0015")
    assert "weather_state" not in inspect(temp_engine).get_table_names()
    command.upgrade(config, "head")

    with _factory(temp_engine)() as session:
        assert weather.get_status(session).active is False
