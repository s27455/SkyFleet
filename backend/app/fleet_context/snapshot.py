"""The read-only fleet snapshot builder (Feature 025).

CONSISTENCY. Everything is read inside ONE transaction opened as PostgreSQL `REPEATABLE READ`,
`READ ONLY`, with a `statement_timeout` (see `read_only_snapshot`). Every query therefore sees the
same committed instant, so counts and rows cannot contradict each other because the simulation
worker committed in between. The worker commits many small transactions (one per flight, one per
charging step, ...): a snapshot never shows half of one, but different entities may differ by up to
one worker tick. A read-only repeatable-read transaction never blocks the worker and never fails
with a serialization error.

READ-ONLY BY CONSTRUCTION. The database itself refuses any write in that transaction; the session
additionally refuses to flush, and the transaction is always rolled back, never committed. Only
functions that read are imported (an architecture test pins the exact allowlist). Nothing here
calls a service with side effects, takes a row lock, or touches `operational_events` (history, free
text and unbounded growth are deliberately out of v1).

SOURCES (authoritative, reused rather than re-derived)
  docked / occupancy   missions.presence (status and position within the docking radius)
  dispatchable         dispatch.service.available_drones_by_hub (the dispatcher's own rule)
  active missions      dispatch.service.active_claims
  emergency geometry   simulation.recovery.POSITION_TOLERANCE_DEG (the recovery rule's tolerance)
  helicopter / rain    simulation.lpr.active_scenario, weather.service.get_status
  worker alive         simulation.heartbeat
Order status is NOT trusted alone: an order interrupted by a drone failure keeps OUT_FOR_DELIVERY
forever, so "in delivery" requires an active mission and the rest is counted as interrupted.

TEXT. No free text from the database reaches the model except Hub names and ids, which are cut to
an allow-list of characters (letters, digits and a little punctuation) and a length. No addresses,
coordinates, event reasons or mode summaries are included.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, event, exists, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.models import AUTO_DISPATCH, DispatchAutoState
from app.dispatch.service import active_claims, available_drones_by_hub
from app.drones.models import Drone, DroneModel, DroneStatus
from app.fleet_context.schemas import (
    FLAG_PRIORITY,
    HISTORY_WINDOW_SECONDS,
    LABEL_MAX_CHARS,
    MAX_DRONES,
    MAX_HUBS,
    MAX_INCIDENTS,
    MAX_RECOVERED_ALERTS,
    SCHEMA_VERSION,
    STATEMENT_TIMEOUT_MS,
    DataStatus,
    DroneFlag,
    DroneRow,
    FleetContext,
    FlightRow,
    HubRow,
    Incident,
    IncidentKind,
    Limitation,
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
from app.hubs.repository import list_hubs
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.missions.presence import docked_hub, hub_occupancy
from app.orders.models import ORDER_SIMULATION, DeliveryOrder, OrderSimulationState, OrderStatus
from app.simulation.clock import as_utc, utcnow
from app.simulation.heartbeat import is_fresh, last_heartbeat
from app.simulation.lpr import active_scenario, is_yielding
from app.simulation.models import (
    RANDOM_INCIDENTS,
    EmergencyReason,
    FlightPhase,
    IncidentAcknowledgement,
    IncidentSchedulerState,
    MissionFlight,
)
from app.simulation.recovery import POSITION_TOLERANCE_DEG
from app.weather.service import get_status as rain_warning_status

_ACTIVE_MISSION = [status.value for status in ACTIVE_MISSION_STATUSES]
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_LABEL_PUNCTUATION = frozenset(" .,'&()-/")


# --- the read-only transaction ----------------------------------------------------------------


def _refuse_flush(*_: Any) -> None:
    raise RuntimeError("the fleet snapshot is read-only: nothing may be written")


@contextmanager
def read_only_snapshot(factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session whose single transaction is a read-only repeatable-read snapshot.

    The isolation level and the read-only flag must be set before the first statement, so the
    session is always fresh. `SET LOCAL` limits only this transaction. On SQLite (unit tests) the
    PostgreSQL-only options are skipped. Always rolled back, never committed.
    """
    session = factory()
    try:
        session.autoflush = False
        event.listen(session, "before_flush", _refuse_flush)
        if session.get_bind().dialect.name == "postgresql":
            session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
            session.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
        else:
            session.connection()
        yield session
    finally:
        session.rollback()
        session.close()


