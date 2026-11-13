"""Migration 0013: the DELIVERY_FAILED status and the failed-delivery columns."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

SETUP = (
    "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)",
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('O1', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'DELIVERED')",
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('O2', 'h1', 'x', 18.0, 54.0, "
    "1.0, 'CANCELLED')",
)


def _config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_accepts_the_new_status_adds_the_columns_and_keeps_orders(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0012")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE orders SET status = 'DELIVERY_FAILED' WHERE id = 'O1'"))

    command.upgrade(config, "0013")

    inspector = inspect(engine)
    assert "delivery_failed_at" in {c["name"] for c in inspector.get_columns("orders")}
    flight_columns = {c["name"] for c in inspector.get_columns("mission_flights")}
    assert {
        "recipient_unavailable_at",
        "handover_failed_at",
        "recipient_unavailable_origin",
    } <= flight_columns
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT id, status, delivery_failed_at FROM orders"))
        # Existing rows are untouched: nothing is backfilled or rewritten.
        assert sorted(tuple(row) for row in rows) == [
            ("O1", "DELIVERED", None),
            ("O2", "CANCELLED", None),
        ]
        connection.execute(text("UPDATE orders SET status = 'DELIVERY_FAILED' WHERE id = 'O1'"))
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE orders SET status = 'NOT_A_STATUS'"))


def test_downgrade_removes_the_columns_and_restores_the_narrower_check(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    config = _config(url)
    command.upgrade(config, "0013")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in SETUP:
            connection.execute(text(statement))

    command.downgrade(config, "0012")

    inspector = inspect(engine)
    assert "delivery_failed_at" not in {c["name"] for c in inspector.get_columns("orders")}
    flight_columns = {c["name"] for c in inspector.get_columns("mission_flights")}
    assert (
        not {
            "recipient_unavailable_at",
            "handover_failed_at",
            "recipient_unavailable_origin",
        }
        & flight_columns
    )
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM orders")).scalar() == 2
    with engine.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(text("UPDATE orders SET status = 'DELIVERY_FAILED' WHERE id = 'O1'"))
