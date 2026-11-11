"""Persisted drone technical models and individual drone units.

A `DroneModel` holds the shared technical capabilities (simulation assumptions, not certified
performance). A `Drone` is one physical unit with its own identity and operational snapshot; its
`hub_id` is the assigned/home Hub (there is no separate DroneBase entity).
"""

from enum import StrEnum

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DroneStatus(StrEnum):
    """Operational states. Feature 005 only seeds `IDLE`; nothing transitions automatically."""

    IDLE = "IDLE"
    IN_FLIGHT = "IN_FLIGHT"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"


_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in DroneStatus)


class DroneModel(Base):
    __tablename__ = "drone_models"
    __table_args__ = (
        CheckConstraint("max_payload_kg > 0", name="ck_drone_models_max_payload_positive"),
        CheckConstraint("max_range_km > 0", name="ck_drone_models_max_range_positive"),
        CheckConstraint(
            "recommended_mission_range_km > 0 AND recommended_mission_range_km <= max_range_km",
            name="ck_drone_models_mission_range_within_max",
        ),
        CheckConstraint("cruise_speed_kmh > 0", name="ck_drone_models_cruise_speed_positive"),
        CheckConstraint(
            "max_speed_kmh >= cruise_speed_kmh", name="ck_drone_models_max_speed_ge_cruise"
        ),
        CheckConstraint("nominal_flight_time_min > 0", name="ck_drone_models_flight_time_positive"),
        CheckConstraint(
            "min_battery_reserve_pct BETWEEN 0 AND 100", name="ck_drone_models_reserve_range"
        ),
        CheckConstraint("charge_to_80_minutes > 0", name="ck_drone_models_charge_time_positive"),
        CheckConstraint("max_wind_mps > 0", name="ck_drone_models_max_wind_positive"),
        CheckConstraint("empty_weight_kg > 0", name="ck_drone_models_empty_weight_positive"),
    )

    # Stable model code, e.g. "SF-1".
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    airframe_type: Mapped[str] = mapped_column(String(64))
    max_payload_kg: Mapped[float] = mapped_column(Float)
    # Nominal upper bound on total distance per charge (not a delivery radius).
    max_range_km: Mapped[float] = mapped_column(Float)
    # Conservative total mission distance: travel to the recipient plus return to a Hub.
    recommended_mission_range_km: Mapped[float] = mapped_column(Float)
    cruise_speed_kmh: Mapped[float] = mapped_column(Float)
    max_speed_kmh: Mapped[float] = mapped_column(Float)
    nominal_flight_time_min: Mapped[int] = mapped_column(Integer)
    min_battery_reserve_pct: Mapped[int] = mapped_column(Integer)
    charge_to_80_minutes: Mapped[int] = mapped_column(Integer)
    max_wind_mps: Mapped[float] = mapped_column(Float)
    empty_weight_kg: Mapped[float] = mapped_column(Float)


class Drone(Base):
    __tablename__ = "drones"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_drones_status_valid"),
        CheckConstraint("battery_pct BETWEEN 0 AND 100", name="ck_drones_battery_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_drones_longitude_range"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_drones_latitude_range"),
    )

    # Stable unit id, e.g. "DRN-001".
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("drone_models.id", ondelete="RESTRICT"))
    # Assigned/home Hub (administrative), not where the drone is. Physical presence at a Hub is
    # derived from status and position (see app/missions/presence.py).
    hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    battery_pct: Mapped[int] = mapped_column(Integer)
    # Position snapshot; seeded at the assigned Hub. A later simulation feature updates it.
    longitude: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)

    model: Mapped[DroneModel] = relationship()
