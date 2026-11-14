"""Migration 0016 on SQLite: the seeded inactive rain warning and the widened event CHECK."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]
EVENT = (
    "INSERT INTO operational_events (event_type, origin, occurred_at) "
    "VALUES ('{kind}', 'MANUAL', '2026-11-12 10:00:00')"
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_seeds_an_inactive_warning_and_accepts_the_new_events(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0015")
    engine = create_engine(url)
    assert "weather_state" not in inspect(engine).get_table_names()
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text(EVENT.format(kind="RAIN_WARNING_ACTIVATED")))

    command.upgrade(config, "0016")

    with engine.begin() as connection:
        row = connection.execute(text("SELECT name, active FROM weather_state")).one()
        assert tuple(row) == ("rain-warning", 0)
        connection.execute(text(EVENT.format(kind="RAIN_WARNING_ACTIVATED")))
        connection.execute(text(EVENT.format(kind="RAIN_WARNING_CLEARED")))


def test_downgrade_drops_the_table_once_the_rain_events_are_gone(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0016")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(EVENT.format(kind="RAIN_WARNING_CLEARED")))
    with engine.begin() as connection:  # the narrower CHECK would refuse them (documented)
        connection.execute(text("DELETE FROM operational_events WHERE event_type LIKE 'RAIN_%'"))
    command.downgrade(config, "0015")

    assert "weather_state" not in inspect(engine).get_table_names()
