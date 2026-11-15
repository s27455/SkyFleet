"""LPR helicopter scenario (Feature 018E): a priority helicopter, a moving zone, drones that yield.

A fictional simulation, not an aviation safety system. One scenario at a time is stored in
`lpr_scenarios` (shared by the API and the worker, so a restart keeps it). The helicopter flies a
fixed straight route at a constant speed, so its position is a pure function of the stored row and
the clock: nothing is written per tick.

Drones respond by standing still (a HOLD leg, `flight.hold_legs`) before they would meet the
helicopter, at the edge of its corridor (the hold distance either side of its route), so the zone
passes beside the drone, not over it; they fly on once the helicopter is far enough away. A drone
already inside the corridor that cannot leave it in time stands where it is, and the zone then
passes over it (nothing better exists for it). The worker decides this on each tick, inside the
flight's own transaction (`engine._yield_to_lpr`). Detection is predictive: it looks at
the drone's scheduled path and the helicopter's route over the next few seconds, not only at the
current distance, so a fast drone cannot cross the zone between two ticks unnoticed. Because both
motions are known, the hold's duration is computed exactly when it is inserted.

This module has the geometry (pure functions) and the scenario lifecycle. It never imports the
engine.
"""

import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.clock import as_utc
from app.config import Settings
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.missions.routing import Point
from app.simulation.flight import Leg, LegKind, hold_legs, lerp, position_at
from app.simulation.models import LprScenario, LprStatus

# One fixed west-to-east corridor across Gdańsk (fictional, deterministic). It runs about 1.1 km
# north of Galeria Bałtycka and well clear of the other Hubs, so drones leaving or docking at a Hub
# are never inside the zone when it opens, while deliveries heading into the corridor are affected.
ROUTE_START: Point = (18.46, 54.3925)
ROUTE_END: Point = (18.67, 54.3925)

_REF_LON, _REF_LAT = 18.56, 54.39
_METRES_PER_DEGREE = 111_320.0
_COS_LAT = math.cos(math.radians(_REF_LAT))

MIN_HOLD_S = 1.0
# How far past the release the hold is checked for a new conflict, and the step it is extended by.
RELEASE_CHECK_S = 60.0
RELEASE_STEP_S = 0.5
# A conflict this close to the start of a hold already in the schedule is that hold's own.
HANDLED_TOLERANCE_S = 1e-3
# A cap on how far ahead a tick looks, whatever the tick spacing was.
MAX_LOOKAHEAD_S = 60.0


class LprAlreadyActiveError(Exception):
    def __init__(self) -> None:
        super().__init__("An LPR helicopter scenario is already active")


@dataclass(frozen=True)
class Zone:
    """The parameters of a running scenario, everything the conflict check needs."""

    scenario_id: str
    origin: str
    started_at: datetime
    ends_at: datetime
    start: Point
    end: Point
    speed_ms: float
    radius_m: float
    margin_m: float
    clear_extra_m: float

    @property
    def duration_s(self) -> float:
        return (self.ends_at - self.started_at).total_seconds()

    @property
    def hold_threshold_m(self) -> float:
        """A drone is held when it comes this close to the helicopter (zone radius plus margin)."""
        return self.radius_m + self.margin_m

    @property
    def clear_threshold_m(self) -> float:
        """A held drone is released when the helicopter is at least this far away."""
        return self.hold_threshold_m + self.clear_extra_m


@dataclass(frozen=True)
class HoldPlan:
    at_s: float  # schedule offset where the drone stops (not before now)
    point: Point
    hold_s: float


def _xy(point: Point) -> tuple[float, float]:
    """Metres east and north of a fixed reference point (fine for a few tens of km)."""
    return (
        (point[0] - _REF_LON) * _COS_LAT * _METRES_PER_DEGREE,
        (point[1] - _REF_LAT) * _METRES_PER_DEGREE,
    )


def route_length_m() -> float:
    (x0, y0), (x1, y1) = _xy(ROUTE_START), _xy(ROUTE_END)
    return math.hypot(x1 - x0, y1 - y0)


def zone_of(row: LprScenario) -> Zone:
    return Zone(
        scenario_id=row.id,
        origin=row.origin,
        started_at=as_utc(row.started_at),
        ends_at=as_utc(row.ends_at),
        start=(row.start_longitude, row.start_latitude),
        end=(row.end_longitude, row.end_latitude),
        speed_ms=row.speed_ms,
        radius_m=row.radius_m,
        margin_m=row.margin_m,
        clear_extra_m=row.clear_extra_m,
    )


