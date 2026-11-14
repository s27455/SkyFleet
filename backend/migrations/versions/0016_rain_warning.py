"""rain warning (Feature 020)

Revision ID: 0016
Revises: 0015

Adds the single-row `weather_state` table (seeded INACTIVE as `rain-warning`) and widens the event
type CHECK with `RAIN_WARNING_ACTIVATED` and `RAIN_WARNING_CLEARED`. No existing row is changed.
The downgrade drops the table and restores the narrower CHECK, which intentionally fails while a
rain warning event exists (delete those events first if a downgrade is really wanted).
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

EVENTS_OLD = (
    "'ORDER_CREATED', 'ORDER_CANCELLED', 'DRONE_FAILURE', 'RECIPIENT_UNAVAILABLE', 'LPR_TRANSIT', "
    "'DRONE_RELOCATION'"
)
EVENTS_NEW = EVENTS_OLD + ", 'RAIN_WARNING_ACTIVATED', 'RAIN_WARNING_CLEARED'"


def _set_event_check(events: str) -> None:
    with op.batch_alter_table("operational_events") as batch:
        batch.drop_constraint("ck_operational_events_type_valid", type_="check")
        batch.create_check_constraint(
            "ck_operational_events_type_valid", f"event_type IN ({events})"
        )


def upgrade() -> None:
    table = op.create_table(
        "weather_state",
        sa.Column("name", sa.String(length=32), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.bulk_insert(table, [{"name": "rain-warning", "active": False}])
    _set_event_check(EVENTS_NEW)


def downgrade() -> None:
    _set_event_check(EVENTS_OLD)
    op.drop_table("weather_state")
