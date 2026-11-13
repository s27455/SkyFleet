"""failed delivery and parcel return (Feature 018D)

Revision ID: 0013
Revises: 0012

Adds the `DELIVERY_FAILED` order status (CHECK constraint), the nullable `orders.delivery_failed_at`
and the nullable `mission_flights` columns `recipient_unavailable_at`, `handover_failed_at` and
`recipient_unavailable_origin`. No row is touched: no data is backfilled, deleted or rewritten.
The downgrade restores the narrower CHECK, which intentionally fails while a DELIVERY_FAILED
order exists, and drops the four columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

STATUSES_OLD = (
    "'CREATED', 'AWAITING_HANDOVER', 'READY_FOR_PICKUP', 'OUT_FOR_DELIVERY', 'DELIVERED', "
    "'CANCELLED'"
)
STATUSES_NEW = STATUSES_OLD + ", 'DELIVERY_FAILED'"


def _set_status_check(statuses: str) -> None:
    # Batch mode recreates the table on SQLite and alters in place on PostgreSQL.
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_orders_status_valid", type_="check")
        batch.create_check_constraint("ck_orders_status_valid", f"status IN ({statuses})")


def upgrade() -> None:
    _set_status_check(STATUSES_NEW)
    op.add_column(
        "orders", sa.Column("delivery_failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "mission_flights",
        sa.Column("recipient_unavailable_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mission_flights",
        sa.Column("handover_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mission_flights",
        sa.Column("recipient_unavailable_origin", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("mission_flights") as batch:
        batch.drop_column("recipient_unavailable_origin")
        batch.drop_column("handover_failed_at")
        batch.drop_column("recipient_unavailable_at")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("delivery_failed_at")
    _set_status_check(STATUSES_OLD)
