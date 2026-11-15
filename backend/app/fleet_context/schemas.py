"""The typed contract of the fleet snapshot (`schema_version` "1").

Everything here is a fact about the PRESENT unless a field name says otherwise (`*_last_60_min`,
`*_all_time`, `recovered_alerts` are history). Values are strings, integers and booleans only: no
floats, no coordinates, no free text from the database (names are sanitised, see `snapshot.py`).

Field order is the serialised order and it is deliberate: what the model must not miss
(`data_status`, `limitations`, `truncated`, `omitted`) comes first, the bulky lists last.

Units and meanings
  battery_pct      integer percent of capacity (0-100), the drone row, updated by the worker
  free             capacity - docked, never negative
  docked / at_hub  inferred from status (not IN_FLIGHT, not MAINTENANCE) and a stored position
                   within the docking radius of a Hub; not hardware-confirmed
  dispatchable     the dispatcher's own rule: IDLE, battery exactly 100, no active mission, docked
  captured_at      UTC, whole seconds, taken at the start of the read-only transaction
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1"

# Hard caps of the builder (a rendered snapshot may be reduced further to fit the byte budget).
MAX_HUBS = 12
MAX_DRONES = 40
MAX_INCIDENTS = 10
MAX_RECOVERED_ALERTS = 10
HISTORY_WINDOW_SECONDS = 3600  # "last 60 min"
STATEMENT_TIMEOUT_MS = 2000  # a slower snapshot fails closed
LABEL_MAX_CHARS = 40


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DataStatus(StrEnum):
    # No limitation and nothing omitted: every section was read in one snapshot, the simulation
    # worker is alive and the invariants hold.
    COMPLETE = "complete"
    # Read `limitations`, `truncated` and `omitted` before trusting any number.
    DEGRADED = "degraded"


class Limitation(StrEnum):
    """Fixed codes (a code may carry `:detail`, e.g. a hub id or an omitted count)."""

    WORKER_NOT_RUNNING = "WORKER_NOT_RUNNING"  # no fresh heartbeat: positions are not updating
    HUB_OVER_CAPACITY = "HUB_OVER_CAPACITY"  # more drones counted at a Hub than its capacity
    FLIGHT_STATUS_MISMATCH = "FLIGHT_STATUS_MISMATCH"  # IN_FLIGHT drones differ from active flights
    UNKNOWN_DRONE_STATUS = "UNKNOWN_DRONE_STATUS"  # counted under OTHER
    UNKNOWN_ORDER_STATUS = "UNKNOWN_ORDER_STATUS"  # counted under orders_open.other
    TEXT_SANITIZED = "TEXT_SANITIZED"  # a name or id contained unsafe characters
    # Added with `:count` for every non-zero `omitted` entry, e.g. DRONES_OMITTED:7.
    DRONES_OMITTED = "DRONES_OMITTED"
    HUBS_OMITTED = "HUBS_OMITTED"
    ACTIVE_INCIDENTS_OMITTED = "ACTIVE_INCIDENTS_OMITTED"
    RECOVERED_ALERTS_OMITTED = "RECOVERED_ALERTS_OMITTED"


class DroneFlag(StrEnum):
    """Facts about one drone, most urgent first (the roster is sorted by this order)."""

    EMERGENCY_LANDING = (
        "EMERGENCY_LANDING"  # a failure is happening: it is flying to a landing point
    )
    GROUNDED = "GROUNDED"  # MAINTENANCE where an emergency flight stopped (needs service)
    LOW_BATTERY = "LOW_BATTERY"  # below the model's reserve and not charging
    RECALLED = "RECALLED"  # its order was cancelled in flight; it returns with the parcel
    RECIPIENT_UNAVAILABLE_PENDING = "RECIPIENT_UNAVAILABLE_PENDING"  # attempt not yet made
    RETURNING_WITH_PARCEL = "RETURNING_WITH_PARCEL"  # the handover failed; the parcel is on board
    YIELDING_TO_LPR = "YIELDING_TO_LPR"  # standing still outside the helicopter's safety zone


FLAG_PRIORITY: tuple[DroneFlag, ...] = tuple(DroneFlag)


class IncidentKind(StrEnum):
    EMERGENCY_LANDING_IN_PROGRESS = "EMERGENCY_LANDING_IN_PROGRESS"
    DRONE_GROUNDED = "DRONE_GROUNDED"


class WarningKind(StrEnum):
    LPR_HELICOPTER_ACTIVE = "LPR_HELICOPTER_ACTIVE"
    RAIN_WARNING_ACTIVE = "RAIN_WARNING_ACTIVE"


class Omitted(Frozen):
    """How many entries of each list are NOT in this snapshot (caps and the byte budget)."""

    drones: int = 0
    hubs: int = 0
    active_incidents: int = 0
    recovered_alerts: int = 0


class Simulation(Frozen):
    # True only with a fresh worker heartbeat. The three modes are what the database says; a mode
    # acts only while the worker runs.
    worker_running: bool
    worker_heartbeat_age_s: int | None
    auto_dispatch: bool
    order_simulation: bool
    random_incidents: bool


class OrdersOpen(Frozen):
    """Orders that are not finished: the PRESENT."""

    created: int
    awaiting_handover: int
    # READY_FOR_PICKUP and no active mission: waiting for a drone.
    waiting_for_drone: int
    # READY_FOR_PICKUP with an active mission that has not taken off yet.
    assigned_not_departed: int
    # OUT_FOR_DELIVERY with an active mission: a parcel really on its way.
    in_delivery: int
    other: int


class OrdersHistory(Frozen):
    """Finished orders: HISTORY, never current state.

    `interrupted` orders keep the status OUT_FOR_DELIVERY forever (a drone failure ended their
    delivery without a new status); they are NOT being delivered.
    """

    delivered_last_60_min: int
    delivery_failed_last_60_min: int
    cancelled_last_60_min: int
    interrupted_last_60_min: int
    delivered_all_time: int
    delivery_failed_all_time: int
    cancelled_all_time: int
    interrupted_all_time: int


class Summary(Frozen):
    drones_total: int
    drones_by_status: dict[str, int]
    drones_docked: int
    drones_dispatchable: int
    orders_open: OrdersOpen
    orders_history: OrdersHistory
    # Emergencies that need attention NOW (landing in progress or still grounded); the true count,
    # also when the list below is capped.
    active_incident_count: int
    # Emergencies whose drone is back in service but whose alert was never acknowledged.
    recovered_alert_count: int


class Incident(Frozen):
    kind: IncidentKind
    drone_id: str
    mission_id: str
    order_id: str | None
    since: str
    # The emergency reason code of a grounded drone (DRONE_FAILURE, BATTERY_CRITICAL, ...).
    reason: str | None
    # A drone-failure ground-crew recovery will move it to a Hub; otherwise it needs an operator.
    recovery_pending: bool | None
    acknowledged: bool | None


class RecoveredAlert(Frozen):
    """An emergency that is over (its drone is no longer grounded) and was not acknowledged."""

    drone_id: str
    mission_id: str
    order_id: str | None
    reason: str
    at: str


class OperationalWarning(Frozen):
    """A fleet-wide condition. Not a drone emergency."""

    kind: WarningKind
    since: str | None
    until: str | None


class HubRow(Frozen):
    id: str
    name: str
    capacity: int
    docked: int
    free: int
    dispatchable: int
    waiting_orders: int


class FlightRow(Frozen):
    phase: str
    purpose: str
    order_id: str | None
    # The Hub this flight will land at (the planned return Hub while outbound), not a destination.
    landing_hub: str
    delivered: bool


class DroneRow(Frozen):
    id: str
    status: str
    battery_pct: int
    at_hub: str | None
    flight: FlightRow | None
    flags: list[DroneFlag]


class FleetContext(Frozen):
    schema_version: str
    captured_at: str
    data_status: DataStatus
    limitations: list[str]
    truncated: bool
    omitted: Omitted
    simulation: Simulation
    summary: Summary
    active_incidents: list[Incident]
    operational_warnings: list[OperationalWarning]
    recovered_alerts: list[RecoveredAlert]
    hubs: list[HubRow]
    drones: list[DroneRow]


def apply_omissions(context: FleetContext, omitted: Omitted) -> FleetContext:
    """The context with `omitted` recorded and every consequence made visible.

    The `*_OMITTED:n` limitations are recomputed from `omitted` (never accumulated), `truncated`
    and `data_status` follow from the limitations, so an omission can never be silent.
    """
    base = [item for item in context.limitations if "_OMITTED" not in item.split(":")[0]]
    codes = [
        f"{Limitation.DRONES_OMITTED.value}:{omitted.drones}" if omitted.drones else "",
        f"{Limitation.HUBS_OMITTED.value}:{omitted.hubs}" if omitted.hubs else "",
        (
            f"{Limitation.ACTIVE_INCIDENTS_OMITTED.value}:{omitted.active_incidents}"
            if omitted.active_incidents
            else ""
        ),
        (
            f"{Limitation.RECOVERED_ALERTS_OMITTED.value}:{omitted.recovered_alerts}"
            if omitted.recovered_alerts
            else ""
        ),
    ]
    codes = [code for code in codes if code]
    limitations = [*base, *codes]
    return context.model_copy(
        update={
            "omitted": omitted,
            "limitations": limitations,
            "truncated": bool(codes),
            "data_status": DataStatus.DEGRADED if limitations else DataStatus.COMPLETE,
        }
    )
