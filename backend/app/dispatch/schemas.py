"""Response contract of the read-only dispatch recommendations (Feature 014A)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.missions.schemas import ReasonCode


class PendingReason(StrEnum):
    # No drone is docked, IDLE, at exactly 100% battery and unclaimed at the order's origin Hub.
    NO_ELIGIBLE_DRONE_AT_HUB = "NO_ELIGIBLE_DRONE_AT_HUB"
    # Fully charged drones exist, but the mission planner rejects the order for every one of them.
    PLANNER_REJECTED = "PLANNER_REJECTED"


class Recommendation(BaseModel):
    """A proposed assignment. Nothing is created or reserved by proposing it."""

    order_id: str
    drone_id: str
    origin_hub_id: str
    # The return Hub the planner selected (planned, not reserved).
    return_hub_id: str


class PendingOrder(BaseModel):
    """A considered order that gets no drone in this pass; it simply stays pending."""

    order_id: str
    origin_hub_id: str
    reason: PendingReason
    # Distinct planner reason codes seen across the candidate drones (PLANNER_REJECTED only).
    planner_reasons: list[ReasonCode]


class RecommendationsResponse(BaseModel):
    recommendations: list[Recommendation]
    pending: list[PendingOrder]


class DispatchExecuteRequest(BaseModel):
    """The pair to dispatch, normally taken from `GET /api/dispatch/recommendations`."""

    order_id: str = Field(min_length=1)
    drone_id: str = Field(min_length=1)


class AutoDispatchStatus(BaseModel):
    """What the server is actually doing, never a client-side assumption."""

    # True only while the mode is ON and the simulation worker (the loop's owner) is alive.
    enabled: bool
    worker_running: bool
    last_check_at: datetime | None
    # A short summary of the last pass (what was started, or why nothing was).
    last_outcome: str | None