# --- text safety ------------------------------------------------------------------------------


class _Cleaner:
    """Cuts database text down to a safe allow-list and remembers that it had to."""

    def __init__(self) -> None:
        self.changed = False

    def ident(self, value: str) -> str:
        if _ID.fullmatch(value):
            return value
        self.changed = True
        return re.sub(r"[^A-Za-z0-9_.:-]", "?", value)[:64] or "?"

    def label(self, value: str) -> str:
        kept = [
            char
            if char.isalnum() or char in _LABEL_PUNCTUATION
            else (" " if char.isspace() else "?")
            for char in value
        ]
        cleaned = re.sub(r" +", " ", "".join(kept)).strip()[:LABEL_MAX_CHARS] or "?"
        if cleaned != value:
            self.changed = True
        return cleaned


def iso(moment: datetime) -> str:
    return as_utc(moment).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- the builder ------------------------------------------------------------------------------


def build_fleet_context(
    factory: sessionmaker[Session], settings: Settings, now: datetime | None = None
) -> FleetContext:
    """The snapshot of the present, or an exception (the caller fails closed)."""
    captured = as_utc(now or utcnow()).replace(microsecond=0)
    with read_only_snapshot(factory) as session:
        return _assemble(session, settings, captured)


def _enabled(row: Any) -> bool:
    return bool(row.enabled) if row is not None else False


