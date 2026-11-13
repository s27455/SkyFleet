"""Migration 0010: operational_events is created, is additive and downgrades cleanly (SQLite)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_adds_the_table_and_downgrade_removes_it(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0009")
    engine = create_engine(url)
    assert "operational_events" not in inspect(engine).get_table_names()

    command.upgrade(config, "0010")
    inspector = inspect(engine)
    assert "operational_events" in inspector.get_table_names()
    index_names = {index["name"] for index in inspector.get_indexes("operational_events")}
    assert {"ix_operational_events_order", "ix_operational_events_mission"} <= index_names
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM operational_events")).scalar() == 0

    command.downgrade(config, "0009")
    assert "operational_events" not in inspect(engine).get_table_names()
