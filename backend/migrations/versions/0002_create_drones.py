"""create drone_models and drones

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drone_models",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("airframe_type", sa.String(64), nullable=False),
        sa.Column("max_payload_kg", sa.Float, nullable=False),
        sa.Column("max_range_km", sa.Float, nullable=False),
        sa.Column("recommended_mission_range_km", sa.Float, nullable=False),
        sa.Column("cruise_speed_kmh", sa.Float, nullable=False),
        sa.Column("max_speed_kmh", sa.Float, nullable=False),
        sa.Column("nominal_flight_time_min", sa.Integer, nullable=False),
        sa.Column("min_battery_reserve_pct", sa.Integer, nullable=False),
        sa.Column("charge_to_80_minutes", sa.Integer, nullable=False),
        sa.Column("max_wind_mps", sa.Float, nullable=False),
        sa.Column("empty_weight_kg", sa.Float, nullable=False),
        sa.CheckConstraint("max_payload_kg > 0", name="ck_drone_models_max_payload_positive"),
        sa.CheckConstraint("max_range_km > 0", name="ck_drone_models_max_range_positive"),
        sa.CheckConstraint(
            "recommended_mission_range_km > 0 AND recommended_mission_range_km <= max_range_km",
            name="ck_drone_models_mission_range_within_max",
        ),
        sa.CheckConstraint("cruise_speed_kmh > 0", name="ck_drone_models_cruise_speed_positive"),
        sa.CheckConstraint(
            "max_speed_kmh >= cruise_speed_kmh", name="ck_drone_models_max_speed_ge_cruise"
        ),
        sa.CheckConstraint(
            "nominal_flight_time_min > 0", name="ck_drone_models_flight_time_positive"
        ),
        sa.CheckConstraint(
            "min_battery_reserve_pct BETWEEN 0 AND 100", name="ck_drone_models_reserve_range"
        ),
        sa.CheckConstraint("charge_to_80_minutes > 0", name="ck_drone_models_charge_time_positive"),
        sa.CheckConstraint("max_wind_mps > 0", name="ck_drone_models_max_wind_positive"),
        sa.CheckConstraint("empty_weight_kg > 0", name="ck_drone_models_empty_weight_positive"),
    )
    op.create_table(
        "drones",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "model_id",
            sa.String(32),
            sa.ForeignKey("drone_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "hub_id",
            sa.String(64),
            sa.ForeignKey("hubs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("battery_pct", sa.Integer, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.CheckConstraint(
            "status IN ('IDLE', 'IN_FLIGHT', 'CHARGING', 'MAINTENANCE')",
            name="ck_drones_status_valid",
        ),
        sa.CheckConstraint("battery_pct BETWEEN 0 AND 100", name="ck_drones_battery_range"),
        sa.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_drones_longitude_range"),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_drones_latitude_range"),
    )


def downgrade() -> None:
    op.drop_table("drones")
    op.drop_table("drone_models")
