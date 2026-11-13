"""Shared fixtures: an in-memory SQLite database, so tests need no external services."""

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from app.config import Settings
from app.db.session import Base, get_session
from app.dispatch import models as dispatch_models  # noqa: F401  (registers tables)
from app.drones import models as drone_models  # noqa: F401  (registers tables on Base.metadata)
from app.drones.models import Drone, DroneStatus
from app.drones.seed import build_sf1_model, seed_drones
from app.hubs import models as hub_models  # noqa: F401  (registers tables on Base.metadata)
from app.hubs.seed import seed_hubs
from app.main import create_app
from app.missions import models as mission_models  # noqa: F401  (registers tables on Base.metadata)
from app.missions import service as missions_service
from app.orders import models as order_models  # noqa: F401  (registers tables on Base.metadata)
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.seed import seed_orders
from app.simulation import models as simulation_models  # noqa: F401  (registers tables)
from app.simulation import service as simulation_service
from app.simulation.heartbeat import record_heartbeat


def _enable_sqlite_foreign_keys(dbapi_connection: SQLiteConnection, _: ConnectionPoolEntry) -> None:
    # SQLite ignores foreign keys unless asked; PostgreSQL always enforces them.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> TestClient:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app(Settings(cors_origins=["http://allowed.test"]))
    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.fixture
def hubs_and_model(session: Session) -> Session:
    """A session whose database already holds the four Hubs and the SF-1 model."""
    seed_hubs(session)
    session.add(build_sf1_model())
    session.commit()
    return session


@pytest.fixture
def make_drone() -> Callable[..., Drone]:
    """Factory for a valid drone row at the Forum Gdańsk Hub; override fields as needed."""

    def factory(**overrides: object) -> Drone:
        values: dict[str, object] = {
            "id": "DRN-900",
            "model_id": "SF-1",
            "hub_id": "hub-forum-gdansk",
            "status": DroneStatus.IDLE.value,
            "battery_pct": 80,
            "longitude": 18.64,
            "latitude": 54.35,
        }
        values.update(overrides)
        return Drone(**values)

    return factory


@pytest.fixture
def make_order() -> Callable[..., DeliveryOrder]:
    """Factory for a valid order from the Forum Gdańsk Hub; override fields as needed."""

    def factory(**overrides: object) -> DeliveryOrder:
        values: dict[str, object] = {
            "id": "ORD-900",
            "origin_hub_id": "hub-forum-gdansk",
            "destination_address": "ul. Testowa 1, Gdańsk",
            "destination_longitude": 18.65,
            "destination_latitude": 54.35,
            "package_weight_kg": 1.5,
            "status": OrderStatus.READY_FOR_PICKUP.value,
        }
        values.update(overrides)
        return DeliveryOrder(**values)

    return factory


@pytest.fixture
def seeded(session: Session) -> Session:
    """A session whose database holds the 4 Hubs, the SF-1 model, 12 drones and 11 orders.

    DRN-001..003 are docked at Osowa, 004..006 at Riviera, 007..009 at Forum Gdańsk and 010..012 at
    Galeria Bałtycka (batteries 100, 90, 80 per Hub). ORD-001..003 start at Bałtycka, 004..006 at
    Forum, 007..008 at Riviera and 009..010 at Osowa.
    """
    seed_hubs(session)
    seed_drones(session)
    seed_orders(session)
    return session


# --- flight simulation helpers ----------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def sim_settings() -> Settings:
    """Explicit settings so the tests never depend on the environment."""
    return Settings(
        mission_payload_energy_factor=0.5,
        hub_dock_proximity_m=50,
        sim_flight_min_seconds=30,
        sim_flight_max_seconds=90,
        sim_delivery_dwell_seconds=3,
        sim_landing_approach_m=60,
        sim_critical_battery_pct=5,
        sim_heartbeat_stale_seconds=10,
    )


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def launch(seeded: Session, sim_settings: Settings) -> Callable[..., str]:
    """Assign and start a mission at `now` (with a fresh worker heartbeat); returns its id."""

    def go(order_id: str, drone_id: str, now: datetime = NOW) -> str:
        mission = missions_service.confirm_mission(seeded, order_id, drone_id, sim_settings)
        record_heartbeat(seeded, now)
        simulation_service.start_mission(seeded, mission.id, now, sim_settings)
        return mission.id

    return go


@pytest.fixture(scope="module")
def temp_engine() -> Iterator[Engine]:
    """A uniquely named temporary PostgreSQL database with the real migrations applied.

    Only for tests marked `postgres` (opt-in: `pytest -m postgres`). It is created on the local
    Docker PostgreSQL (port 55432) next to the development database, which is never touched, and
    dropped afterwards. Anything else is refused and the test is skipped.
    """
    dev_url = make_url(Settings().database_url)
    if not dev_url.drivername.startswith("postgresql"):
        pytest.skip("The configured database is not PostgreSQL")
    if dev_url.host not in {"localhost", "127.0.0.1", "::1"} or dev_url.port != 55432:
        pytest.skip(
            f"Refusing to create databases on {dev_url.host}:{dev_url.port}; "
            "only the local Docker PostgreSQL (port 55432) is allowed"
        )
    prefix = "skyfleet_test_"
    name = f"{prefix}{uuid.uuid4().hex[:8]}"
    assert name != dev_url.database

    admin = create_engine(dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError:
        admin.dispose()
        pytest.skip("PostgreSQL is not reachable")

    test_url = dev_url.set(database=name)
    pg_engine = create_engine(test_url, pool_size=20)
    try:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        config.set_main_option("sqlalchemy.url", test_url.render_as_string(hide_password=False))
        command.upgrade(config, "head")
        with sessionmaker(bind=pg_engine)() as session:
            seed_hubs(session)
            seed_drones(session)
            seed_orders(session)
        yield pg_engine
    finally:
        pg_engine.dispose()
        with admin.connect() as connection:
            assert name.startswith(prefix) and name != dev_url.database  # last line of defence
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
