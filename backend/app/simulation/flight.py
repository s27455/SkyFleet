"""Deterministic flight schedule and state: pure functions, no database and no clock.

A flight is an ordered list of timed legs measured in seconds from takeoff:

    OUTBOUND (loaded) -> DELIVERY (a short stop at the destination) -> RETURN (empty) [-> DIVERSION]

The state at any time (position, battery, phase, progress, next target) is a pure function of the
legs and that time, so it is reproducible in tests and survives a restart. This is accelerated
simulation time, not flight physics: a complete mission takes between a minimum and a maximum
number of seconds, scaled by route length, and positions are straight-line interpolations. The SF-1
speeds in the drone model are not changed.
"""

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from app.missions.routing import Point, distance_km
from app.simulation.models import FlightPhase


class LegKind(StrEnum):
    OUTBOUND = "OUTBOUND"
    DELIVERY = "DELIVERY"
    RETURN = "RETURN"
    DIVERSION = "DIVERSION"
    RECALL = "RECALL"  # Feature 018B: back to a Hub with the parcel still on board (loaded)
    EMERGENCY = "EMERGENCY"  # Feature 018C: the approach to the emergency landing point


_PHASE_OF_LEG = {
    LegKind.OUTBOUND: FlightPhase.OUTBOUND,
    LegKind.DELIVERY: FlightPhase.DELIVERING,
    LegKind.RETURN: FlightPhase.RETURNING,
    LegKind.DIVERSION: FlightPhase.DIVERTING,
    # A recalled drone is returning to a Hub; `MissionFlight.recalled_at` tells it apart.
    LegKind.RECALL: FlightPhase.RETURNING,
    LegKind.EMERGENCY: FlightPhase.EMERGENCY_APPROACH,
}


@dataclass(frozen=True)
class Leg:
    kind: LegKind
    start_s: float
    duration_s: float
    origin: Point
    target: Point
    distance_km: float
    loaded: bool  # carrying the parcel: uses the loaded consumption rate

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


def leg_to_dict(leg: Leg) -> dict[str, Any]:
    return {
        "kind": leg.kind.value,
        "start_s": leg.start_s,
        "duration_s": leg.duration_s,
        "origin": list(leg.origin),
        "target": list(leg.target),
        "distance_km": leg.distance_km,
        "loaded": leg.loaded,
    }


def leg_from_dict(data: dict[str, Any]) -> Leg:
    return Leg(
        kind=LegKind(data["kind"]),
        start_s=float(data["start_s"]),
        duration_s=float(data["duration_s"]),
        origin=(float(data["origin"][0]), float(data["origin"][1])),
        target=(float(data["target"][0]), float(data["target"][1])),
        distance_km=float(data["distance_km"]),
        loaded=bool(data["loaded"]),
    )


def lerp(a: Point, b: Point, fraction: float) -> Point:
    """Straight-line interpolation in longitude/latitude (fine for routes of a few km)."""
    f = min(max(fraction, 0.0), 1.0)
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def flight_duration_s(total_km: float, budget_km: float, min_s: float, max_s: float) -> float:
    """Total simulated seconds of a complete mission: `min_s` at 0 km up to `max_s` at the budget.

    `min_s + (max_s - min_s) * min(total_km / budget_km, 1)`, so routes at or beyond the mission
    distance budget take the maximum.
    """
    share = min(max(total_km / budget_km, 0.0), 1.0)
    return min_s + (max_s - min_s) * share


# Used for diversion legs only when the original route had no length at all.
FALLBACK_PACE_S_PER_KM = 60.0


