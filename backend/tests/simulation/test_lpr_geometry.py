"""Hold legs and the LPR conflict geometry (Feature 018E): pure functions, no database."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.missions.routing import distance_km
from app.simulation import lpr
from app.simulation.flight import (
    Leg,
    LegKind,
    emergency_landing_point,
    hold_legs,
    lerp,
    position_at,
    state_at,
    truncate_leg,
)
from app.simulation.models import FlightPhase

T0 = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
A, B, HUB = (18.60, 54.38), (18.62, 54.38), (18.60, 54.39)
PACE = 20.0  # seconds per km
EMPTY, LOADED = 5.0, 6.0  # % of battery per km


def leg(
    kind: LegKind,
    start: float,
    dur: float,
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    loaded: bool = True,
) -> Leg:
    return Leg(kind, start, dur, a, b, distance_km(a, b), loaded=loaded)


def plain() -> list[Leg]:
    return [
        leg(LegKind.OUTBOUND, 0, 10, A, B),
        leg(LegKind.DELIVERY, 10, 3, B, B),
        leg(LegKind.RETURN, 13, 10, B, A, loaded=False),
    ]


def battery(legs: list[Leg], at_s: float) -> float:
    return state_at(
        legs, at_s, start_battery=100.0, empty_rate=EMPTY, loaded_rate=LOADED
    ).battery_pct


# --- hold_legs ---------------------------------------------------------------------------------


def test_a_hold_splits_the_leg_and_shifts_everything_after_it() -> None:
    legs = plain()
    point = position_at(legs, 4)

    new = hold_legs(legs, 4, point, 6.0, PACE)

    assert [item.kind for item in new] == [
        LegKind.OUTBOUND,
        LegKind.HOLD,
        LegKind.OUTBOUND,
        LegKind.DELIVERY,
        LegKind.RETURN,
    ]
    first, hold, rest, stop, back = new
    assert (first.start_s, first.end_s, first.target) == (0, 4, point)
    assert (hold.start_s, hold.end_s, hold.origin, hold.target) == (4, 10, point, point)
    assert (rest.start_s, rest.end_s, rest.origin, rest.target) == (10, 16, point, B)
    assert (stop.start_s, stop.end_s) == (16, 19)  # the handover is six seconds later
    assert (back.start_s, back.end_s) == (19, 29)
    assert new[-1].end_s == legs[-1].end_s + 6.0


def test_the_hold_does_not_move_the_drone() -> None:
    legs = plain()
    point = position_at(legs, 4)
    new = hold_legs(legs, 4, point, 6.0, PACE)

    for t in (4.0, 6.0, 9.999):
        assert position_at(new, t) == pytest.approx(point)  # standing still for the whole hold
    assert position_at(new, 3.9) == pytest.approx(position_at(legs, 3.9))  # before: unchanged
    assert position_at(new, 16) == pytest.approx(position_at(legs, 10))  # after: the same route
    assert position_at(new, 29.0) == pytest.approx(A)  # and the same landing point


def test_a_hold_between_two_legs_is_inserted_without_splitting() -> None:
    new = hold_legs(plain(), 10, B, 5.0, PACE)

    assert [item.kind for item in new] == [
        LegKind.OUTBOUND,
        LegKind.HOLD,
        LegKind.DELIVERY,
        LegKind.RETURN,
    ]
    assert (new[2].start_s, new[3].start_s) == (15, 18)


def test_a_hold_in_the_delivery_stop_splits_the_stop() -> None:
    new = hold_legs(plain(), 11.0, B, 4.0, PACE)

    assert [item.kind for item in new] == [
        LegKind.OUTBOUND,
        LegKind.DELIVERY,
        LegKind.HOLD,
        LegKind.DELIVERY,
        LegKind.RETURN,
    ]
    assert new[1].duration_s == pytest.approx(1.0) and new[3].duration_s == pytest.approx(2.0)
    assert new[3].end_s == 17  # the parcel is handed over at the end of the last part


def test_a_hold_after_the_end_of_the_schedule_is_refused() -> None:
    with pytest.raises(ValueError):
        hold_legs(plain(), 23.0, A, 5.0, PACE)


def test_the_hold_costs_battery_like_cruising_at_the_original_pace() -> None:
    legs = plain()
    new = hold_legs(legs, 4, position_at(legs, 4), 6.0, PACE)

    hold = new[1]
    assert hold.distance_km == pytest.approx(6.0 / PACE)  # the distance it would have flown
    assert battery(new, 4) - battery(new, 10) == pytest.approx(hold.distance_km * LOADED)
    # In total the drone is exactly that much emptier when it lands.
    assert battery(legs, 23) - battery(new, 29) == pytest.approx(hold.distance_km * LOADED)


def test_an_empty_drone_holds_at_the_empty_rate() -> None:
    legs = plain()
    new = hold_legs(legs, 15, position_at(legs, 15), 4.0, PACE)

    hold = next(item for item in new if item.kind == LegKind.HOLD)
    assert hold.loaded is False
    assert battery(new, 15) - battery(new, 19) == pytest.approx(hold.distance_km * EMPTY)


def test_a_hold_keeps_the_phase_of_the_flight_it_interrupts() -> None:
    legs = plain()
    new = hold_legs(legs, 4, position_at(legs, 4), 6.0, PACE)

    assert state_at(new, 6, start_battery=100, empty_rate=EMPTY, loaded_rate=LOADED).phase == (
        FlightPhase.OUTBOUND
    )
    late = hold_legs(legs, 15, position_at(legs, 15), 4.0, PACE)
    assert state_at(late, 16, start_battery=100, empty_rate=EMPTY, loaded_rate=LOADED).phase == (
        FlightPhase.RETURNING
    )


def test_cutting_a_hold_short_keeps_its_cost_in_proportion() -> None:
    hold = Leg(LegKind.HOLD, 4, 8.0, A, A, 0.4, loaded=True)

    cut = truncate_leg(hold, 8, A)  # a recall or a failure ends the hold halfway

    assert cut.duration_s == 4.0 and cut.distance_km == pytest.approx(0.2)


def test_a_stationary_hold_has_no_heading_for_an_emergency_landing() -> None:
    legs = plain()
    new = hold_legs(legs, 4, position_at(legs, 4), 6.0, PACE)

    point = emergency_landing_point(new, 6.0, position_at(new, 6.0), 250.0)

    # Still along the outbound heading (due east), not the due-north fallback.
    assert point[1] == pytest.approx(A[1], abs=1e-5)
    assert point[0] > position_at(new, 6.0)[0]


# --- conflict prediction -----------------------------------------------------------------------


def zone() -> lpr.Zone:
    length = lpr.route_length_m()
    return lpr.Zone(
        scenario_id="LPR-TEST",
        origin="MANUAL",
        started_at=T0,
        ends_at=T0 + timedelta(seconds=length / 80.0),
        start=lpr.ROUTE_START,
        end=lpr.ROUTE_END,
        speed_ms=80.0,
        radius_m=500.0,
        margin_m=250.0,
        clear_extra_m=100.0,
    )


def crossing_flight() -> tuple[list[Leg], datetime]:
    """A drone flying north across the middle of the route at about 130 m/s.

    It reaches the route (the middle of the helicopter's pass) 16.5 s into its flight, exactly when
    the helicopter does.
    """
    middle = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    south, north = (middle[0], middle[1] - 0.02), (middle[0], middle[1] + 0.02)
    legs = [leg(LegKind.OUTBOUND, 0, 33, south, north)]
    helicopter_at_middle = zone().duration_s / 2
    return legs, T0 + timedelta(seconds=helicopter_at_middle - 16.5)


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return distance_km(a, b) * 1000


@pytest.mark.parametrize("tick", [1.0, 2.5, 5.0])
def test_a_fast_drone_cannot_cross_the_zone_between_two_ticks(tick: float) -> None:
    legs, started = crossing_flight()
    z = zone()
    plan = None
    elapsed = 0.0
    while elapsed < 33 and plan is None:
        plan = lpr.plan_hold(legs, elapsed, started, z, 2 * tick)
        if plan is None:
            # Every position the drone has actually reached so far is outside the drawn zone.
            now = started + timedelta(seconds=elapsed)
            assert distance_m(position_at(legs, elapsed), lpr.helicopter_position(z, now)) >= 500
            elapsed += tick

    assert plan is not None  # the crossing is always noticed
    assert plan.at_s >= elapsed
    # It stops outside the corridor, so the zone passes beside it and never over it.
    for step in range(int(plan.hold_s * 10) + 1):
        moment = started + timedelta(seconds=plan.at_s + step / 10)
        assert distance_m(plan.point, lpr.helicopter_position(z, moment)) >= z.radius_m
    lateral = distance_m(plan.point, (plan.point[0], lpr.ROUTE_START[1]))
    assert lateral >= z.hold_threshold_m - 1  # at the corridor's edge, not at the helicopter


def test_the_prediction_does_not_depend_on_when_the_tick_runs() -> None:
    legs, started = crossing_flight()
    z = zone()

    early = lpr.first_conflict(legs, 0.0, 30.0, z, started)
    late = lpr.first_conflict(legs, 5.0, 30.0, z, started)
    exact = lpr.first_conflict(legs, early or 0.0, (early or 0.0) + 0.5, z, started)

    assert early is not None
    assert late == pytest.approx(early)
    assert exact == pytest.approx(early)


def test_a_drone_far_from_the_route_is_never_a_conflict() -> None:
    far = [leg(LegKind.OUTBOUND, 0, 30, (18.60, 54.50), (18.62, 54.50))]  # 12 km north

    assert lpr.plan_hold(far, 0.0, T0 + timedelta(seconds=60), zone(), 60.0) is None


def test_a_conflict_beyond_the_look_ahead_is_not_acted_on_yet() -> None:
    legs, started = crossing_flight()

    assert lpr.plan_hold(legs, 0.0, started, zone(), 2.0) is None
    assert lpr.plan_hold(legs, 0.0, started, zone(), 20.0) is not None


def test_a_helicopter_that_has_already_passed_is_not_a_conflict() -> None:
    legs, started = crossing_flight()
    after = started + timedelta(seconds=zone().duration_s)  # the pass is over before takeoff

    assert lpr.plan_hold(legs, 0.0, after, zone(), 60.0) is None


def test_time_already_spent_holding_is_not_a_new_conflict() -> None:
    legs, started = crossing_flight()
    z = zone()
    plan = lpr.plan_hold(legs, 0.0, started, z, 30.0)
    assert plan is not None
    held = hold_legs(legs, plan.at_s, plan.point, plan.hold_s, PACE)

    # Standing still at the hold distance is not a conflict, and neither is flying on afterwards.
    assert lpr.plan_hold(held, plan.at_s, started, z, plan.hold_s - 0.1) is None
    resume = plan.at_s + plan.hold_s
    assert lpr.plan_hold(held, resume, started, z, 5.0) is None


def test_a_drone_standing_in_the_helicopters_way_is_held_at_once() -> None:
    middle = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    sitting = [leg(LegKind.OUTBOUND, 0, 60, middle, (middle[0] + 0.0001, middle[1]))]
    started = T0 + timedelta(seconds=zone().duration_s / 2 - 5)  # helicopter 400 m away

    plan = lpr.plan_hold(sitting, 0.0, started, zone(), 2.0)

    assert plan is not None and plan.at_s == 0.0


# --- hold duration -----------------------------------------------------------------------------


def test_the_hold_lasts_until_the_helicopter_is_clear_of_the_drone() -> None:
    legs, started = crossing_flight()
    z = zone()
    plan = lpr.plan_hold(legs, 0.0, started, z, 30.0)
    assert plan is not None

    end = started + timedelta(seconds=plan.at_s + plan.hold_s)
    gap = distance_m(plan.point, lpr.helicopter_position(z, end))

    assert gap >= z.clear_threshold_m - 2.0  # released only once the helicopter is clear
    assert 5 < plan.hold_s < 40  # an observable wait, not a stop for the whole scenario
    # And it stays clear: the helicopter only moves further away.
    later = started + timedelta(seconds=plan.at_s + plan.hold_s + 3)
    assert distance_m(plan.point, lpr.helicopter_position(z, later)) > z.clear_threshold_m


def test_a_hold_never_outlasts_the_scenario() -> None:
    z = zone()
    # A drone waiting near the end of the route: the zone disappears when the pass ends.
    near_end = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.999)
    started = T0 + timedelta(seconds=z.duration_s - 3)

    hold = lpr.hold_duration_s(near_end, 0.0, z, started)

    assert hold == pytest.approx(3.0, abs=0.1)  # not until the helicopter is "clear" of its end


def test_the_hold_is_at_least_a_second() -> None:
    z = zone()
    point = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    started = T0 + timedelta(seconds=z.duration_s / 2 + 1000 / 80)  # helicopter already past

    assert lpr.hold_duration_s(point, 0.0, z, started) >= lpr.MIN_HOLD_S


def test_the_route_is_a_fixed_corridor_with_a_plausible_length() -> None:
    assert 10_000 < lpr.route_length_m() < 20_000
    assert math.isclose(zone().duration_s, lpr.route_length_m() / 80.0, abs_tol=1e-3)


def test_a_hold_is_taken_before_the_corridor_not_at_the_moment_of_meeting() -> None:
    legs, started = crossing_flight()
    z = zone()
    meet = lpr.first_conflict(legs, 0.0, 30.0, z, started)
    plan = lpr.plan_hold(legs, 0.0, started, z, 30.0)

    assert meet is not None and plan is not None
    assert plan.at_s < meet  # it stops earlier, before it is in the helicopter's way
    assert lpr.standing_clearance_m(plan.point, plan.at_s, z, started) >= z.hold_threshold_m - 1


def test_standing_on_the_route_ahead_of_the_helicopter_is_not_clear_but_beside_it_is() -> None:
    z = zone()
    on_route = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    beside = (on_route[0], on_route[1] + 0.02)  # about 2.2 km north of the route

    assert lpr.standing_clearance_m(on_route, 0.0, z, T0) < 1.0  # the helicopter flies over it
    assert lpr.standing_clearance_m(beside, 0.0, z, T0) > 2000


def test_a_helicopter_that_has_passed_leaves_the_place_clear() -> None:
    z = zone()
    behind = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.1)
    late = z.duration_s * 0.5  # it is well beyond that point by now

    assert lpr.standing_clearance_m(behind, late, z, T0) > 1000


def test_a_hold_ahead_of_the_drone_is_not_inserted_again_on_later_ticks() -> None:
    legs, started = crossing_flight()
    z = zone()
    plan = lpr.plan_hold(legs, 0.0, started, z, 30.0)
    assert plan is not None and plan.at_s > 1.0
    held = hold_legs(legs, plan.at_s, plan.point, plan.hold_s, PACE)

    for elapsed in (0.5, 1.0, plan.at_s - 0.3, plan.at_s, plan.at_s + 1.0):
        assert lpr.plan_hold(held, elapsed, started, z, 4.0) is None


def test_a_drone_inside_the_corridor_that_can_leave_it_in_time_stops_outside_it() -> None:
    z = zone()
    middle = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    inside = (middle[0], middle[1] + 0.0027)  # 300 m north of the route
    out, back = (middle[0], middle[1] + 0.013), (middle[0], middle[1] + 0.0003)
    legs = [  # out of the corridor at 100 m/s, then back towards the route
        leg(LegKind.OUTBOUND, 0, 11, inside, out),
        leg(LegKind.OUTBOUND, 11, 12, out, back),
    ]
    started = T0 + timedelta(
        seconds=z.duration_s / 2 - 19
    )  # the helicopter is at the middle at 19 s

    plan = lpr.plan_hold(legs, 0.0, started, z, 30.0)

    assert plan is not None
    assert 3.0 < plan.at_s < 6.0  # at the corridor's edge on the way out, not at once
    assert lpr.standing_clearance_m(plan.point, plan.at_s, z, started) >= z.hold_threshold_m - 1


def test_a_drone_that_cannot_leave_the_corridor_in_time_stands_where_it_is() -> None:
    z = zone()
    middle = lerp(lpr.ROUTE_START, lpr.ROUTE_END, 0.5)
    inside = (middle[0] - 0.003, middle[1] + 0.0027)
    legs = [leg(LegKind.OUTBOUND, 0, 60, inside, (inside[0] + 0.0002, inside[1] + 0.0005))]
    started = T0 + timedelta(seconds=z.duration_s / 2 - 6)  # the helicopter is almost there

    plan = lpr.plan_hold(legs, 0.0, started, z, 10.0)

    assert plan is not None and plan.at_s == 0.0  # nothing better exists: it holds right now
