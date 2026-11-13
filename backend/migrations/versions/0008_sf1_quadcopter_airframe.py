"""SF-1 airframe: hexacopter -> quadcopter (MVP uses quadcopters only, four motors)

Revision ID: 0008
Revises: 0007

Data-only migration, no schema change. `airframe_type` is descriptive metadata that nothing in the
backend reads. The update is guarded: it touches only the SF-1 row and only while it still holds the
old seeded value, so a value someone changed on purpose is never overwritten. Drone ids, fleet size,
flight parameters, missions and orders are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_UPDATE = sa.text(
    "UPDATE drone_models SET airframe_type = :new WHERE id = 'SF-1' AND airframe_type = :old"
)


def upgrade() -> None:
    op.get_bind().execute(_UPDATE, {"old": "hexacopter", "new": "quadcopter"})


def downgrade() -> None:
    op.get_bind().execute(_UPDATE, {"old": "quadcopter", "new": "hexacopter"})
