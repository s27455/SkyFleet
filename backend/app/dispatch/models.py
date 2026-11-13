"""Persisted automatic-dispatch mode, shared by the API (toggle) and the worker (loop)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

AUTO_DISPATCH = "auto-dispatch"


class DispatchAutoState(Base):
    """The single row `auto-dispatch`. A missing row means OFF."""

    __tablename__ = "dispatch_auto_state"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # A short human-readable summary of the last pass, not a log.
    last_outcome: Mapped[str | None] = mapped_column(String(255), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
