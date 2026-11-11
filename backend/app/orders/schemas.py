"""API response contract for delivery orders."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.orders.models import OrderStatus


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
