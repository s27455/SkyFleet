"""automatic dispatch mode: one row of shared state between the API and the worker

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The API (toggle) and the simulation worker (loop) are separate processes, so the mode lives
    # here. No row means OFF; the worker also resets it to OFF whenever it starts.
    op.create_table(
        "dispatch_auto_state",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outcome", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dispatch_auto_state")
