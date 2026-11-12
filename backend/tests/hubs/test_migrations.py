"""Guards that the Alembic migrations and the SQLAlchemy models describe the same schema."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from app.db.session import Base
from app.drones import models as drone_models  # noqa: F401  (registers tables on Base.metadata)
from app.hubs import models as hub_models  # noqa: F401  (registers tables on Base.metadata)
from app.missions import models as mission_models  # noqa: F401  (registers tables on Base.metadata)
from app.orders import models as order_models  # noqa: F401  (registers tables on Base.metadata)
from app.simulation import models as simulation_models  # noqa: F401  (registers tables)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migrations_create_schema_matching_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"

    command.upgrade(make_config(url), "head")

    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()
    assert diff == []


def test_migrations_can_downgrade_to_base(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    with engine.connect() as connection:
        tables = set(
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        )
    engine.dispose()
    assert not {"hubs", "drones", "drone_models", "orders", "missions"} & tables


def test_downgrade_to_0001_drops_only_the_drone_tables(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)

    command.upgrade(config, "head")
    command.downgrade(config, "0001")
    engine = create_engine(url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    engine.dispose()
    assert "hubs" in tables
    assert not {"drones", "drone_models", "orders", "missions"} & tables

    command.upgrade(config, "head")


def test_migrated_schema_enforces_check_constraints_and_foreign_keys(tmp_path: Path) -> None:
    """compare_metadata ignores CHECK constraints, so exercise the migration's own DDL."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(make_config(url), "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(
            "INSERT INTO hubs (id, name, address, longitude, latitude) "
            "VALUES ('h1', 'H1', 'a', 18.0, 54.0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'hexacopter', 3.0, 20.0, 14.0, "
            "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
        )

    drone = (
        "INSERT INTO drones VALUES ('D1', '{model}', '{hub}', '{status}', {battery}, 18.0, 54.0)"
    )
    invalid_inserts = [
        drone.format(model="M1", hub="h1", status="IDLE", battery=101),
        drone.format(model="M1", hub="h1", status="FLYING", battery=50),
        drone.format(model="M1", hub="missing", status="IDLE", battery=50),
        drone.format(model="missing", hub="h1", status="IDLE", battery=50),
        "INSERT INTO drone_models VALUES ('M2', 'Model 2', 'x', 0.0, 20.0, 14.0, "
        "45.0, 60.0, 32, 20, 45, 10.0, 9.0)",
        "INSERT INTO drone_models VALUES ('M3', 'Model 3', 'x', 3.0, 20.0, 14.0, "
        "45.0, 40.0, 32, 20, 45, 10.0, 9.0)",
    ]
    for statement in invalid_inserts:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql(statement)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(drone.format(model="M1", hub="h1", status="IDLE", battery=50))
    engine.dispose()