def _assemble(session: Session, settings: Settings, captured: datetime) -> FleetContext:
    cleaner = _Cleaner()
    limitations: list[str] = []
    radius = settings.hub_dock_proximity_m

    # simulation: is anything advancing, and which modes are on
    beat = last_heartbeat(session)
    running = is_fresh(beat, captured, settings.sim_heartbeat_stale_seconds)
    simulation = Simulation(
        worker_running=running,
        worker_heartbeat_age_s=None
        if beat is None
        else max(0, int((captured - beat).total_seconds())),
        auto_dispatch=_enabled(session.get(DispatchAutoState, AUTO_DISPATCH)),
        order_simulation=_enabled(session.get(OrderSimulationState, ORDER_SIMULATION)),
        random_incidents=_enabled(session.get(IncidentSchedulerState, RANDOM_INCIDENTS)),
    )
    if not running:
        limitations.append(Limitation.WORKER_NOT_RUNNING.value)

    # the fleet, as the domain itself defines docking and dispatch eligibility
    hubs = list(list_hubs(session))
    drone_rows = session.execute(
        select(Drone, DroneModel.min_battery_reserve_pct)
        .join(DroneModel, DroneModel.id == Drone.model_id)
        .order_by(Drone.id)
    ).all()
    drones = [drone for drone, _ in drone_rows]
    reserve = {drone.id: pct for drone, pct in drone_rows}
    _, active_drone_ids = active_claims(session)
    occupancy = hub_occupancy(drones, hubs, radius)
    dispatchable = available_drones_by_hub(drones, hubs, active_drone_ids, radius)

    flights = session.execute(
        select(MissionFlight, Mission)
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .where(MissionFlight.phase.not_in([FlightPhase.LANDED.value, FlightPhase.EMERGENCY.value]))
        .order_by(MissionFlight.started_at, MissionFlight.mission_id)
    ).all()
    flight_of = {mission.drone_id: (flight, mission) for flight, mission in flights}
    if {d.id for d in drones if d.status == DroneStatus.IN_FLIGHT.value} != set(flight_of):
        limitations.append(Limitation.FLIGHT_STATUS_MISMATCH.value)

    # emergencies: what is happening now, and what is over
    approach = sorted(
        (
            Incident(
                kind=IncidentKind.EMERGENCY_LANDING_IN_PROGRESS,
                drone_id=cleaner.ident(mission.drone_id),
                mission_id=cleaner.ident(mission.id),
                order_id=cleaner.ident(mission.order_id) if mission.order_id else None,
                since=iso(flight.failed_at or flight.started_at),
                reason=None,
                recovery_pending=None,
                acknowledged=None,
            )
            for flight, mission in flights
            if flight.phase == FlightPhase.EMERGENCY_APPROACH.value
        ),
        key=lambda item: (item.since, item.mission_id),
        reverse=True,
    )
    grounded_rows, recovered_total, recovered_rows = _emergencies(session)
    grounded = [
        Incident(
            kind=IncidentKind.DRONE_GROUNDED,
            drone_id=cleaner.ident(drone_id),
            mission_id=cleaner.ident(mission_id),
            order_id=cleaner.ident(order_id) if order_id else None,
            since=iso(at),
            reason=cleaner.ident(reason or "UNKNOWN"),
            recovery_pending=reason == EmergencyReason.DRONE_FAILURE.value,
            acknowledged=acknowledged_at is not None,
        )
        for mission_id, drone_id, order_id, reason, at, acknowledged_at in grounded_rows
    ]
    incidents = [*approach, *grounded]
    recovered = [
        RecoveredAlert(
            drone_id=cleaner.ident(drone_id),
            mission_id=cleaner.ident(mission_id),
            order_id=cleaner.ident(order_id) if order_id else None,
            reason=cleaner.ident(reason or "UNKNOWN"),
            at=iso(at),
        )
        for mission_id, drone_id, order_id, reason, at, _ in recovered_rows
    ]
    landing_drones = {item.drone_id for item in approach}
    grounded_drones = {item.drone_id for item in grounded}

    warnings: list[OperationalWarning] = []
    scenario = active_scenario(session, captured)
    if scenario is not None:
        warnings.append(
            OperationalWarning(
                kind=WarningKind.LPR_HELICOPTER_ACTIVE,
                since=iso(scenario.started_at),
                until=iso(scenario.ends_at),
            )
        )
    rain = rain_warning_status(session)
    if rain.active:
        warnings.append(
            OperationalWarning(
                kind=WarningKind.RAIN_WARNING_ACTIVE,
                since=iso(rain.activated_at) if rain.activated_at else None,
                until=None,
            )
        )

    # the roster: flagged drones first, then drones in flight or on a mission, then the rest
    status_counts = {status.value: 0 for status in DroneStatus}
    roster: list[tuple[tuple[int, int, str], DroneRow]] = []
    for drone in drones:
        if drone.status in status_counts:
            status_counts[drone.status] += 1
        else:
            status_counts["OTHER"] = status_counts.get("OTHER", 0) + 1
        flags = _flags(drone, reserve[drone.id], flight_of.get(drone.id), captured)
        if cleaner.ident(drone.id) in landing_drones:
            flags.append(DroneFlag.EMERGENCY_LANDING)
        if cleaner.ident(drone.id) in grounded_drones:
            flags.append(DroneFlag.GROUNDED)
        flags = sorted(set(flags), key=FLAG_PRIORITY.index)
        pair = flight_of.get(drone.id)
        hub = docked_hub(drone, hubs, radius)
        row = DroneRow(
            id=cleaner.ident(drone.id),
            status=cleaner.ident(drone.status),
            battery_pct=drone.battery_pct,
            at_hub=cleaner.ident(hub.id) if hub is not None else None,
            flight=None
            if pair is None
            else FlightRow(
                phase=cleaner.ident(pair[0].phase),
                purpose=cleaner.ident(pair[1].purpose),
                order_id=cleaner.ident(pair[1].order_id) if pair[1].order_id else None,
                landing_hub=cleaner.ident(pair[0].landing_target_hub_id),
                delivered=pair[0].delivered_at is not None,
            ),
            flags=flags,
        )
        # Roster priority (deterministic): 0 flagged drones, by flag urgency; 1 other drones in
        # flight or holding an active mission (ASSIGNED or IN_FLIGHT); 2 all the rest. Ties by id.
        if flags:
            key = (0, FLAG_PRIORITY.index(flags[0]), row.id)
        elif (
            drone.status == DroneStatus.IN_FLIGHT.value
            or drone.id in active_drone_ids
            or drone.id in flight_of
        ):
            key = (1, 0, row.id)
        else:
            key = (2, 0, row.id)
        roster.append((key, row))
    if "OTHER" in status_counts:
        limitations.append(Limitation.UNKNOWN_DRONE_STATUS.value)
    ordered = [row for _, row in sorted(roster, key=lambda item: item[0])]

    # hubs
    waiting_by_hub = _waiting_orders_by_hub(session)
    hub_rows: list[HubRow] = []
    for hub in hubs:
        docked = occupancy.get(hub.id, 0)
        if docked > hub.drone_capacity:
            limitations.append(f"{Limitation.HUB_OVER_CAPACITY.value}:{cleaner.ident(hub.id)}")
        hub_rows.append(
            HubRow(
                id=cleaner.ident(hub.id),
                name=cleaner.label(hub.name),
                capacity=hub.drone_capacity,
                docked=docked,
                free=max(0, hub.drone_capacity - docked),
                dispatchable=len(dispatchable.get(hub.id, [])),
                waiting_orders=waiting_by_hub.get(hub.id, 0),
            )
        )

    orders_open, orders_history, unknown_orders = _orders(session, captured)
    if unknown_orders:
        limitations.append(Limitation.UNKNOWN_ORDER_STATUS.value)
    if cleaner.changed:
        limitations.append(Limitation.TEXT_SANITIZED.value)

    context = FleetContext(
        schema_version=SCHEMA_VERSION,
        captured_at=iso(captured),
        data_status=DataStatus.COMPLETE,
        limitations=limitations,
        truncated=False,
        omitted=Omitted(),
        simulation=simulation,
        summary=Summary(
            drones_total=len(drones),
            drones_by_status=status_counts,
            drones_docked=sum(occupancy.values()),
            drones_dispatchable=sum(len(found) for found in dispatchable.values()),
            orders_open=orders_open,
            orders_history=orders_history,
            active_incident_count=len(incidents),
            recovered_alert_count=recovered_total,
        ),
        active_incidents=incidents[:MAX_INCIDENTS],
        operational_warnings=warnings,
        recovered_alerts=recovered[:MAX_RECOVERED_ALERTS],
        hubs=hub_rows[:MAX_HUBS],
        drones=ordered[:MAX_DRONES],
    )
    return apply_omissions(
        context,
        Omitted(
            drones=max(0, len(ordered) - MAX_DRONES),
            hubs=max(0, len(hub_rows) - MAX_HUBS),
            active_incidents=max(0, len(incidents) - MAX_INCIDENTS),
            recovered_alerts=max(0, recovered_total - MAX_RECOVERED_ALERTS),
        ),
    )


