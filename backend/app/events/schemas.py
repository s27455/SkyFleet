from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.simulation.clock import as_utc


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    occurred_at: datetime
    origin: str
    order_id: str | None
    mission_id: str | None
    flight_id: str | None
    drone_id: str | None
    reason: str | None
    details: dict[str, Any] | None

    @field_validator("occurred_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        """SQLite returns naive timestamps; the API always states UTC explicitly."""
        return as_utc(value)
