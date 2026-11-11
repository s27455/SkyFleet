"""create hubs

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hubs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("address", sa.String(200), nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("drone_capacity", sa.Integer, nullable=False, server_default="50"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_hubs_longitude_range"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_hubs_latitude_range"),
        sa.CheckConstraint("drone_capacity > 0", name="ck_hubs_drone_capacity_positive"),
    )


def downgrade() -> None:
    op.drop_table("hubs")