def _flags(
    drone: Drone,
    reserve_pct: int,
    pair: tuple[MissionFlight, Mission] | None,
    captured: datetime,
) -> list[DroneFlag]:
    flags: list[DroneFlag] = []
    if drone.battery_pct < reserve_pct and drone.status != DroneStatus.CHARGING.value:
        flags.append(DroneFlag.LOW_BATTERY)
    if pair is not None:
        flight = pair[0]
        if flight.recalled_at is not None:
            flags.append(DroneFlag.RECALLED)
        if flight.recipient_unavailable_at is not None and flight.handover_failed_at is None:
            flags.append(DroneFlag.RECIPIENT_UNAVAILABLE_PENDING)
        if flight.handover_failed_at is not None:
            flags.append(DroneFlag.RETURNING_WITH_PARCEL)
        if is_yielding(flight.legs, flight.started_at, captured):
            flags.append(DroneFlag.YIELDING_TO_LPR)
    return flags


def _emergencies(session: Session) -> tuple[list[Any], int, list[Any]]:
    """(grounded rows, number of recovered unacknowledged alerts, the newest of them).

    An emergency flight is the incident's record. It is ACTIVE while its drone is still in
    MAINTENANCE exactly where the flight stopped (the recovery rule's own test), and RECOVERED
    once the drone is back in service. A recovered emergency stays listed only while its alert is
    unacknowledged; an acknowledged, recovered one is history and is not read at all.
    """
    grounded_here = and_(
        Drone.status == DroneStatus.MAINTENANCE.value,
        func.abs(Drone.longitude - MissionFlight.longitude) <= POSITION_TOLERANCE_DEG,
        func.abs(Drone.latitude - MissionFlight.latitude) <= POSITION_TOLERANCE_DEG,
    )
    rows = (
        select(
            MissionFlight.mission_id,
            Mission.drone_id,
            Mission.order_id,
            MissionFlight.emergency_reason,
            MissionFlight.emergency_at,
            IncidentAcknowledgement.acknowledged_at,
        )
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .join(Drone, Drone.id == Mission.drone_id)
        .outerjoin(
            IncidentAcknowledgement, IncidentAcknowledgement.mission_id == MissionFlight.mission_id
        )
        .where(
            MissionFlight.phase == FlightPhase.EMERGENCY.value,
            MissionFlight.emergency_at.is_not(None),
        )
    )
    newest_first = (MissionFlight.emergency_at.desc(), MissionFlight.mission_id)
    grounded = session.execute(rows.where(grounded_here).order_by(*newest_first)).all()
    recovered_filter = and_(~grounded_here, IncidentAcknowledgement.mission_id.is_(None))
    total = session.scalar(
        select(func.count()).select_from(rows.where(recovered_filter).subquery())
    )
    recovered = session.execute(
        rows.where(recovered_filter).order_by(*newest_first).limit(MAX_RECOVERED_ALERTS)
    ).all()
    return list(grounded), int(total or 0), list(recovered)


