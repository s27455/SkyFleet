"""Migration 0006: the automatic dispatch state table (SQLite)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def table_names(url: str) -> set[str]:
    with create_engine(url).connect() as connection:
        return {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def test_the_table_is_created_empty_and_removed_again(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)

    command.upgrade(config, "0005")
    assert "dispatch_auto_state" not in table_names(url)

    command.upgrade(config, "0006")
    assert "dispatch_auto_state" in table_names(url)
    with create_engine(url).connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM dispatch_auto_state").scalar() == 0

    command.downgrade(config, "0005")
    assert "dispatch_auto_state" not in table_names(url)


def test_a_new_row_defaults_to_off(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(make_config(url), "0006")
    engine = create_engine(url)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO dispatch_auto_state (name, updated_at) VALUES ('x', '2026-11-12')"
        )
    with engine.connect() as connection:
        enabled = connection.exec_driver_sql("SELECT enabled FROM dispatch_auto_state").scalar()

    assert enabled == 0
