"""API response contract for delivery orders."""

from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.orders.models import MAX_PACKAGE_WEIGHT_KG, OrderStatus

Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
PackageWeight = Annotated[float, Field(gt=0, le=MAX_PACKAGE_WEIGHT_KG)]


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    origin_hub_id: str
    destination_address: str
    destination_longitude: float
    destination_latitude: float
    package_weight_kg: float
    status: OrderStatus
    delivered_at: datetime | None
    cancelled_at: datetime | None
    delivery_failed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OrderCreateRequest(BaseModel):
    """Customer and parcel details only; id, status and timestamps are set by the backend."""

    model_config = ConfigDict(extra="forbid")

    origin_hub_id: str = Field(min_length=1, max_length=64)
    destination_address: Address
    destination_longitude: Longitude
    destination_latitude: Latitude
    package_weight_kg: PackageWeight


class OrderUpdateRequest(BaseModel):
    """Whitelisted edits for a mission-free pending order; at least one field, none null."""

    model_config = ConfigDict(extra="forbid")

    origin_hub_id: str | None = Field(default=None, min_length=1, max_length=64)
    destination_address: Address | None = None
    destination_longitude: Longitude | None = None
    destination_latitude: Latitude | None = None
    package_weight_kg: PackageWeight | None = None

    @model_validator(mode="after")
    def _at_least_one_value(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to change")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Fields cannot be null")
        return self


class OrderSimulationStatus(BaseModel):
    """What the server is actually doing, never a client-side assumption."""

    # True only while the mode is ON and the simulation worker (the loop's owner) is alive.
    enabled: bool
    worker_running: bool
    # The last generation attempt and a short summary of it (an order created, or why not).
    last_check_at: datetime | None
    last_outcome: str | None
    # Every READY_FOR_PICKUP order counts; generation pauses at the limit.
    outstanding_orders: int
    max_outstanding_orders: int
