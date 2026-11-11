"""Migration 0004 adds the missions table without touching existing data."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
MODEL = (
    "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'hexacopter', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
)
DRONES = (
    "INSERT INTO drones VALUES ('D1', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
    "INSERT INTO drones VALUES ('D2', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
)
ORDERS = tuple(
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    f"destination_latitude, package_weight_kg, status) VALUES ('{oid}', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'READY_FOR_PICKUP')"
    for oid in ("O1", "O2")
)
MISSION = (
    "INSERT INTO missions (id, order_id, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('{mid}', '{order}', '{drone}', 'h1', 'h1', '{status}', "
    "1.0, 1.0, 2.0, 10.0, 11.0)"
)


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def seed_prerequisites(engine: Engine) -> None:
    with engine.begin() as connection:
        for statement in (HUB, MODEL, *DRONES, *ORDERS):
            connection.exec_driver_sql(statement)


def test_upgrade_adds_missions_and_keeps_hubs_drones_and_orders(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "0003")
    engine = create_engine(url)
    seed_prerequisites(engine)

    command.upgrade(config, "0004")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM hubs").scalar() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM drones").scalar() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM orders").scalar() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM missions").scalar() == 0
    engine.dispose()


def test_downgrade_to_0003_drops_only_missions(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "head")

    command.downgrade(config, "0003")

    engine = create_engine(url)
    present = tables(engine)
    engine.dispose()
    assert {"hubs", "drones", "drone_models", "orders"} <= present
    assert "missions" not in present


def test_migrated_missions_table_enforces_constraints_and_active_uniqueness(
    tmp_path: Path,
) -> None:
    """compare_metadata ignores CHECKs, so exercise the migration's own DDL."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(make_config(url), "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    seed_prerequisites(engine)

    def run(statement: str) -> None:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.exec_driver_sql(statement)

    base = {"order": "O1", "drone": "D1", "status": "ASSIGNED"}
    invalid = [
        MISSION.format(mid="M1", **{**base, "status": "PENDING"}),
        MISSION.format(mid="M1", **{**base, "order": "O-missing"}),
        MISSION.format(mid="M1", **{**base, "drone": "D-missing"}),
        MISSION.replace("1.0, 1.0, 2.0", "-1.0, 1.0, 2.0").format(mid="M1", **base),
    ]
    for statement in invalid:
        with pytest.raises(IntegrityError):
            run(statement)

    run(MISSION.format(mid="M1", **base))
    with pytest.raises(IntegrityError):  # same order, other drone
        run(MISSION.format(mid="M2", order="O1", drone="D2", status="IN_FLIGHT"))
    with pytest.raises(IntegrityError):  # same drone, other order
        run(MISSION.format(mid="M2", order="O2", drone="D1", status="ASSIGNED"))
    run(MISSION.format(mid="M3", order="O1", drone="D1", status="CANCELLED"))  # history is fine
    run(MISSION.format(mid="M4", order="O2", drone="D2", status="ASSIGNED"))  # other pair is fine
    engine.dispose()
