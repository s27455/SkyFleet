"""API response contracts for drones."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.drones.models import DroneStatus


class DroneModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    airframe_type: str
    max_payload_kg: float
    max_range_km: float
    recommended_mission_range_km: float
    cruise_speed_kmh: float
    max_speed_kmh: float
    nominal_flight_time_min: int
    min_battery_reserve_pct: int
    charge_to_80_minutes: int
    max_wind_mps: float
    empty_weight_kg: float


class DroneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hub_id: str
    status: DroneStatus
    battery_pct: int
    longitude: float
    latitude: float
    model: DroneModelResponse


class DroneCreateRequest(BaseModel):
    """Administrator-controlled fields only; status, position and model are set by the backend."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^DRN-\d{3,}$", max_length=32)
    hub_id: str = Field(min_length=1, max_length=64)
    battery_pct: int = Field(default=100, ge=0, le=100)


class RelocateRequest(BaseModel):
    """The destination of a manual relocation (Feature 019A)."""

    model_config = ConfigDict(extra="forbid")

    destination_hub_id: str = Field(min_length=1, max_length=64)


class DroneUpdateRequest(BaseModel):
    """Whitelisted administrative changes; every other field is rejected (422)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[DroneStatus.IDLE, DroneStatus.MAINTENANCE] | None = None
    hub_id: str | None = Field(default=None, min_length=1, max_length=64)
    battery_pct: int | None = Field(default=None, ge=0, le=100)
