"""manual drone relocation (Feature 019A)

Revision ID: 0015
Revises: 0014

Makes `missions.order_id` nullable and adds `missions.purpose` (`DELIVERY` for every existing row,
`RELOCATION` for an order-less hub-to-hub flight), with two CHECK constraints: the purpose is
valid, and a relocation has no order while a delivery always has one. Widens the flight phase CHECK
with `RELOCATING` and the event type CHECK with `DRONE_RELOCATION`. No row is rewritten except that
the new `purpose` column is filled with `DELIVERY`. The downgrade restores the narrower checks and
the NOT NULL order, which intentionally fails while a relocation exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

PHASES_OLD = (
    "'OUTBOUND', 'DELIVERING', 'RETURNING', 'DIVERTING', 'LANDED', 'EMERGENCY', "
    "'EMERGENCY_APPROACH'"
)
PHASES_NEW = PHASES_OLD + ", 'RELOCATING'"
EVENTS_OLD = (
    "'ORDER_CREATED', 'ORDER_CANCELLED', 'DRONE_FAILURE', 'RECIPIENT_UNAVAILABLE', 'LPR_TRANSIT'"
)
EVENTS_NEW = EVENTS_OLD + ", 'DRONE_RELOCATION'"
PURPOSE_ORDER = (
    "(purpose = 'RELOCATION' AND order_id IS NULL) "
    "OR (purpose = 'DELIVERY' AND order_id IS NOT NULL)"
)


def _partial_indexes() -> None:
    """Recreate the two partial unique indexes (a SQLite table rebuild may not keep them)."""
    active = "status IN ('ASSIGNED', 'IN_FLIGHT')"
    for name, column in (
        ("uq_missions_active_order", "order_id"),
        ("uq_missions_active_drone", "drone_id"),
    ):
        op.create_index(
            name,
            "missions",
            [column],
            unique=True,
            postgresql_where=sa.text(active),
            sqlite_where=sa.text(active),
            if_not_exists=True,
        )


def _set_phase_check(phases: str) -> None:
    with op.batch_alter_table("mission_flights") as batch:
        batch.drop_constraint("ck_mission_flights_phase_valid", type_="check")
        batch.create_check_constraint("ck_mission_flights_phase_valid", f"phase IN ({phases})")


def _set_event_check(events: str) -> None:
    with op.batch_alter_table("operational_events") as batch:
        batch.drop_constraint("ck_operational_events_type_valid", type_="check")
        batch.create_check_constraint(
            "ck_operational_events_type_valid", f"event_type IN ({events})"
        )


def upgrade() -> None:
    with op.batch_alter_table("missions") as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(16), nullable=False, server_default="DELIVERY")
        )
        batch.alter_column("order_id", existing_type=sa.String(), nullable=True)
        batch.create_check_constraint(
            "ck_missions_purpose_valid", "purpose IN ('DELIVERY', 'RELOCATION')"
        )
        batch.create_check_constraint("ck_missions_purpose_order", PURPOSE_ORDER)
    _partial_indexes()
    _set_phase_check(PHASES_NEW)
    _set_event_check(EVENTS_NEW)


def downgrade() -> None:
    _set_event_check(EVENTS_OLD)
    _set_phase_check(PHASES_OLD)
    with op.batch_alter_table("missions") as batch:
        batch.drop_constraint("ck_missions_purpose_order", type_="check")
        batch.drop_constraint("ck_missions_purpose_valid", type_="check")
        batch.alter_column("order_id", existing_type=sa.String(), nullable=False)
        batch.drop_column("purpose")
    _partial_indexes()
