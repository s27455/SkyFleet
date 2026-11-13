"""drone failure and emergency landing (Feature 018C)

Revision ID: 0012
Revises: 0011

Adds the nullable `mission_flights.failed_at`, widens `phase` to 24 characters (the new value
`EMERGENCY_APPROACH` has 18) and widens two CHECK constraints: the flight phase
with `EMERGENCY_APPROACH` and the emergency reason with `DRONE_FAILURE`. No row is touched: no data
is backfilled, deleted or rewritten. The downgrade restores the narrower constraints, which
intentionally fails while a flight uses a new value, and drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

PHASES_OLD = "'OUTBOUND', 'DELIVERING', 'RETURNING', 'DIVERTING', 'LANDED', 'EMERGENCY'"
PHASES_NEW = PHASES_OLD + ", 'EMERGENCY_APPROACH'"
REASONS_OLD = "'NO_HUB_WITH_CAPACITY', 'BATTERY_INSUFFICIENT', 'BATTERY_CRITICAL'"
REASONS_NEW = REASONS_OLD + ", 'DRONE_FAILURE'"


def _set_checks(phases: str, reasons: str, phase_length: int) -> None:
    # Batch mode recreates the table on SQLite and alters in place on PostgreSQL.
    with op.batch_alter_table("mission_flights") as batch:
        batch.alter_column(
            "phase",
            existing_type=sa.String(),
            type_=sa.String(phase_length),
            existing_nullable=False,
        )
        batch.drop_constraint("ck_mission_flights_phase_valid", type_="check")
        batch.drop_constraint("ck_mission_flights_emergency_reason_valid", type_="check")
        batch.create_check_constraint("ck_mission_flights_phase_valid", f"phase IN ({phases})")
        batch.create_check_constraint(
            "ck_mission_flights_emergency_reason_valid",
            f"emergency_reason IS NULL OR emergency_reason IN ({reasons})",
        )


def upgrade() -> None:
    _set_checks(PHASES_NEW, REASONS_NEW, 24)
    op.add_column(
        "mission_flights", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("mission_flights") as batch:
        batch.drop_column("failed_at")
    _set_checks(PHASES_OLD, REASONS_OLD, 16)
