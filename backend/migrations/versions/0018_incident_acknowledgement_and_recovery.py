"""incident acknowledgements and drone recovery (Feature 022)

Revision ID: 0018
Revises: 0017

Adds the `incident_acknowledgements` table (one row per acknowledged emergency alert, keyed by the
mission id) and widens the event type CHECK with `DRONE_RECOVERED`. No existing row is changed and
nothing is seeded. Recovery itself stores nothing new: it is derived from the failed flight and the
events, and the `DRONE_RECOVERED` event with its unique `dedupe_key` is its "done" marker.

The downgrade drops the table and restores the narrower CHECK, which intentionally fails while a
`DRONE_RECOVERED` event exists (delete those events first if a downgrade is really wanted).
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

EVENTS_OLD = (
    "'ORDER_CREATED', 'ORDER_CANCELLED', 'DRONE_FAILURE', 'RECIPIENT_UNAVAILABLE', 'LPR_TRANSIT', "
    "'DRONE_RELOCATION', 'RAIN_WARNING_ACTIVATED', 'RAIN_WARNING_CLEARED'"
)
EVENTS_NEW = EVENTS_OLD + ", 'DRONE_RECOVERED'"


def _set_event_check(events: str) -> None:
    with op.batch_alter_table("operational_events") as batch:
        batch.drop_constraint("ck_operational_events_type_valid", type_="check")
        batch.create_check_constraint(
            "ck_operational_events_type_valid", f"event_type IN ({events})"
        )


def upgrade() -> None:
    op.create_table(
        "incident_acknowledgements",
        sa.Column(
            "mission_id",
            sa.String(12),
            sa.ForeignKey("missions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
    )
    _set_event_check(EVENTS_NEW)


def downgrade() -> None:
    _set_event_check(EVENTS_OLD)
    op.drop_table("incident_acknowledgements")
