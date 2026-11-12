"""flight simulation: flights, worker heartbeat, new order and mission statuses

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ACTIVE_PREDICATE = "status IN ('ASSIGNED', 'IN_FLIGHT')"

ORDER_STATUSES_OLD = "'CREATED', 'AWAITING_HANDOVER', 'READY_FOR_PICKUP'"
ORDER_STATUSES_NEW = ORDER_STATUSES_OLD + ", 'OUT_FOR_DELIVERY', 'DELIVERED'"
MISSION_STATUSES_OLD = "'ASSIGNED', 'IN_FLIGHT', 'CANCELLED'"
MISSION_STATUSES_NEW = MISSION_STATUSES_OLD + ", 'COMPLETED', 'EMERGENCY'"


def _set_status_check(table: str, name: str, statuses: str) -> None:
    # Batch mode recreates the table on SQLite and alters in place on PostgreSQL.
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(name, type_="check")
        batch.create_check_constraint(name, f"status IN ({statuses})")


def _create_active_mission_indexes() -> None:
    for name, column in (
        ("uq_missions_active_order", "order_id"),
        ("uq_missions_active_drone", "drone_id"),
    ):
        op.create_index(
            name,
            "missions",
            [column],
            unique=True,
            postgresql_where=sa.text(ACTIVE_PREDICATE),
            sqlite_where=sa.text(ACTIVE_PREDICATE),
        )


def _drop_active_mission_indexes() -> None:
    op.drop_index("uq_missions_active_drone", table_name="missions")
    op.drop_index("uq_missions_active_order", table_name="missions")


def upgrade() -> None:
    # The partial unique indexes are dropped and recreated around the table rebuild so their
    # predicate is certain to survive.
    _drop_active_mission_indexes()
    _set_status_check("missions", "ck_missions_status_valid", MISSION_STATUSES_NEW)
    _create_active_mission_indexes()
    _set_status_check("orders", "ck_orders_status_valid", ORDER_STATUSES_NEW)

    op.create_table(
        "mission_flights",
        sa.Column(
            "mission_id",
            sa.String(12),
            sa.ForeignKey("missions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("start_battery_pct", sa.Float, nullable=False),
        sa.Column("battery_pct", sa.Float, nullable=False),
        sa.Column("legs", sa.JSON, nullable=False),
        sa.Column("pace_s_per_km", sa.Float, nullable=False),
        sa.Column(
            "planned_return_hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "landing_target_hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("landed_hub_id", sa.String(64), sa.ForeignKey("hubs.id", ondelete="RESTRICT")),
        sa.Column("tried_hub_ids", sa.JSON, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("progress", sa.Float, nullable=False),
        sa.Column("target_longitude", sa.Float),
        sa.Column("target_latitude", sa.Float),
        sa.Column("target_eta_s", sa.Float),
        sa.Column("emergency_reason", sa.String(24)),
        sa.Column("emergency_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "phase IN ('OUTBOUND', 'DELIVERING', 'RETURNING', 'DIVERTING', 'LANDED', 'EMERGENCY')",
            name="ck_mission_flights_phase_valid",
        ),
        sa.CheckConstraint(
            "emergency_reason IS NULL OR emergency_reason IN "
            "('NO_HUB_WITH_CAPACITY', 'BATTERY_INSUFFICIENT', 'BATTERY_CRITICAL')",
            name="ck_mission_flights_emergency_reason_valid",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 1", name="ck_mission_flights_progress_range"),
        sa.CheckConstraint("pace_s_per_km > 0", name="ck_mission_flights_pace_positive"),
    )
    op.create_table(
        "simulation_heartbeats",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # Rows already in a Feature 010 status make the narrower CHECK fail, which is intended:
    # downgrading with delivered orders or finished missions would lose information.
    op.drop_table("simulation_heartbeats")
    op.drop_table("mission_flights")
    _set_status_check("orders", "ck_orders_status_valid", ORDER_STATUSES_OLD)
    _drop_active_mission_indexes()
    _set_status_check("missions", "ck_missions_status_valid", MISSION_STATUSES_OLD)
    _create_active_mission_indexes()