def helicopter_position(zone: Zone, now: datetime) -> Point:
    """Where the helicopter is at `now`: on its route, clamped to the two ends."""
    elapsed = min(max((now - zone.started_at).total_seconds(), 0.0), zone.duration_s)
    return lerp(zone.start, zone.end, elapsed / zone.duration_s if zone.duration_s > 0 else 1.0)


def is_yielding(legs: list[dict[str, Any]], started: datetime, now: datetime) -> bool:
    """Whether a flight with these stored legs is standing in a hold at `now`."""
    elapsed = (now - as_utc(started)).total_seconds()
    return any(
        entry["kind"] == LegKind.HOLD.value
        and entry["start_s"] <= elapsed < entry["start_s"] + entry["duration_s"]
        for entry in legs
    )


# --- conflict prediction and hold duration (pure) ---------------------------------------------


def _point_on(leg: Leg, at_s: float) -> Point:
    if leg.duration_s <= 0:
        return leg.origin
    return lerp(leg.origin, leg.target, (at_s - leg.start_s) / leg.duration_s)


def _first_within(
    r0: tuple[float, float], r1: tuple[float, float], span: float, limit: float
) -> float | None:
    """Earliest time in [0, span] at which a relative vector moving r0 -> r1 is within `limit`."""
    c = r0[0] ** 2 + r0[1] ** 2 - limit**2
    if c <= 0:
        return 0.0
    if span <= 0:
        return None
    dx, dy = (r1[0] - r0[0]) / span, (r1[1] - r0[1]) / span
    a = dx * dx + dy * dy
    if a == 0:
        return None
    b = r0[0] * dx + r0[1] * dy
    disc = b * b - a * c
    if disc < 0:
        return None
    tau = (-b - math.sqrt(disc)) / a
    return tau if 0.0 <= tau <= span else None


def first_conflict(
    legs: list[Leg], from_s: float, to_s: float, zone: Zone, flight_started: datetime
) -> float | None:
    """The first schedule offset in [from_s, to_s] at which a moving or waiting drone would be
    within the hold distance of the helicopter, or None.

    Both motions are straight lines within each leg, so the closest approach is solved exactly: the
    result does not depend on how often the worker ticks. Time already spent in a hold is skipped
    (a held drone stands at the hold distance by construction and is not a new conflict).
    """
    offset = (flight_started - zone.started_at).total_seconds()  # helicopter time = offset + t
    lo = max(from_s, -offset)
    hi = min(to_s, zone.duration_s - offset)
    if hi < lo:
        return None  # the helicopter is not in the air during this window
    start_xy, end_xy = _xy(zone.start), _xy(zone.end)
    duration = zone.duration_s
    velocity = ((end_xy[0] - start_xy[0]) / duration, (end_xy[1] - start_xy[1]) / duration)

    def helicopter(t: float) -> tuple[float, float]:
        return (start_xy[0] + velocity[0] * (t + offset), start_xy[1] + velocity[1] * (t + offset))

    holds = [item.start_s for item in legs if item.kind == LegKind.HOLD]
    for leg in legs:
        if leg.kind == LegKind.HOLD:
            continue
        if leg.duration_s > 0 and leg.end_s <= lo:
            continue  # already flown
        a, b = max(leg.start_s, lo), min(leg.end_s, hi)
        if b < a:
            continue
        pa, pb = _xy(_point_on(leg, a)), _xy(_point_on(leg, b))
        ha, hb = helicopter(a), helicopter(b)
        hit = _first_within(
            (pa[0] - ha[0], pa[1] - ha[1]),
            (pb[0] - hb[0], pb[1] - hb[1]),
            b - a,
            zone.hold_threshold_m,
        )
        if hit is None:
            continue
        # A conflict where a hold already starts is handled: the legs before a hold still end at
        # the hold distance, and that must not insert a second hold on every tick.
        if any(abs(start - (a + hit)) <= HANDLED_TOLERANCE_S for start in holds):
            continue
        return a + hit
    return None


