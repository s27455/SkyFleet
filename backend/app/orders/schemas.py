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
