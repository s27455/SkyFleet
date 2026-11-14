"""Persisted weather restriction (Feature 020): one global rain warning."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

RAIN_WARNING = "rain-warning"


class WeatherState(Base):
    """The single row `rain-warning`. A missing row means INACTIVE (the migration seeds it)."""

    __tablename__ = "weather_state"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Who last changed it (an `EventOrigin` value); only MANUAL exists in the MVP.
    origin: Mapped[str | None] = mapped_column(String(16), default=None)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