def hold_duration_s(point: Point, at_s: float, zone: Zone, flight_started: datetime) -> float:
    """How long a drone standing at `point` from offset `at_s` has to wait.

    Until the helicopter is at least the clear distance away for good, or the scenario ends (the
    zone is gone then), whichever is first; never less than `MIN_HOLD_S`.
    """
    offset = (flight_started - zone.started_at).total_seconds()
    helicopter_now = at_s + offset
    start_xy, end_xy = _xy(zone.start), _xy(zone.end)
    duration = zone.duration_s
    vx, vy = (end_xy[0] - start_xy[0]) / duration, (end_xy[1] - start_xy[1]) / duration
    px, py = _xy(point)
    dx, dy = start_xy[0] - px, start_xy[1] - py
    a = vx * vx + vy * vy
    b = dx * vx + dy * vy
    c = dx * dx + dy * dy - zone.clear_threshold_m**2
    disc = b * b - a * c
    clear = helicopter_now if a == 0 or disc < 0 else (-b + math.sqrt(disc)) / a
    return max(min(clear, duration) - helicopter_now, MIN_HOLD_S)


def standing_clearance_m(point: Point, at_s: float, zone: Zone, flight_started: datetime) -> float:
    """How close the helicopter will come to `point` from schedule offset `at_s` on.

    A drone standing there from `at_s` on is overflown by the zone unless this exceeds the hold
    distance, so it is the test for "outside the helicopter's corridor".
    """
    offset = (flight_started - zone.started_at).total_seconds()
    first = min(max(at_s + offset, 0.0), zone.duration_s)
    start_xy, end_xy = _xy(zone.start), _xy(zone.end)
    duration = zone.duration_s
    vx, vy = (end_xy[0] - start_xy[0]) / duration, (end_xy[1] - start_xy[1]) / duration
    px, py = _xy(point)
    along = ((px - start_xy[0]) * vx + (py - start_xy[1]) * vy) / (vx * vx + vy * vy)
    closest = min(max(along, first), duration)
    return math.hypot(start_xy[0] + vx * closest - px, start_xy[1] + vy * closest - py)


def latest_safe_time(
    legs: list[Leg], now_s: float, conflict_s: float, zone: Zone, flight_started: datetime
) -> float:
    """The moment in [now, conflict] at which the drone should stand still, outside the corridor.

    Standing still where the helicopter is about to pass is no yield, so the drone stops before it
    enters the corridor (the hold distance either side of the helicopter's route), not merely at
    the moment it would meet the helicopter: the last such moment. A drone that is already inside
    the corridor flies on to the first point outside it if it gets there before the conflict (for
    example after a delivery at the corridor's edge). If it cannot, that is now: nothing better
    exists for a drone that cannot leave in time, and the zone then passes over it.
    """

    def safe(at_s: float) -> bool:
        point = position_at(legs, at_s)
        return standing_clearance_m(point, at_s, zone, flight_started) >= zone.hold_threshold_m

    if not safe(now_s):
        unsafe, t = now_s, now_s
        while t < conflict_s:
            t = min(t + 0.05, conflict_s)
            if safe(t):
                exit_s = t
                for _ in range(24):  # the first moment outside the corridor
                    middle = (unsafe + exit_s) / 2
                    if safe(middle):
                        exit_s = middle
                    else:
                        unsafe = middle
                return exit_s
            unsafe = t
        return now_s
    last_safe, first_unsafe, t = now_s, None, now_s
    while t < conflict_s and first_unsafe is None:
        t = min(t + 0.05, conflict_s)
        if safe(t):
            last_safe = t
        else:
            first_unsafe = t
    if first_unsafe is None:
        return conflict_s  # only meeting the helicopter in time and place is the conflict
    for _ in range(24):  # refine to well under a millisecond
        middle = (last_safe + first_unsafe) / 2
        if safe(middle):
            last_safe = middle
        else:
            first_unsafe = middle
    return last_safe


def plan_hold(
    legs: list[Leg], elapsed_s: float, flight_started: datetime, zone: Zone, lookahead_s: float
) -> HoldPlan | None:
    """Where and for how long a drone must stand still to stay out of the zone, or None.

    The window is [now, now + lookahead]. If the drone would meet the helicopter in it, it stops at
    the last point where standing is still outside the helicopter's corridor (see
    `latest_safe_time`), which may be a moment ahead of its position now, so it is already standing
    when it gets there, and waits until the helicopter is clear.
    """
    conflict_s = first_conflict(legs, elapsed_s, elapsed_s + lookahead_s, zone, flight_started)
    if conflict_s is None:
        return None
    at_s = latest_safe_time(legs, elapsed_s, conflict_s, zone, flight_started)
    if at_s >= legs[-1].end_s:
        return None  # the flight ends first
    point = position_at(legs, at_s)
    hold_s = hold_duration_s(point, at_s, zone, flight_started)
    # The helicopter being clear of the spot is not enough: a drone that flies on across the
    # corridor can still be on a collision course with it. Wait until the drone's own continued
    # path is conflict-free (it is, at the latest, once the scenario is over).
    for _ in range(int(zone.duration_s / RELEASE_STEP_S) + 1):
        shifted = hold_legs(legs, at_s, point, hold_s, 1.0)  # only the timing matters here
        release = at_s + hold_s
        if (
            first_conflict(shifted, release, release + RELEASE_CHECK_S, zone, flight_started)
            is None
        ):
            break
        hold_s += RELEASE_STEP_S
    return HoldPlan(at_s=at_s, point=point, hold_s=hold_s)


