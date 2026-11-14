"""API contracts for mission planning, confirmation and cancellation."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.missions.capacity import SkipReason
from app.missions.models import MissionPurpose, MissionStatus


class ReasonCode(StrEnum):
    ORDER_NOT_READY = "ORDER_NOT_READY"
    ORDER_ALREADY_ASSIGNED = "ORDER_ALREADY_ASSIGNED"
    DRONE_ALREADY_ASSIGNED = "DRONE_ALREADY_ASSIGNED"
    DRONE_NOT_AVAILABLE = "DRONE_NOT_AVAILABLE"
    DRONE_NOT_AT_ORIGIN_HUB = "DRONE_NOT_AT_ORIGIN_HUB"
    OVERWEIGHT = "OVERWEIGHT"
    ROUTE_TOO_LONG = "ROUTE_TOO_LONG"
    INSUFFICIENT_BATTERY = "INSUFFICIENT_BATTERY"
    RETURN_HUBS_FULL = "RETURN_HUBS_FULL"


class PlanReason(BaseModel):
    code: ReasonCode
    message: str


class PlanRoute(BaseModel):
    origin_hub_id: str
    # The planned return Hub; None when no suitable Hub exists. Planned, not reserved.
    return_hub_id: str | None
    # The Hub the distances and energy figures were computed for (the planned return Hub, or the
    # nearest Hub to the destination when none is suitable).
    basis_hub_id: str
    origin_to_destination_km: float
    destination_to_return_km: float
    total_km: float


class PlanEnergy(BaseModel):
    """Simulation assumptions, not certified flight performance."""

    empty_rate_pct_per_km: float
    loaded_rate_pct_per_km: float
    payload_energy_factor: float
    expected_pct: float
    worst_case_pct: float
    reserve_pct: float
    required_battery_pct: float
    drone_battery_pct: int


class HubOccupancy(BaseModel):
    hub_id: str
    docked_drones: int
    capacity: int


class SkippedHub(BaseModel):
    hub_id: str
    reason: SkipReason


class PlanResponse(BaseModel):
    order_id: str
    drone_id: str
    eligible: bool
    reasons: list[PlanReason]
    route: PlanRoute
    energy: PlanEnergy
    distance_budget_km: float
    # Physical occupancy now (docked drones only; missions reserve nothing).
    hub_occupancy: list[HubOccupancy]
    skipped_return_hubs: list[SkippedHub]
    notes: list[str]


class MissionCreateRequest(BaseModel):
    order_id: str = Field(min_length=1)
    drone_id: str = Field(min_length=1)


class MissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # None for a relocation (Feature 019A): it serves no order.
    order_id: str | None
    purpose: MissionPurpose
    drone_id: str
    origin_hub_id: str
    return_hub_id: str
    status: MissionStatus
    origin_to_destination_km: float
    destination_to_return_km: float
    total_km: float
    expected_energy_pct: float
    worst_case_energy_pct: float
    created_at: datetime
    updated_at: datetime
