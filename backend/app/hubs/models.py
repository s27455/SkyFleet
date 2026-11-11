"""Persisted Mall Pickup Hub: parcel handover point and drone base (business-rules.md §2)."""

from sqlalchemy import CheckConstraint, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

DEFAULT_DRONE_CAPACITY = 50


class Hub(Base):
    __tablename__ = "hubs"
    __table_args__ = (
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_hubs_longitude_range"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_hubs_latitude_range"),
        CheckConstraint("drone_capacity > 0", name="ck_hubs_drone_capacity_positive"),
    )

    # Stable slug, e.g. "hub-galeria-baltycka"; matches the ids used by the frontend mock data.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    address: Mapped[str] = mapped_column(String(200))
    longitude: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    # Maximum number of drones the Hub can accommodate (not parcels or orders).
    drone_capacity: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_DRONE_CAPACITY, server_default=str(DEFAULT_DRONE_CAPACITY)
    )