def _orders(session: Session, captured: datetime) -> tuple[OrdersOpen, OrdersHistory, bool]:
    cutoff = captured - timedelta(seconds=HISTORY_WINDOW_SECONDS)
    has_active_mission = exists().where(
        Mission.order_id == DeliveryOrder.id, Mission.status.in_(_ACTIVE_MISSION)
    )
    ended_in_emergency_recently = exists().where(
        Mission.order_id == DeliveryOrder.id,
        MissionFlight.mission_id == Mission.id,
        MissionFlight.phase == FlightPhase.EMERGENCY.value,
        MissionFlight.delivered_at.is_(None),
        MissionFlight.ended_at > cutoff,
    )

    def count(*conditions: Any) -> int:
        statement = select(func.count()).select_from(DeliveryOrder).where(*conditions)
        return int(session.scalar(statement) or 0)

    by_status = dict(
        session.execute(
            select(DeliveryOrder.status, func.count()).group_by(DeliveryOrder.status)
        ).all()
    )
    known = {status.value for status in OrderStatus}
    other = sum(number for status, number in by_status.items() if status not in known)
    ready = DeliveryOrder.status == OrderStatus.READY_FOR_PICKUP.value
    out = DeliveryOrder.status == OrderStatus.OUT_FOR_DELIVERY.value
    last_hour = session.execute(
        select(
            func.count().filter(
                and_(
                    DeliveryOrder.status == OrderStatus.DELIVERED.value,
                    DeliveryOrder.delivered_at > cutoff,
                )
            ),
            func.count().filter(
                and_(
                    DeliveryOrder.status == OrderStatus.DELIVERY_FAILED.value,
                    DeliveryOrder.delivery_failed_at > cutoff,
                )
            ),
            func.count().filter(
                and_(
                    DeliveryOrder.status == OrderStatus.CANCELLED.value,
                    DeliveryOrder.cancelled_at > cutoff,
                )
            ),
        ).select_from(DeliveryOrder)
    ).one()
    open_orders = OrdersOpen(
        created=by_status.get(OrderStatus.CREATED.value, 0),
        awaiting_handover=by_status.get(OrderStatus.AWAITING_HANDOVER.value, 0),
        waiting_for_drone=count(ready, ~has_active_mission),
        assigned_not_departed=count(ready, has_active_mission),
        in_delivery=count(out, has_active_mission),
        other=other,
    )
    history = OrdersHistory(
        delivered_last_60_min=int(last_hour[0]),
        delivery_failed_last_60_min=int(last_hour[1]),
        cancelled_last_60_min=int(last_hour[2]),
        interrupted_last_60_min=count(out, ~has_active_mission, ended_in_emergency_recently),
        delivered_all_time=by_status.get(OrderStatus.DELIVERED.value, 0),
        delivery_failed_all_time=by_status.get(OrderStatus.DELIVERY_FAILED.value, 0),
        cancelled_all_time=by_status.get(OrderStatus.CANCELLED.value, 0),
        interrupted_all_time=count(out, ~has_active_mission),
    )
    return open_orders, history, other > 0


def _waiting_orders_by_hub(session: Session) -> dict[str, int]:
    has_active_mission = exists().where(
        Mission.order_id == DeliveryOrder.id, Mission.status.in_(_ACTIVE_MISSION)
    )
    rows = session.execute(
        select(DeliveryOrder.origin_hub_id, func.count())
        .where(DeliveryOrder.status == OrderStatus.READY_FOR_PICKUP.value, ~has_active_mission)
        .group_by(DeliveryOrder.origin_hub_id)
    ).all()
    return {hub_id: int(number) for hub_id, number in rows}
