"""LPR helicopter scenarios (Feature 018E)

Revision ID: 0014
Revises: 0013

Adds the table `lpr_scenarios`: one row per helicopter pass, with a partial unique index that
allows at most one ACTIVE scenario. Nothing existing is touched. The downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lpr_scenarios",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_longitude", sa.Float, nullable=False),
        sa.Column("start_latitude", sa.Float, nullable=False),
        sa.Column("end_longitude", sa.Float, nullable=False),
        sa.Column("end_latitude", sa.Float, nullable=False),
        sa.Column("speed_ms", sa.Float, nullable=False),
        sa.Column("radius_m", sa.Float, nullable=False),
        sa.Column("margin_m", sa.Float, nullable=False),
        sa.Column("clear_extra_m", sa.Float, nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'COMPLETED')", name="ck_lpr_scenarios_status_valid"
        ),
        sa.CheckConstraint("speed_ms > 0 AND radius_m > 0", name="ck_lpr_scenarios_positive"),
    )
    op.create_index(
        "uq_lpr_scenarios_one_active",
        "lpr_scenarios",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_lpr_scenarios_one_active", table_name="lpr_scenarios")
    op.drop_table("lpr_scenarios")
