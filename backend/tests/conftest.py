"""Shared fixtures: an in-memory SQLite database, so tests need no external services."""

from collections.abc import Callable, Iterator
from sqlite3 import Connection as SQLiteConnection

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

from app.config import Settings
from app.db.session import Base, get_session
from app.drones import models as drone_models  # noqa: F401  (registers tables on Base.metadata)
from app.drones.models import Drone, DroneStatus
from app.drones.seed import build_sf1_model, seed_drones
from app.hubs import models as hub_models  # noqa: F401  (registers tables on Base.metadata)
from app.hubs.seed import seed_hubs
from app.main import create_app
from app.missions import models as mission_models  # noqa: F401  (registers tables on Base.metadata)
from app.orders import models as order_models  # noqa: F401  (registers tables on Base.metadata)
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.seed import seed_orders


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
    """A session whose database holds the 4 Hubs, the SF-1 model, 12 drones and 10 orders.

    DRN-001..003 are docked at Osowa, 004..006 at Riviera, 007..009 at Forum Gdańsk and 010..012 at
    Galeria Bałtycka (batteries 100, 90, 80 per Hub). ORD-001..003 start at Bałtycka, 004..006 at
    Forum, 007..008 at Riviera and 009..010 at Osowa.
    """
    seed_hubs(session)
    seed_drones(session)
    seed_orders(session)
    return session
