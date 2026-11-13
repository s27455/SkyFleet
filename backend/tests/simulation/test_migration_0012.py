"""Migration 0012: the failure flag, the EMERGENCY_APPROACH phase and the DRONE_FAILURE reason."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

SETUP = (
    "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)",
    "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'quadcopter', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)",
    "INSERT INTO drones VALUES ('D1', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('O1', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'READY_FOR_PICKUP')",
    "INSERT INTO missions (id, order_id, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('MIS-1', 'O1', 'D1', 'h1', 'h1', 'COMPLETED', "
    "1.0, 1.0, 2.0, 10.0, 11.0)",
)
FLIGHT = (
    "INSERT INTO mission_flights (mission_id, phase, started_at, emergency_reason, "
    "start_battery_pct, battery_pct, legs, pace_s_per_km, planned_return_hub_id, "
    "landing_target_hub_id, tried_hub_ids, longitude, latitude, progress) VALUES ('MIS-1', "
    "'{phase}', '2026-11-12 10:00:00', {reason}, 100.0, 90.0, '[]', 100.0, 'h1', 'h1', '[]', "
    "18.0, 54.0, 1)"
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_accepts_the_new_values_and_keeps_existing_flights(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0011")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))
        connection.execute(text(FLIGHT.format(phase="LANDED", reason="NULL")))
        connection.execute(text("DELETE FROM mission_flights"))
        connection.execute(text(FLIGHT.format(phase="LANDED", reason="NULL")))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE mission_flights SET phase = 'EMERGENCY_APPROACH'"))

    command.upgrade(config, "0012")

    assert "failed_at" in {c["name"] for c in inspect(engine).get_columns("mission_flights")}
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT mission_id, phase, failed_at FROM mission_flights"))
        assert [tuple(row) for row in rows] == [("MIS-1", "LANDED", None)]
        connection.execute(text("UPDATE mission_flights SET phase = 'EMERGENCY_APPROACH'"))
        connection.execute(
            text(
                "UPDATE mission_flights SET phase = 'EMERGENCY', emergency_reason = 'DRONE_FAILURE'"
            )
        )
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE mission_flights SET phase = 'NOT_A_PHASE'"))


def test_downgrade_removes_the_column_and_restores_the_narrower_checks(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0012")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))
        connection.execute(text(FLIGHT.format(phase="LANDED", reason="NULL")))

    command.downgrade(config, "0011")

    assert "failed_at" not in {c["name"] for c in inspect(engine).get_columns("mission_flights")}
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM mission_flights")).scalar() == 1
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE mission_flights SET phase = 'EMERGENCY_APPROACH'"))
