"""Order delivery time: orders.delivered_at (Feature 017A)

Revision ID: 0009
Revises: 0008

Adds a nullable, timezone-aware `delivered_at` to `orders` and backfills it for orders that are
already DELIVERED from `mission_flights.delivered_at` (the same instant the engine now writes).
A DELIVERED order with no flight row keeps NULL; nothing is invented. No row is deleted and no
other column changes. The downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_BACKFILL = sa.text(
    """
    UPDATE orders
    SET delivered_at = (
        SELECT MAX(mission_flights.delivered_at)
        FROM missions
        JOIN mission_flights ON mission_flights.mission_id = missions.id
        WHERE missions.order_id = orders.id AND mission_flights.delivered_at IS NOT NULL
    )
    WHERE status = 'DELIVERED' AND delivered_at IS NULL
    """
)


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.get_bind().execute(_BACKFILL)


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("delivered_at")
