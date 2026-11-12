"""Migration 0005: flights, heartbeat and the wider order and mission status checks (SQLite)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[2]

HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
MODEL = (
    "INSERT INTO drone_models VALUES ('M1', 'Model 1', 'hexacopter', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
)
DRONES = (
    "INSERT INTO drones VALUES ('D1', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
    "INSERT INTO drones VALUES ('D2', 'M1', 'h1', 'IDLE', 90, 18.0, 54.0)",
)
ORDER = (
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status) VALUES ('{oid}', 'h1', 'x', 18.0, 54.0, "
    "1.0, '{status}')"
)
MISSION = (
    "INSERT INTO missions (id, order_id, drone_id, origin_hub_id, return_hub_id, status, "
    "origin_to_destination_km, destination_to_return_km, total_km, expected_energy_pct, "
    "worst_case_energy_pct) VALUES ('{mid}', '{order}', '{drone}', 'h1', 'h1', '{status}', "
    "1.0, 1.0, 2.0, 10.0, 11.0)"
)


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def run(engine: Engine, statement: str) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql(statement)


def prepare_0004(tmp_path: Path) -> tuple[Config, Engine]:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "0004")
    engine = create_engine(url)
    for statement in (
        HUB,
        MODEL,
        *DRONES,
        ORDER.format(oid="O1", status="READY_FOR_PICKUP"),
        ORDER.format(oid="O2", status="READY_FOR_PICKUP"),
        MISSION.format(mid="M1", order="O1", drone="D1", status="ASSIGNED"),
        MISSION.format(mid="M2", order="O1", drone="D1", status="CANCELLED"),
    ):
        run(engine, statement)
    return config, engine


def test_upgrade_keeps_existing_data_and_adds_the_new_tables(tmp_path: Path) -> None:
    config, engine = prepare_0004(tmp_path)

    command.upgrade(config, "0005")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM orders").scalar() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM missions").scalar() == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM drones").scalar() == 2
    assert {"mission_flights", "simulation_heartbeats"} <= tables(engine)
    engine.dispose()


def test_the_new_order_and_mission_statuses_are_accepted_and_others_still_rejected(
    tmp_path: Path,
) -> None:
    config, engine = prepare_0004(tmp_path)
    command.upgrade(config, "0005")

    for status in ("OUT_FOR_DELIVERY", "DELIVERED"):
        run(engine, ORDER.format(oid=f"X-{status[:3]}", status=status))
    with pytest.raises(IntegrityError):
        run(engine, ORDER.format(oid="X-BAD", status="PENDING"))
    run(engine, MISSION.format(mid="M3", order="O2", drone="D2", status="COMPLETED"))
    run(engine, MISSION.format(mid="M4", order="O2", drone="D2", status="EMERGENCY"))
    with pytest.raises(IntegrityError):
        run(engine, MISSION.format(mid="M5", order="O2", drone="D2", status="FLYING"))
    engine.dispose()


def test_the_active_mission_uniqueness_and_foreign_keys_survive_the_table_rebuild(
    tmp_path: Path,
) -> None:
    config, engine = prepare_0004(tmp_path)
    command.upgrade(config, "0005")

    with pytest.raises(IntegrityError):  # a second active mission for the order
        run(engine, MISSION.format(mid="M9", order="O1", drone="D2", status="IN_FLIGHT"))
    with pytest.raises(IntegrityError):  # a second active mission for the drone
        run(engine, MISSION.format(mid="M9", order="O2", drone="D1", status="ASSIGNED"))
    run(engine, MISSION.format(mid="M9", order="O2", drone="D2", status="ASSIGNED"))
    run(engine, MISSION.format(mid="M10", order="O2", drone="D2", status="COMPLETED"))
    with pytest.raises(IntegrityError):  # the foreign keys still point at real rows
        run(engine, MISSION.format(mid="M11", order="O-missing", drone="D1", status="CANCELLED"))
    engine.dispose()


def test_the_flight_table_enforces_its_constraints(tmp_path: Path) -> None:
    config, engine = prepare_0004(tmp_path)
    command.upgrade(config, "0005")
    flight = (
        "INSERT INTO mission_flights (mission_id, phase, started_at, start_battery_pct, "
        "battery_pct, legs, pace_s_per_km, planned_return_hub_id, landing_target_hub_id, "
        "tried_hub_ids, longitude, latitude, progress{extra_columns}) VALUES ('M1', '{phase}', "
        "'2026-11-12 10:00:00', 100.0, 100.0, '[]', {pace}, 'h1', 'h1', '[]', 18.0, 54.0, "
        "{progress}{extra_values})"
    )

    def sql(
        phase: str = "OUTBOUND",
        pace: float = 40.0,
        progress: float = 0.0,
        reason: str | None = None,
    ) -> str:
        extra_columns = ", emergency_reason" if reason else ""
        extra_values = f", '{reason}'" if reason else ""
        return flight.format(
            phase=phase,
            pace=pace,
            progress=progress,
            extra_columns=extra_columns,
            extra_values=extra_values,
        )

    for bad in (sql(phase="HOVERING"), sql(pace=0), sql(progress=1.5), sql(reason="CRASH")):
        with pytest.raises(IntegrityError):
            run(engine, bad)
    run(engine, sql())
    with pytest.raises(IntegrityError):  # one flight per mission
        run(engine, sql())
    engine.dispose()


def test_downgrade_removes_the_new_tables_and_restores_the_narrow_checks(tmp_path: Path) -> None:
    config, engine = prepare_0004(tmp_path)
    command.upgrade(config, "0005")

    command.downgrade(config, "0004")

    assert not {"mission_flights", "simulation_heartbeats"} & tables(engine)
    with pytest.raises(IntegrityError):
        run(engine, ORDER.format(oid="X1", status="DELIVERED"))
    with pytest.raises(IntegrityError):
        run(engine, MISSION.format(mid="M7", order="O2", drone="D2", status="COMPLETED"))
    with pytest.raises(IntegrityError):  # the partial index is back, not a full unique index
        run(engine, MISSION.format(mid="M8", order="O1", drone="D2", status="ASSIGNED"))
    run(engine, MISSION.format(mid="M8", order="O2", drone="D2", status="ASSIGNED"))
    command.upgrade(config, "0005")  # and it can go up again
    engine.dispose()
