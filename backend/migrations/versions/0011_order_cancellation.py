"""order cancellation and drone recall (Feature 018B)

Revision ID: 0011
Revises: 0010

Adds the `CANCELLED` order status (CHECK constraint), the nullable `orders.cancelled_at` and the
nullable `mission_flights.recalled_at`. No row is touched: no data is backfilled, deleted or
rewritten. The downgrade restores the narrower CHECK, which intentionally fails while a CANCELLED
order exists, and drops both columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STATUSES_OLD = "'CREATED', 'AWAITING_HANDOVER', 'READY_FOR_PICKUP', 'OUT_FOR_DELIVERY', 'DELIVERED'"
STATUSES_NEW = STATUSES_OLD + ", 'CANCELLED'"


def _set_status_check(statuses: str) -> None:
    # Batch mode recreates the table on SQLite and alters in place on PostgreSQL.
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_orders_status_valid", type_="check")
        batch.create_check_constraint("ck_orders_status_valid", f"status IN ({statuses})")


def upgrade() -> None:
    _set_status_check(STATUSES_NEW)
    op.add_column("orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "mission_flights", sa.Column("recalled_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("mission_flights") as batch:
        batch.drop_column("recalled_at")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("cancelled_at")
    _set_status_check(STATUSES_OLD)
