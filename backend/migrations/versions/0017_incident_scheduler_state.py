"""automatic random incidents: one row of shared state between the API and the worker (021D-2)

Revision ID: 0017
Revises: 0016

Adds the `incident_scheduler_state` table. A missing row means OFF (nothing is seeded), and the
worker resets the mode to OFF whenever it starts. It is independent of `dispatch_auto_state` and
`order_simulation_state`. No existing table or row is changed, and the event type CHECK is not
touched: automatic incidents use the existing event types with the AUTOMATIC origin.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_scheduler_state",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("incident_scheduler_state")
