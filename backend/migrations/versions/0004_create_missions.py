"""create missions

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ACTIVE_PREDICATE = "status IN ('ASSIGNED', 'IN_FLIGHT')"


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(32),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "drone_id",
            sa.String(32),
            sa.ForeignKey("drones.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "origin_hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "return_hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin_to_destination_km", sa.Float, nullable=False),
        sa.Column("destination_to_return_km", sa.Float, nullable=False),
        sa.Column("total_km", sa.Float, nullable=False),
        sa.Column("expected_energy_pct", sa.Float, nullable=False),
        sa.Column("worst_case_energy_pct", sa.Float, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('ASSIGNED', 'IN_FLIGHT', 'CANCELLED')", name="ck_missions_status_valid"
        ),
        sa.CheckConstraint("origin_to_destination_km >= 0", name="ck_missions_leg_out_nonnegative"),
        sa.CheckConstraint(
            "destination_to_return_km >= 0", name="ck_missions_leg_back_nonnegative"
        ),
        sa.CheckConstraint("total_km >= 0", name="ck_missions_total_nonnegative"),
        sa.CheckConstraint("expected_energy_pct >= 0", name="ck_missions_expected_nonnegative"),
        sa.CheckConstraint("worst_case_energy_pct >= 0", name="ck_missions_worst_nonnegative"),
    )
    # At most one active mission per order and per drone, enforced by the database.
    for name, column in (
        ("uq_missions_active_order", "order_id"),
        ("uq_missions_active_drone", "drone_id"),
    ):
        op.create_index(
            name,
            "missions",
            [column],
            unique=True,
            postgresql_where=sa.text(ACTIVE_PREDICATE),
            sqlite_where=sa.text(ACTIVE_PREDICATE),
        )


def downgrade() -> None:
    op.drop_index("uq_missions_active_drone", table_name="missions")
    op.drop_index("uq_missions_active_order", table_name="missions")
    op.drop_table("missions")