def build_legs(
    origin: Point,
    destination: Point,
    return_point: Point,
    *,
    total_seconds: float,
    dwell_s: float,
) -> tuple[list[Leg], float]:
    """The planned legs for a mission, and the pace in seconds per km.

    The delivery stop takes `dwell_s` of the total; the rest is split between the outbound and the
    return leg in proportion to their distance.
    """
    out_km = distance_km(origin, destination)
    back_km = distance_km(destination, return_point)
    moving_s = max(total_seconds - dwell_s, 0.0)
    total_km = out_km + back_km
    if total_km > 0:
        out_s = moving_s * out_km / total_km
        back_s = moving_s * back_km / total_km
        pace = moving_s / total_km
    else:
        out_s = back_s = moving_s / 2
        pace = FALLBACK_PACE_S_PER_KM
    legs = [
        Leg(LegKind.OUTBOUND, 0.0, out_s, origin, destination, out_km, loaded=True),
        Leg(LegKind.DELIVERY, out_s, dwell_s, destination, destination, 0.0, loaded=True),
        Leg(LegKind.RETURN, out_s + dwell_s, back_s, destination, return_point, back_km, False),
    ]
    return legs, pace


@dataclass(frozen=True)
class FlightState:
    phase: FlightPhase
    position: Point
    battery_pct: float
    progress: float  # elapsed share of the current schedule, 0..1
    target: Point  # the end of the current leg
    eta_s: float  # seconds until the current leg ends
    elapsed_s: float
    total_s: float  # the end of the schedule


def state_at(
    legs: list[Leg],
    elapsed_s: float,
    *,
    start_battery: float,
    empty_rate: float,
    loaded_rate: float,
) -> FlightState:
    """Position, battery, phase and progress after `elapsed_s` seconds of flight."""
    t = max(elapsed_s, 0.0)
    total_s = legs[-1].end_s

    battery = start_battery
    for leg in legs:
        if leg.duration_s > 0:
            flown = min(max((t - leg.start_s) / leg.duration_s, 0.0), 1.0)
        else:
            flown = 1.0 if t >= leg.start_s else 0.0
        battery -= flown * leg.distance_km * (loaded_rate if leg.loaded else empty_rate)

    current = legs[0]
    for leg in legs:
        if leg.start_s <= t:
            current = leg
    if t >= total_s:
        position = legs[-1].target
        eta = 0.0
    else:
        fraction = (t - current.start_s) / current.duration_s if current.duration_s > 0 else 1.0
        position = lerp(current.origin, current.target, fraction)
        eta = max(current.end_s - t, 0.0)

    progress = min(t / total_s, 1.0) if total_s > 0 else 1.0
    return FlightState(
        phase=_PHASE_OF_LEG[current.kind],
        position=position,
        battery_pct=battery,
        progress=progress,
        target=current.target,
        eta_s=eta,
        elapsed_s=t,
        total_s=total_s,
    )


def landing_decision(final_leg: Leg, approach_m: float) -> tuple[float, Point]:
    """When and where the landing is decided: `approach_m` before the end of the final leg.

    The capacity recheck and the docking happen at this single instant (atomically, under the
    Hub's row lock). If the leg is shorter than the approach distance the decision is taken at the
    start of the leg.
    """
    distance_m = final_leg.distance_km * 1000
    if distance_m <= approach_m or final_leg.duration_s <= 0:
        fraction = 0.0
    else:
        fraction = 1.0 - approach_m / distance_m
    return (
        final_leg.start_s + final_leg.duration_s * fraction,
        lerp(final_leg.origin, final_leg.target, fraction),
    )


def first_time_below(
    legs: list[Leg],
    floor_pct: float,
    *,
    start_battery: float,
    empty_rate: float,
    loaded_rate: float,
    after_s: float,
) -> float | None:
    """The first offset at or after `after_s` where the battery is below `floor_pct`.

    Battery falls linearly within a leg, so the crossing is computed exactly. It depends only on
    the legs, never on when a tick happens to run.
    """

    def battery(at_s: float) -> float:
        return state_at(
            legs, at_s, start_battery=start_battery, empty_rate=empty_rate, loaded_rate=loaded_rate
        ).battery_pct

    for leg in legs:
        if leg.end_s <= after_s:
            continue
        begin = max(leg.start_s, after_s)
        before, after = battery(begin), battery(leg.end_s)
        if before < floor_pct:
            return begin
        if after < floor_pct and leg.end_s > begin:
            return begin + (before - floor_pct) / (before - after) * (leg.end_s - begin)
    return None


