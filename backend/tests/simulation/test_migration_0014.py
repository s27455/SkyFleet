"""Migration 0014: the LPR helicopter scenarios table."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

ROW = (
    "INSERT INTO lpr_scenarios (id, status, origin, started_at, ends_at, start_longitude, "
    "start_latitude, end_longitude, end_latitude, speed_ms, radius_m, margin_m, clear_extra_m) "
    "VALUES ('{id}', '{status}', 'MANUAL', '2026-11-12 10:00:00', '2026-11-12 10:03:00', "
    "18.46, 54.39, 18.67, 54.39, 80, 500, 250, 100)"
)
SETUP = (
    "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)",
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('O1', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'DELIVERY_FAILED')",
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_adds_the_table_and_keeps_existing_data(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0013")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))
    assert "lpr_scenarios" not in inspect(engine).get_table_names()

    command.upgrade(config, "0014")

    assert "lpr_scenarios" in inspect(engine).get_table_names()
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, status FROM orders")).all()
        assert [tuple(row) for row in rows] == [("O1", "DELIVERY_FAILED")]  # untouched
        assert connection.execute(text("SELECT count(*) FROM lpr_scenarios")).scalar() == 0


def test_the_database_allows_one_active_scenario_and_any_number_of_finished_ones(
    tmp_path: Path,
) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    command.upgrade(_config(url), "0014")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(ROW.format(id="LPR-1", status="ACTIVE")))
        connection.execute(text(ROW.format(id="LPR-2", status="COMPLETED")))
        connection.execute(text(ROW.format(id="LPR-3", status="COMPLETED")))

    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(ROW.format(id="LPR-4", status="ACTIVE")))  # a second active one
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(ROW.format(id="LPR-5", status="PAUSED")))  # an unknown status


def test_downgrade_drops_only_the_table(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0014")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))

    command.downgrade(config, "0013")

    assert "lpr_scenarios" not in inspect(engine).get_table_names()
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM orders")).scalar() == 1
