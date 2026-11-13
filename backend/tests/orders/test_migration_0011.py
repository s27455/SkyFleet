"""Migration 0011: the CANCELLED status and the cancellation and recall timestamps (SQLite)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
ORDER = (
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('{oid}', 'h1', 'x', 18.0, 54.0, "
    "1.0, '{status}')"
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_keeps_existing_rows_and_accepts_cancelled(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0010")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(HUB))
        connection.execute(text(ORDER.format(oid="O1", status="DELIVERED")))
        connection.execute(text(ORDER.format(oid="O2", status="READY_FOR_PICKUP")))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(ORDER.format(oid="O3", status="CANCELLED")))

    command.upgrade(config, "0011")

    inspector = inspect(engine)
    assert "cancelled_at" in {c["name"] for c in inspector.get_columns("orders")}
    assert "recalled_at" in {c["name"] for c in inspector.get_columns("mission_flights")}
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, status, cancelled_at FROM orders ORDER BY id"))
        assert [tuple(row) for row in rows] == [
            ("O1", "DELIVERED", None),
            ("O2", "READY_FOR_PICKUP", None),
        ]
        connection.execute(text(ORDER.format(oid="O3", status="CANCELLED")))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(ORDER.format(oid="O4", status="NOT_A_STATUS")))


def test_downgrade_restores_the_columns_and_the_narrower_status_check(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0011")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(HUB))
        connection.execute(text(ORDER.format(oid="O1", status="READY_FOR_PICKUP")))

    command.downgrade(config, "0010")

    inspector = inspect(engine)
    assert "cancelled_at" not in {c["name"] for c in inspector.get_columns("orders")}
    assert "recalled_at" not in {c["name"] for c in inspector.get_columns("mission_flights")}
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM orders")).scalar() == 1
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text(ORDER.format(oid="O2", status="CANCELLED")))