def stop_legs(legs: list[Leg], at_s: float, point: Point) -> list[Leg]:
    """The schedule cut short: the leg flown at `at_s` ends at `point`; later legs are dropped."""
    for index, leg in enumerate(legs):
        if at_s <= leg.end_s:
            return [*legs[:index], truncate_leg(leg, at_s, point)]
    return [*legs[:-1], truncate_leg(legs[-1], at_s, point)]


def truncate_leg(leg: Leg, at_s: float, point: Point) -> Leg:
    """The leg cut short at `point`, reached at offset `at_s` (the drone leaves the path there)."""
    return replace(
        leg,
        duration_s=max(at_s - leg.start_s, 0.0),
        target=point,
        distance_km=distance_km(leg.origin, point),
    )


def diversion_leg(
    from_point: Point, hub: Point, at_s: float, pace_s_per_km: float, *, loaded: bool = False
) -> Leg:
    """A leg from `from_point` to another Hub, flown at the original pace.

    Empty by default; a recalled flight still carries its parcel, so its diversion is `loaded`.
    """
    km = distance_km(from_point, hub)
    return Leg(LegKind.DIVERSION, at_s, km * pace_s_per_km, from_point, hub, km, loaded=loaded)


def recall_legs(
    legs: list[Leg], at_s: float, point: Point, hub: Point, pace_s_per_km: float
) -> list[Leg]:
    """The schedule after a recall at `at_s`, when the drone is at `point` with the parcel.

    The leg flown at `at_s` is cut short at `point`, every later leg (rest of the delivery and the
    empty return) is dropped, and one loaded RECALL leg to `hub` is appended at the original pace.
    """
    km = distance_km(point, hub)
    recall = Leg(LegKind.RECALL, at_s, km * pace_s_per_km, point, hub, km, loaded=True)
    return [*stop_legs(legs, at_s, point), recall]


METRES_PER_DEGREE_LATITUDE = 111_320.0


def emergency_landing_point(
    legs: list[Leg], at_s: float, position: Point, distance_m: float
) -> Point:
    """The simulated emergency landing point: `distance_m` along the current heading.

    A deterministic MVP rule (no terrain, obstacle or airspace model). The heading is that of the
    leg being flown at `at_s`; while the drone is stationary (the delivery stop) it is the heading
    of the last leg that moved. With no moving leg at all the point lies due north. The drone flies
    the full distance even past the leg's end: a failure does not follow the plan.
    """
    heading: tuple[float, float] | None = None
    for leg in legs:
        if leg.start_s > at_s and heading is not None:
            break
        if leg.distance_km > 0:
            heading = (leg.target[0] - leg.origin[0], leg.target[1] - leg.origin[1])
    latitude_scale = math.cos(math.radians(position[1]))
    # Heading in metres (east, north); longitude degrees shrink with the cosine of the latitude.
    east = heading[0] * latitude_scale if heading else 0.0
    north = heading[1] if heading else 1.0
    norm = math.hypot(east, north)
    if norm == 0:
        east, north, norm = 0.0, 1.0, 1.0
    east, north = east / norm, north / norm
    return (
        position[0] + east * distance_m / (METRES_PER_DEGREE_LATITUDE * latitude_scale),
        position[1] + north * distance_m / METRES_PER_DEGREE_LATITUDE,
    )


def emergency_legs(
    legs: list[Leg],
    at_s: float,
    position: Point,
    landing: Point,
    pace_s_per_km: float,
    *,
    loaded: bool,
) -> list[Leg]:
    """The schedule after a failure at `at_s`: the leg flown is cut at `position` and one EMERGENCY
    leg to the landing point follows, at the original pace. `loaded` is true while the parcel is
    still on board (it was not delivered).
    """
    km = distance_km(position, landing)
    approach = Leg(
        LegKind.EMERGENCY, at_s, km * pace_s_per_km, position, landing, km, loaded=loaded
    )
    return [*stop_legs(legs, at_s, position), approach]
