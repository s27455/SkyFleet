"""create orders

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "origin_hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("destination_address", sa.String(255), nullable=False),
        sa.Column("destination_longitude", sa.Float, nullable=False),
        sa.Column("destination_latitude", sa.Float, nullable=False),
        sa.Column("package_weight_kg", sa.Float, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('CREATED', 'AWAITING_HANDOVER', 'READY_FOR_PICKUP')",
            name="ck_orders_status_valid",
        ),
        sa.CheckConstraint(
            "length(trim(destination_address)) > 0", name="ck_orders_destination_address_nonempty"
        ),
        sa.CheckConstraint(
            "destination_longitude BETWEEN -180 AND 180", name="ck_orders_longitude_range"
        ),
        sa.CheckConstraint(
            "destination_latitude BETWEEN -90 AND 90", name="ck_orders_latitude_range"
        ),
        # 3.0 kg = SF-1 Courier maximum payload (MVP order-acceptance rule).
        sa.CheckConstraint(
            "package_weight_kg > 0 AND package_weight_kg <= 3.0",
            name="ck_orders_package_weight_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("orders")
