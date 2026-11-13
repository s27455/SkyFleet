"""operational events: an append-only timeline table (Feature 018A)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

EVENT_TYPES = (
    "'ORDER_CREATED', 'ORDER_CANCELLED', 'DRONE_FAILURE', 'RECIPIENT_UNAVAILABLE', 'LPR_TRANSIT'"
)
ORIGINS = "'SYSTEM', 'AUTOMATIC', 'MANUAL'"


def upgrade() -> None:
    # Additive only: no existing row is touched and no history is backfilled.
    op.create_table(
        "operational_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="RESTRICT")),
        sa.Column("mission_id", sa.String(12), sa.ForeignKey("missions.id", ondelete="RESTRICT")),
        sa.Column(
            "flight_id",
            sa.String(12),
            sa.ForeignKey("mission_flights.mission_id", ondelete="RESTRICT"),
        ),
        sa.Column("drone_id", sa.String(32), sa.ForeignKey("drones.id", ondelete="RESTRICT")),
        sa.Column("reason", sa.String(255)),
        sa.Column("details", sa.JSON),
        sa.Column("dedupe_key", sa.String(128), unique=True),
        sa.CheckConstraint(
            f"event_type IN ({EVENT_TYPES})", name="ck_operational_events_type_valid"
        ),
        sa.CheckConstraint(f"origin IN ({ORIGINS})", name="ck_operational_events_origin_valid"),
    )
    op.create_index(
        "ix_operational_events_order", "operational_events", ["order_id", "occurred_at", "id"]
    )
    op.create_index(
        "ix_operational_events_mission", "operational_events", ["mission_id", "occurred_at", "id"]
    )
    op.create_index(
        "ix_operational_events_drone", "operational_events", ["drone_id", "occurred_at", "id"]
    )


def downgrade() -> None:
    op.drop_table("operational_events")
