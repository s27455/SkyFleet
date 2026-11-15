"""Builders shared by the fleet-context tests. Nothing here can reach the network."""

from datetime import UTC, datetime, timedelta

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.ai.errors import UpstreamError, UpstreamKind
from app.ai.types import TransportRequest, TransportResult, TransportUsage
from app.config import Settings
from app.fleet_context.schemas import (
    SCHEMA_VERSION,
    DataStatus,
    DroneFlag,
    DroneRow,
    FleetContext,
    FlightRow,
    HubRow,
    Incident,
    IncidentKind,
    Omitted,
    OperationalWarning,
    OrdersHistory,
    OrdersOpen,
    RecoveredAlert,
    Simulation,
    Summary,
    WarningKind,
    apply_omissions,
)
from app.missions.models import Mission, MissionPurpose, MissionStatus
from app.simulation.models import MissionFlight

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
FAKE_KEY = "sk-ant-api03-THIS-IS-A-FAKE-TEST-KEY"


# --- pure contexts for the renderer tests ------------------------------------------------------


def drone_row(index: int, *, flagged: bool = False) -> DroneRow:
    return DroneRow(
        id=f"DRN-{index:03d}",
        status="IN_FLIGHT" if flagged else "IDLE",
        battery_pct=12 if flagged else 100,
        at_hub=None if flagged else "hub-forum-gdansk",
        flight=FlightRow(
            phase="OUTBOUND",
            purpose="DELIVERY",
            order_id=f"ORD-{index:08d}",
            landing_hub="hub-centrum-handlowe-osowa",
            delivered=False,
        )
        if flagged
        else None,
        flags=[DroneFlag.LOW_BATTERY] if flagged else [],
    )


def hand_context(
    *,
    drones: int = 0,
    flagged: int = 0,
    hubs: int = 2,
    incidents: int = 0,
    recovered: int = 0,
    warnings: bool = False,
    limitations: tuple[str, ...] = (),
) -> FleetContext:
    """A synthetic context. The first `flagged` drones carry a flag (flagged rows come first)."""
    rows = [drone_row(i, flagged=i <= flagged) for i in range(1, drones + 1)]
    context = FleetContext(
        schema_version=SCHEMA_VERSION,
        captured_at="2026-11-12T10:00:00Z",
        data_status=DataStatus.COMPLETE,
        limitations=list(limitations),
        truncated=False,
        omitted=Omitted(),
        simulation=Simulation(
            worker_running=True,
            worker_heartbeat_age_s=0,
            auto_dispatch=True,
            order_simulation=False,
            random_incidents=False,
        ),
        summary=Summary(
            drones_total=drones,
            drones_by_status={"IDLE": drones, "IN_FLIGHT": 0, "CHARGING": 0, "MAINTENANCE": 0},
            drones_docked=drones,
            drones_dispatchable=drones,
            orders_open=OrdersOpen(
                created=0,
                awaiting_handover=0,
                waiting_for_drone=0,
                assigned_not_departed=0,
                in_delivery=0,
                other=0,
            ),
            orders_history=OrdersHistory(
                delivered_last_60_min=1,
                delivery_failed_last_60_min=0,
                cancelled_last_60_min=0,
                interrupted_last_60_min=0,
                delivered_all_time=2,
                delivery_failed_all_time=0,
                cancelled_all_time=0,
                interrupted_all_time=0,
            ),
            active_incident_count=incidents,
            recovered_alert_count=recovered,
        ),
        active_incidents=[
            Incident(
                kind=IncidentKind.DRONE_GROUNDED,
                drone_id=f"DRN-{900 + i}",
                mission_id=f"MIS-{i:08d}",
                order_id=None,
                since="2026-11-12T09:00:00Z",
                reason="DRONE_FAILURE",
                recovery_pending=True,
                acknowledged=False,
            )
            for i in range(incidents)
        ],
        operational_warnings=[
            OperationalWarning(kind=WarningKind.RAIN_WARNING_ACTIVE, since=None, until=None)
        ]
        if warnings
        else [],
        recovered_alerts=[
            RecoveredAlert(
                drone_id=f"DRN-{800 + i}",
                mission_id=f"MIS-R{i:07d}",
                order_id=None,
                reason="DRONE_FAILURE",
                at="2026-11-12T08:00:00Z",
            )
            for i in range(recovered)
        ],
        hubs=[
            HubRow(
                id=f"hub-{i}",
                name=f"Hub number {i}",
                capacity=50,
                docked=3,
                free=47,
                dispatchable=1,
                waiting_orders=0,
            )
            for i in range(hubs)
        ],
        drones=rows,
    )
    return apply_omissions(context, Omitted())


# --- database rows for the snapshot tests ------------------------------------------------------


def add_mission(
    session: Session,
    mission_id: str,
    drone_id: str,
    *,
    status: MissionStatus,
    order_id: str | None = None,
    hub: str = "hub-forum-gdansk",
) -> Mission:
    mission = Mission(
        id=mission_id,
        order_id=order_id,
        purpose=(MissionPurpose.DELIVERY if order_id else MissionPurpose.RELOCATION).value,
        drone_id=drone_id,
        origin_hub_id=hub,
        return_hub_id=hub,
        status=status.value,
        origin_to_destination_km=1.0,
        destination_to_return_km=0.0 if order_id is None else 1.0,
        total_km=1.0,
        expected_energy_pct=1.0,
        worst_case_energy_pct=1.0,
    )
    session.add(mission)
    session.flush()
    return mission


def add_flight(
    session: Session,
    mission_id: str,
    *,
    phase: str,
    longitude: float = 18.60,
    latitude: float = 54.40,
    hub: str = "hub-forum-gdansk",
    **fields: object,
) -> MissionFlight:
    values: dict[str, object] = {
        "mission_id": mission_id,
        "phase": phase,
        "started_at": NOW - timedelta(minutes=5),
        "start_battery_pct": 90.0,
        "battery_pct": 80.0,
        "legs": [],
        "pace_s_per_km": 60.0,
        "planned_return_hub_id": hub,
        "landing_target_hub_id": hub,
        "longitude": longitude,
        "latitude": latitude,
        "progress": 0.5,
    }
    values.update(fields)
    flight = MissionFlight(**values)
    session.add(flight)
    session.flush()
    return flight


# --- AI fakes (a small copy: the AI tests' fakes live in another test package) -----------------


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def ok_result(text: str = "An answer.") -> TransportResult:
    return TransportResult(
        text=text,
        usage=TransportUsage(input_tokens=1_000, output_tokens=100),
        stop_reason="end_turn",
        provider_request_id="req_fake_001",
    )


class FakeTransport:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.requests: list[TransportRequest] = []

    def send(self, request: TransportRequest) -> TransportResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ok_result()


def upstream(kind: str, status: int | None = None) -> UpstreamError:
    return UpstreamError(UpstreamKind(kind), status_code=status)


def ai_settings(**overrides: object) -> Settings:
    """AI enabled with a FAKE key, never reading `.env` or the real environment."""
    values: dict[str, object] = {
        "ai_enabled": True,
        "anthropic_api_key": SecretStr(FAKE_KEY),
        "hub_dock_proximity_m": 50,
        "sim_heartbeat_stale_seconds": 10,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]
