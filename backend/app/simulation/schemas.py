"""API contracts for flights (REST polling; the payload suits a later stream as well)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.missions.models import MissionPurpose, MissionStatus
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
    order_id: str | None  # None for a relocation (Feature 019A)
    purpose: MissionPurpose
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
    # Feature 018E: the drone is standing still outside the LPR helicopter's safety zone.
    yielding_to_lpr: bool
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
    order_id: str | None  # None when a relocating drone failed
    stage: str  # BEFORE_DELIVERY, RECALL, HANDOVER_FAILED, AFTER_DELIVERY or RELOCATION
    landing_position: tuple[float, float]  # [longitude, latitude], a simulated point


class LprScenarioResponse(BaseModel):
    """The LPR helicopter scenario with the helicopter's position now (Feature 018E).

    The route, speed and radius are fictional simulation parameters; the frontend may glide the
    marker between polls but never decides anything.
    """

    id: str
    status: str
    origin: str
    started_at: datetime
    ends_at: datetime
    position: tuple[float, float]  # [longitude, latitude] of the helicopter now
    route_start: tuple[float, float]
    route_end: tuple[float, float]
    speed_ms: float
    radius_m: float  # the drawn safety zone
    hold_margin_m: float  # drones stop this far outside it


class LprStatusResponse(BaseModel):
    server_time: datetime
    scenario: LprScenarioResponse | None


class RandomIncidentsStatus(BaseModel):
    """What the server is actually doing, never a client-side assumption (Feature 021D-2)."""

    # True only while the mode is ON and the simulation worker (the loop's owner) is alive.
    enabled: bool
    worker_running: bool
    # The last scheduled attempt and a short summary: an incident triggered, or why not. An attempt
    # may be skipped, so an incident is never promised for every interval.
    last_check_at: datetime | None
    last_outcome: str | None


class RelocationReasonCode(StrEnum):
    DRONE_ALREADY_ASSIGNED = "DRONE_ALREADY_ASSIGNED"
    DRONE_NOT_AVAILABLE = "DRONE_NOT_AVAILABLE"
    DRONE_NOT_AT_HUB = "DRONE_NOT_AT_HUB"
    SAME_HUB = "SAME_HUB"
    ROUTE_TOO_LONG = "ROUTE_TOO_LONG"
    INSUFFICIENT_BATTERY = "INSUFFICIENT_BATTERY"
    DESTINATION_FULL = "DESTINATION_FULL"


class RelocationReason(BaseModel):
    code: RelocationReasonCode
    message: str


class RelocationPlanResponse(BaseModel):
    """Feasibility of relocating one drone to one Hub (Feature 019A); the preview writes nothing.

    Distances and energy are simulation assumptions (the existing empty-flight rate), not certified
    flight performance. The destination is not reserved; capacity is rechecked at landing.
    """

    drone_id: str
    eligible: bool
    reasons: list[RelocationReason]
    origin_hub_id: str | None  # the Hub the drone is docked at now
    destination_hub_id: str
    distance_km: float
    distance_budget_km: float
    required_battery_pct: float  # the flight plus the minimum reserve
    expected_battery_use_pct: float
    drone_battery_pct: int
    destination_docked_drones: int
    destination_capacity: int
    warnings: list[str]


class RelocationResponse(BaseModel):
    """The relocation that was started (Feature 019A)."""

    mission_id: str
    drone_id: str
    origin_hub_id: str
    destination_hub_id: str
    started_at: datetime
    distance_km: float
