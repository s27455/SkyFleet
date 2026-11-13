"""API contracts for flights (REST polling; the payload suits a later stream as well)."""

from datetime import datetime

from pydantic import BaseModel

from app.missions.models import MissionStatus
from app.simulation.models import EmergencyReason, FlightPhase


class FlightTarget(BaseModel):
    """Where the drone is heading and how long, in simulation seconds, until it gets there.

    The frontend may interpolate toward this point between polls; it never runs the mission.
    """

    position: tuple[float, float]  # [longitude, latitude]
    eta_s: float


class FlightEmergency(BaseModel):
    """A simulated emergency outcome. It is not a computed safe landing site."""

    reason: EmergencyReason
    at: datetime
    position: tuple[float, float]


class FlightResponse(BaseModel):
    mission_id: str
    order_id: str
    drone_id: str
    mission_status: MissionStatus
    phase: FlightPhase
    progress: float  # 0..1 of the current schedule
    position: tuple[float, float]  # [longitude, latitude], the snapshot at `updated_at`
    battery_pct: int
    battery_exact_pct: float
    target: FlightTarget | None
    origin_hub_id: str
    planned_return_hub_id: str
    landing_target_hub_id: str
    started_at: datetime
    delivered_at: datetime | None
    # Set when the order was cancelled in flight: the drone returns to a Hub with the parcel.
    recalled_at: datetime | None
    # Set when a drone failure was triggered: the drone makes an emergency landing (Feature 018C).
    failed_at: datetime | None
    # Feature 018D: the recipient was reported unavailable (the attempt is still pending until
    # `handover_failed_at`); after it the drone returns with the parcel.
    recipient_unavailable_at: datetime | None
    handover_failed_at: datetime | None
    updated_at: datetime
    emergency: FlightEmergency | None


class FlightsResponse(BaseModel):
    """Active flights and flights that ended in an emergency (landed flights are not listed)."""

    server_time: datetime
    # The worker's latest heartbeat; `worker_stale` is true when it is missing or too old, in
    # which case the flight snapshots below are no longer being updated.
    worker_heartbeat_at: datetime | None
    worker_stale: bool
    flights: list[FlightResponse]


class RecipientUnavailableResponse(BaseModel):
    """What a manual Recipient unavailable trigger did (Feature 018D).

    The outcome is pending: the order is only marked as failed when the drone reaches the
    destination at `attempt_at` (the scheduled instant of the delivery attempt).
    """

    drone_id: str
    mission_id: str
    order_id: str
    attempt_at: datetime


class DroneFailureResponse(BaseModel):
    """What a manual Drone failure trigger did (Feature 018C)."""

    drone_id: str
    mission_id: str
    order_id: str
    stage: str  # BEFORE_DELIVERY, RECALL, HANDOVER_FAILED or AFTER_DELIVERY
    landing_position: tuple[float, float]  # [longitude, latitude], a simulated point
