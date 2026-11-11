"""API response contracts for drones."""

from pydantic import BaseModel, ConfigDict

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
