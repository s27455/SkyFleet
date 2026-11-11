"""API response contract for Hubs."""

from pydantic import BaseModel, ConfigDict


class HubResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: str
    longitude: float
    latitude: float
    drone_capacity: int
