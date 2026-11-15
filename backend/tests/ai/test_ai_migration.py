"""Migration 0019 (AI budget): the head, and equal to the ORM models.

The migration is executed here only against a throwaway in-memory SQLite database. No real database
is touched.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect

from app.ai import models  # noqa: F401  (registers the tables)
from app.db.session import Base

BACKEND = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND / "migrations" / "versions" / "0019_ai_budget.py"
TABLES = ("ai_budget_state", "ai_request_log")


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0019_ai_budget", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scratch() -> Engine:
    return create_engine("sqlite://")  # an empty in-memory database, gone after the test


def run(engine: Engine, step: str) -> None:
    migration = load_migration()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(migration, step)()


def test_0019_is_the_single_alembic_head() -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["0019"]
    assert script.get_revision("0019").down_revision == "0018"
    assert not (BACKEND / "migrations" / "migrations").exists()


def test_0019_declares_the_next_revision() -> None:
    migration = load_migration()

    assert (migration.revision, migration.down_revision) == ("0019", "0018")


def test_0019_creates_the_same_tables_as_the_models(scratch: Engine) -> None:
    run(scratch, "upgrade")
    schema = inspect(scratch)

    assert set(schema.get_table_names()) == set(TABLES)  # and nothing else
    for name in TABLES:
        model = Base.metadata.tables[name]
        migration_columns = {c["name"]: c for c in schema.get_columns(name)}
        assert set(migration_columns) == {c.name for c in model.columns}, name
        for column in model.columns:
            assert migration_columns[column.name]["nullable"] == column.nullable, (
                name,
                column.name,
            )
        assert schema.get_pk_constraint(name)["constrained_columns"] == [
            c.name for c in model.primary_key.columns
        ]
        assert {i["name"] for i in schema.get_indexes(name)} == {i.name for i in model.indexes}
        assert {c["name"] for c in schema.get_check_constraints(name)} == {
            c.name for c in model.constraints if c.__class__.__name__ == "CheckConstraint"
        }


def test_0019_enforces_the_same_rules_as_the_models(scratch: Engine) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    run(scratch, "upgrade")
    insert_log = (
        "INSERT INTO ai_request_log (created_at, model, status, request_bytes, reserved_nano_usd, "
        "charged_nano_usd) VALUES ('2026-11-20 12:00:00', 'm', '{status}', 1, {reserved}, 0)"
    )
    with scratch.begin() as connection:
        connection.execute(text(insert_log.format(status="RESERVED", reserved=5)))
    for bad in (
        insert_log.format(status="BOGUS", reserved=5),
        insert_log.format(status="RESERVED", reserved=-1),
    ):
        with scratch.connect() as connection, pytest.raises(IntegrityError):
            connection.execute(text(bad))
    with scratch.connect() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO ai_budget_state (name, spent_nano_usd, reserved_nano_usd, halted, "
                "updated_at) VALUES ('x', -1, 0, 0, '2026-11-20 12:00:00')"
            )
        )


def test_0019_downgrade_removes_exactly_its_tables(scratch: Engine) -> None:
    run(scratch, "upgrade")
    run(scratch, "downgrade")

    assert inspect(scratch).get_table_names() == []


def test_0019_does_not_touch_any_existing_table() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert source.count("op.create_table(") == 2
    for forbidden in ("op.alter_column", "op.drop_column", "batch_alter_table", "op.execute"):
        assert forbidden not in source
