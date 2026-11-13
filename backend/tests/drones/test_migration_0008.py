"""Migration 0008: SF-1 airframe becomes a quadcopter, guarded, data only (SQLite)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]

MODEL = (
    "INSERT INTO drone_models VALUES ('{id}', '{name}', '{airframe}', 3.0, 20.0, 14.0, "
    "45.0, 60.0, 32, 20, 45, 10.0, 9.0)"
)
HUB = "INSERT INTO hubs (id, name, address, longitude, latitude) VALUES ('h1', 'H1', 'a', 18, 54)"
DRONE = "INSERT INTO drones VALUES ('D1', 'SF-1', 'h1', 'IDLE', 90, 18.0, 54.0)"


def make_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def prepare(tmp_path: Path, *statements: str) -> tuple[Config, Engine]:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = make_config(url)
    command.upgrade(config, "0007")
    engine = create_engine(url)
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
    return config, engine


def airframes(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        return dict(
            connection.exec_driver_sql("SELECT id, airframe_type FROM drone_models").fetchall()
        )


def test_sf1_hexacopter_becomes_quadcopter_and_nothing_else_changes(tmp_path: Path) -> None:
    config, engine = prepare(
        tmp_path,
        MODEL.format(id="SF-1", name="SkyFleet SF-1 Courier", airframe="hexacopter"),
        HUB,
        DRONE,
    )
    with engine.connect() as connection:
        before = connection.exec_driver_sql(
            "SELECT id, name, max_payload_kg, nominal_flight_time_min, empty_weight_kg "
            "FROM drone_models"
        ).fetchall()

    command.upgrade(config, "0008")

    assert airframes(engine) == {"SF-1": "quadcopter"}
    with engine.connect() as connection:
        after = connection.exec_driver_sql(
            "SELECT id, name, max_payload_kg, nominal_flight_time_min, empty_weight_kg "
            "FROM drone_models"
        ).fetchall()
        assert connection.exec_driver_sql("SELECT id, model_id FROM drones").fetchall() == [
            ("D1", "SF-1")
        ]
    assert after == before


def test_a_deliberately_changed_value_and_other_models_are_not_overwritten(tmp_path: Path) -> None:
    config, engine = prepare(
        tmp_path,
        MODEL.format(id="SF-1", name="SF-1", airframe="octocopter"),
        MODEL.format(id="X-9", name="X-9", airframe="hexacopter"),
    )

    command.upgrade(config, "0008")

    assert airframes(engine) == {"SF-1": "octocopter", "X-9": "hexacopter"}


def test_downgrade_restores_the_old_value(tmp_path: Path) -> None:
    config, engine = prepare(tmp_path, MODEL.format(id="SF-1", name="SF-1", airframe="hexacopter"))
    command.upgrade(config, "0008")

    command.downgrade(config, "0007")

    assert airframes(engine) == {"SF-1": "hexacopter"}
