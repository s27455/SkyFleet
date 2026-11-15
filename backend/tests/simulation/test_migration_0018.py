"""Migration 0018: incident acknowledgements and the DRONE_RECOVERED event type (Feature 022)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

EVENT = (
    "INSERT INTO operational_events (event_type, occurred_at, origin, dedupe_key) "
    "VALUES ('{kind}', '2026-11-15 10:00:00', 'AUTOMATIC', '{key}')"
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_adds_the_table_and_accepts_the_new_event_type(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0017")
    engine = create_engine(url)
    assert "incident_acknowledgements" not in inspect(engine).get_table_names()
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(EVENT.format(kind="DRONE_RECOVERED", key="k0")))

    command.upgrade(config, "0018")

    columns = {c["name"]: c for c in inspect(engine).get_columns("incident_acknowledgements")}
    assert set(columns) == {"mission_id", "acknowledged_at"}
    assert columns["acknowledged_at"]["nullable"] is False
    assert inspect(engine).get_pk_constraint("incident_acknowledgements")[
        "constrained_columns"
    ] == ["mission_id"]
    with engine.begin() as connection:
        connection.execute(text(EVENT.format(kind="DRONE_RECOVERED", key="k1")))
        connection.execute(text(EVENT.format(kind="DRONE_FAILURE", key="k2")))  # still valid
    with engine.connect() as connection, pytest.raises(IntegrityError):  # the key stays unique
        connection.execute(text(EVENT.format(kind="DRONE_RECOVERED", key="k1")))
    with engine.connect() as connection, pytest.raises(IntegrityError):  # and the CHECK is closed
        connection.execute(text(EVENT.format(kind="SOMETHING_ELSE", key="k3")))


def test_downgrade_refuses_while_a_recovery_event_exists(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0018")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(EVENT.format(kind="DRONE_RECOVERED", key="k1")))

    with pytest.raises(IntegrityError):
        command.downgrade(config, "0017")


def test_downgrade_restores_the_old_schema_when_no_recovery_event_exists(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0018")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(EVENT.format(kind="DRONE_FAILURE", key="k1")))

    command.downgrade(config, "0017")

    assert "incident_acknowledgements" not in inspect(engine).get_table_names()
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(EVENT.format(kind="DRONE_RECOVERED", key="k9")))
