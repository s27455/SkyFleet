"""Migration 0003 adds the orders table without touching existing Hubs and drones."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
MODEL = (
    "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'hexacopter', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
)
DRONE = "INSERT INTO drones VALUES ('D1', 'M1', 'h1', 'IDLE', 50, 18.0, 54.0)"


def test_upgrade_adds_orders_and_keeps_existing_hubs_and_drones(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "0002")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(HUB)
        connection.exec_driver_sql(MODEL)
        connection.exec_driver_sql(DRONE)

    command.upgrade(config, "0003")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM hubs").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM drones").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM orders").scalar() == 0
    engine.dispose()


def test_downgrade_to_0002_drops_only_orders(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "head")

    command.downgrade(config, "0002")

    engine = create_engine(url)
    with engine.connect() as connection:
        tables = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    engine.dispose()
    assert {"hubs", "drones", "drone_models"} <= tables
    assert "orders" not in tables


def test_migrated_orders_table_enforces_its_own_constraints(tmp_path: Path) -> None:
    """compare_metadata ignores CHECK constraints, so exercise the migration's own DDL."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(make_config(url), "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(HUB)

    order = (
        "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
        "destination_latitude, package_weight_kg, status) "
        "VALUES ('O1', '{hub}', '{address}', {lng}, {lat}, {weight}, '{status}')"
    )
    valid = {
        "hub": "h1",
        "address": "ul. Test 1",
        "lng": 18.0,
        "lat": 54.0,
        "weight": 1.0,
        "status": "READY_FOR_PICKUP",
    }
    invalid_changes: list[dict[str, object]] = [
        {"hub": "missing"},
        {"address": "   "},
        {"lng": 181.0},
        {"lat": -91.0},
        {"weight": 0},
        {"weight": -1},
        {"weight": 3.01},
        {"status": "PENDING"},
    ]
    for change in invalid_changes:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql(order.format(**{**valid, **change}))

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(order.format(**{**valid, "weight": 3.0}))
        row = connection.exec_driver_sql("SELECT created_at, updated_at FROM orders").one()
    engine.dispose()
    assert row[0] is not None
    assert row[1] is not None
