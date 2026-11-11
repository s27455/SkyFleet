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
from app.drones.seed import build_sf1_model
from app.hubs import models as hub_models  # noqa: F401  (registers tables on Base.metadata)
from app.hubs.seed import seed_hubs
from app.main import create_app


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