# --- the scenario lifecycle ---------------------------------------------------------------------


def active_zone(session: Session, now: datetime) -> Zone | None:
    """The running scenario's zone, or None (also None once its end time has passed)."""
    row = session.scalars(
        select(LprScenario).where(LprScenario.status == LprStatus.ACTIVE.value)
    ).first()
    if row is None or as_utc(row.ends_at) <= now:
        return None
    return zone_of(row)


def active_scenario(session: Session, now: datetime) -> LprScenario | None:
    row = session.scalars(
        select(LprScenario).where(LprScenario.status == LprStatus.ACTIVE.value)
    ).first()
    return row if row is not None and as_utc(row.ends_at) > now else None


def _event_details(row: LprScenario, phase: str) -> dict[str, Any]:
    return {"phase": phase, "scenario_id": row.id, "radius_m": row.radius_m}


def _complete(session: Session, row: LprScenario, now: datetime) -> None:
    row.status = LprStatus.COMPLETED.value
    row.completed_at = now
    append_event(
        session,
        event_type=EventType.LPR_TRANSIT,
        origin=EventOrigin(row.origin),
        reason="LPR helicopter has left the operating area; the safety zone is gone",
        details=_event_details(row, "COMPLETED"),
        dedupe_key=f"{EventType.LPR_TRANSIT.value}:{row.id}:COMPLETED",
        occurred_at=now,
    )


def complete_due(session: Session, now: datetime) -> bool:
    """Complete the scenario once its end time has passed (the worker calls this each tick)."""
    row = session.scalars(
        select(LprScenario)
        .where(LprScenario.status == LprStatus.ACTIVE.value)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if row is None or as_utc(row.ends_at) > now:
        session.rollback()
        return False
    _complete(session, row, now)
    session.commit()
    return True


def start_scenario(
    session: Session, now: datetime, settings: Settings, *, origin: EventOrigin = EventOrigin.MANUAL
) -> LprScenario:
    """Start the helicopter pass; raises `LprAlreadyActiveError`, changing nothing, if one runs.

    The database allows one ACTIVE scenario (a partial unique index), so two concurrent triggers
    cannot both succeed whatever the pre-check saw. A scenario whose end time has passed but that
    the worker has not completed yet is completed here, so it never blocks a new one.
    """
    try:
        existing = session.scalars(
            select(LprScenario)
            .where(LprScenario.status == LprStatus.ACTIVE.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if existing is not None:
            if as_utc(existing.ends_at) > now:
                raise LprAlreadyActiveError
            _complete(session, existing, now)
            session.flush()
        row = LprScenario(
            id=f"LPR-{secrets.token_hex(4).upper()}",
            status=LprStatus.ACTIVE.value,
            origin=origin.value,
            started_at=now,
            ends_at=now + timedelta(seconds=route_length_m() / settings.sim_lpr_speed_ms),
            start_longitude=ROUTE_START[0],
            start_latitude=ROUTE_START[1],
            end_longitude=ROUTE_END[0],
            end_latitude=ROUTE_END[1],
            speed_ms=settings.sim_lpr_speed_ms,
            radius_m=settings.sim_lpr_zone_radius_m,
            margin_m=settings.sim_lpr_hold_margin_m,
            clear_extra_m=settings.sim_lpr_clear_extra_m,
        )
        session.add(row)
        session.flush()
        append_event(
            session,
            event_type=EventType.LPR_TRANSIT,
            origin=origin,
            reason="LPR helicopter is crossing the operating area; a safety zone moves with it",
            details=_event_details(row, "STARTED"),
            dedupe_key=f"{EventType.LPR_TRANSIT.value}:{row.id}:STARTED",
            occurred_at=now,
        )
        session.commit()
        return row
    except IntegrityError as error:  # a concurrent trigger won the unique index
        session.rollback()
        raise LprAlreadyActiveError from error
    except BaseException:
        session.rollback()
        raise
