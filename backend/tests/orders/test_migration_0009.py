"""Migration 0009: orders.delivered_at with a backfill from the flights (SQLite)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]

HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
MODEL = (
    "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'quadcopter', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
)
DRONE = "INSERT INTO drones VALUES ('D1', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)"
ORDER = (
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('{oid}', 'h1', 'x', 18.0, 54.0, "
    "1.0, '{status}')"
)
MISSION = (
    "INSERT INTO missions (id, order_id, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('{mid}', '{order}', 'D1', 'h1', 'h1', '{status}', "
    "1.0, 1.0, 2.0, 10.0, 11.0)"
)
FLIGHT = (
    "INSERT INTO mission_flights (mission_id, phase, started_at, delivered_at, start_battery_pct, "
    "battery_pct, legs, pace_s_per_km, planned_return_hub_id, landing_target_hub_id, "
    "tried_hub_ids, longitude, latitude, progress) VALUES ('{mid}', 'LANDED', "
    "'2026-11-12 10:00:00', {delivered}, 100.0, 90.0, '[]', 100.0, 'h1', 'h1', '[]', 18.0, 54.0, 1)"
)


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def prepare(tmp_path: Path) -> tuple[Config, Engine]:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "0008")
    engine = create_engine(url)
    statements = (
        HUB,
        MODEL,
        DRONE,
        ORDER.format(oid="O-FLOWN", status="DELIVERED"),  # delivered, flight knows when
        ORDER.format(oid="O-LEGACY", status="DELIVERED"),  # delivered, no flight at all
        ORDER.format(oid="O-READY", status="READY_FOR_PICKUP"),
        MISSION.format(mid="M1", order="O-FLOWN", status="COMPLETED"),
        FLIGHT.format(mid="M1", delivered="'2026-11-12 10:00:30'"),
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    return config, engine


def delivered_at(engine: Engine) -> dict[str, str | None]:
    with engine.connect() as connection:
        return dict(
            connection.exec_driver_sql("SELECT id, delivered_at FROM orders ORDER BY id").fetchall()
        )


def test_upgrade_backfills_from_the_flight_and_invents_nothing(tmp_path: Path) -> None:
    config, engine = prepare(tmp_path)

    command.upgrade(config, "0009")

    values = delivered_at(engine)
    assert str(values["O-FLOWN"]).startswith("2026-11-12 10:00:30")
    assert values["O-LEGACY"] is None  # no flight: stays unknown, hidden from the active view
    assert values["O-READY"] is None
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM orders").scalar() == 3
    engine.dispose()


def test_downgrade_drops_the_column_and_keeps_every_order(tmp_path: Path) -> None:
    config, engine = prepare(tmp_path)
    command.upgrade(config, "0009")

    command.downgrade(config, "0008")

    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(orders)")}
        assert "delivered_at" not in columns
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM orders").scalar() == 3
    engine.dispose()
