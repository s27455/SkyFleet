"""API contract for the rain warning (Feature 020)."""

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.common.clock import as_utc


class RainWarningResponse(BaseModel):
    active: bool
    activated_at: datetime | None
    cleared_at: datetime | None
    origin: str | None
    # False when the request found the warning already in the requested state (nothing recorded).
    changed: bool = False

    @field_validator("activated_at", "cleared_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        """SQLite returns naive timestamps; the API always states UTC explicitly."""
        return None if value is None else as_utc(value)
