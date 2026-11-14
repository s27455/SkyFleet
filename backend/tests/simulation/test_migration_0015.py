"""Migration 0015: order-less missions, the mission purpose, the RELOCATING phase and event type."""

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
    "INSERT INTO drones VALUES ('D2', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('O1', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'READY_FOR_PICKUP')",
    "INSERT INTO missions (id, order_id, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('MIS-1', 'O1', 'D1', 'h1', 'h1', 'COMPLETED', "
    "1.0, 1.0, 2.0, 10.0, 11.0)",
)
RELOCATION = (
    "INSERT INTO missions (id, order_id, purpose, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('{id}', NULL, 'RELOCATION', '{drone}', 'h1', 'h1', "
    "'{status}', 1.0, 0.0, 1.0, 5.0, 5.0)"
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _upgraded(tmp_path: Path):  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0014")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))
    return url, config, engine


def test_upgrade_marks_existing_missions_as_deliveries_and_accepts_a_relocation(
    tmp_path: Path,
) -> None:
    _, config, engine = _upgraded(tmp_path)
    assert "purpose" not in {c["name"] for c in inspect(engine).get_columns("missions")}

    command.upgrade(config, "0015")

    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, order_id, purpose FROM missions"))
        assert [tuple(row) for row in rows] == [("MIS-1", "O1", "DELIVERY")]
        connection.execute(text(RELOCATION.format(id="MIS-R", drone="D2", status="IN_FLIGHT")))
    columns = {c["name"]: c for c in inspect(engine).get_columns("missions")}
    assert columns["order_id"]["nullable"] is True


def test_purpose_and_order_must_agree(tmp_path: Path) -> None:
    _, config, engine = _upgraded(tmp_path)
    command.upgrade(config, "0015")
    delivery_without_order = RELOCATION.replace("'RELOCATION'", "'DELIVERY'").format(
        id="MIS-X", drone="D2", status="COMPLETED"
    )
    relocation_with_order = RELOCATION.replace("NULL, 'RELOCATION'", "'O1', 'RELOCATION'").format(
        id="MIS-Y", drone="D2", status="COMPLETED"
    )
    unknown_purpose = RELOCATION.replace("'RELOCATION', '{drone}'", "'OTHER', '{drone}'").format(
        id="MIS-Z", drone="D2", status="COMPLETED"
    )
    for statement in (delivery_without_order, relocation_with_order, unknown_purpose):
        with engine.connect() as connection, pytest.raises(IntegrityError):
            connection.execute(text(statement))


def test_the_active_unique_indexes_survive_and_still_protect_a_drone(tmp_path: Path) -> None:
    _, config, engine = _upgraded(tmp_path)
    command.upgrade(config, "0015")
    names = {index["name"] for index in inspect(engine).get_indexes("missions")}
    assert {"uq_missions_active_order", "uq_missions_active_drone"} <= names
    with engine.begin() as connection:
        connection.execute(text(RELOCATION.format(id="MIS-R", drone="D2", status="IN_FLIGHT")))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(RELOCATION.format(id="MIS-S", drone="D2", status="ASSIGNED")))


def test_the_new_phase_and_event_type_are_accepted(tmp_path: Path) -> None:
    _, config, engine = _upgraded(tmp_path)
    command.upgrade(config, "0015")
    with engine.begin() as connection:
        connection.execute(text(RELOCATION.format(id="MIS-R", drone="D2", status="IN_FLIGHT")))
        connection.execute(
            text(
                "INSERT INTO mission_flights (mission_id, phase, started_at, start_battery_pct, "
                "battery_pct, legs, pace_s_per_km, planned_return_hub_id, landing_target_hub_id, "
                "tried_hub_ids, longitude, latitude, progress) VALUES ('MIS-R', 'RELOCATING', "
                "'2026-11-12 10:00:00', 90.0, 90.0, '[]', 100.0, 'h1', 'h1', '[]', 18.0, 54.0, 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO operational_events (event_type, occurred_at, origin, mission_id) "
                "VALUES ('DRONE_RELOCATION', '2026-11-12 10:00:00', 'MANUAL', 'MIS-R')"
            )
        )


def test_downgrade_restores_the_old_schema_when_no_relocation_exists(tmp_path: Path) -> None:
    _, config, engine = _upgraded(tmp_path)
    command.upgrade(config, "0015")

    command.downgrade(config, "0014")

    columns = {c["name"]: c for c in inspect(engine).get_columns("missions")}
    assert "purpose" not in columns and columns["order_id"]["nullable"] is False
    names = {index["name"] for index in inspect(engine).get_indexes("missions")}
    assert {"uq_missions_active_order", "uq_missions_active_drone"} <= names
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE mission_flights SET phase = 'RELOCATING'"))
        connection.execute(
            text(
                "INSERT INTO operational_events (event_type, occurred_at, origin) "
                "VALUES ('DRONE_RELOCATION', '2026-11-12 10:00:00', 'MANUAL')"
            )
        )


def test_downgrade_refuses_while_a_relocation_exists(tmp_path: Path) -> None:
    _, config, engine = _upgraded(tmp_path)
    command.upgrade(config, "0015")
    with engine.begin() as connection:
        connection.execute(text(RELOCATION.format(id="MIS-R", drone="D2", status="COMPLETED")))

    with pytest.raises(IntegrityError):
        command.downgrade(config, "0014")
