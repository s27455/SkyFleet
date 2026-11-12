"""The deterministic flight schedule and state: pure functions, no database, no clock."""

import pytest

from app.missions.routing import distance_km
from app.simulation.flight import (
    FlightState,
    Leg,
    LegKind,
    build_legs,
    diversion_leg,
    first_time_below,
    flight_duration_s,
    landing_decision,
    leg_from_dict,
    leg_to_dict,
    state_at,
    stop_legs,
    truncate_leg,
)
from app.simulation.models import FlightPhase

ORIGIN = (0.0, 0.0)
DESTINATION = (0.01, 0.0)  # about 1.11 km east of the origin
RETURN_HUB = (0.002, 0.0)  # about 0.22 km east of the origin, so 0.89 km back from the destination
EMPTY, LOADED = 5.0, 7.5  # percent per km (a 3 kg parcel on the SF-1 model)


def legs_for(total_s: float = 40.0, dwell: float = 3.0) -> tuple[list[Leg], float]:
    return build_legs(ORIGIN, DESTINATION, RETURN_HUB, total_seconds=total_s, dwell_s=dwell)


def state(legs: list[Leg], t: float, start: float = 100.0) -> FlightState:
    return state_at(legs, t, start_battery=start, empty_rate=EMPTY, loaded_rate=LOADED)


# --- duration mapping -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total_km", "expected"),
    [(0, 30.0), (3.5, 45.0), (7, 60.0), (10.5, 75.0), (14, 90.0), (20, 90.0), (-1, 30.0)],
)
def test_duration_maps_route_length_linearly_to_30_to_90_seconds(
    total_km: float, expected: float
) -> None:
    assert flight_duration_s(total_km, 14.0, 30.0, 90.0) == pytest.approx(expected)


def test_a_seeded_sized_route_takes_about_36_seconds() -> None:
    assert flight_duration_s(1.372, 14.0, 30.0, 90.0) == pytest.approx(35.88, abs=0.01)


# --- schedule -------------------------------------------------------------------------------------


def test_the_legs_fill_the_whole_duration_with_a_fixed_delivery_stop() -> None:
    legs, pace = legs_for(40.0)

    assert [leg.kind for leg in legs] == [LegKind.OUTBOUND, LegKind.DELIVERY, LegKind.RETURN]
    assert legs[1].duration_s == 3.0
    assert legs[-1].end_s == pytest.approx(40.0)
    for before, after in zip(legs, legs[1:], strict=False):
        assert after.start_s == pytest.approx(before.end_s)
    assert pace == pytest.approx(37.0 / (legs[0].distance_km + legs[2].distance_km))


def test_the_moving_time_is_split_in_proportion_to_leg_distance() -> None:
    legs, pace = legs_for(40.0)

    assert legs[0].duration_s == pytest.approx(legs[0].distance_km * pace)
    assert legs[2].duration_s == pytest.approx(legs[2].distance_km * pace)
    assert legs[0].loaded and not legs[2].loaded


def test_legs_survive_a_round_trip_through_storage() -> None:
    legs, _ = legs_for()

    assert [leg_from_dict(leg_to_dict(leg)) for leg in legs] == legs


# --- state over time ------------------------------------------------------------------------------


def test_at_takeoff_the_drone_is_at_the_origin_with_its_full_starting_battery() -> None:
    legs, _ = legs_for()

    s = state(legs, 0.0)

    assert s.phase == FlightPhase.OUTBOUND
    assert s.position == ORIGIN
    assert s.battery_pct == 100.0
    assert s.progress == 0.0
    assert s.target == DESTINATION


def test_halfway_through_the_outbound_leg_it_is_halfway_there() -> None:
    legs, _ = legs_for()

    s = state(legs, legs[0].duration_s / 2)

    assert s.position == pytest.approx((0.005, 0.0))
    assert s.battery_pct == pytest.approx(100 - 0.5 * legs[0].distance_km * LOADED)
    assert s.eta_s == pytest.approx(legs[0].duration_s / 2)


def test_during_the_delivery_stop_the_drone_waits_at_the_destination() -> None:
    legs, _ = legs_for()
    a = state(legs, legs[0].end_s + 0.5)
    b = state(legs, legs[0].end_s + 2.5)

    assert a.phase == b.phase == FlightPhase.DELIVERING
    assert a.position == b.position == DESTINATION
    assert a.battery_pct == pytest.approx(b.battery_pct)  # no distance, no energy


def test_the_return_leg_is_flown_empty_and_ends_at_the_hub() -> None:
    legs, _ = legs_for()
    out_energy = legs[0].distance_km * LOADED

    middle = state(legs, legs[2].start_s + legs[2].duration_s / 2)
    end = state(legs, legs[2].end_s)

    assert middle.phase == FlightPhase.RETURNING
    assert middle.position == pytest.approx(((0.01 + 0.002) / 2, 0.0))
    assert end.position == RETURN_HUB
    assert end.battery_pct == pytest.approx(100 - out_energy - legs[2].distance_km * EMPTY)
    assert end.progress == 1.0


def test_a_heavier_parcel_costs_more_on_the_outbound_leg_only() -> None:
    legs, _ = legs_for()
    light = state_at(legs, legs[-1].end_s, start_battery=100, empty_rate=EMPTY, loaded_rate=5.25)
    heavy = state_at(legs, legs[-1].end_s, start_battery=100, empty_rate=EMPTY, loaded_rate=LOADED)

    assert light.battery_pct - heavy.battery_pct == pytest.approx(
        legs[0].distance_km * (LOADED - 5.25)
    )


def test_before_takeoff_and_long_after_landing_the_state_is_clamped() -> None:
    legs, _ = legs_for()

    assert state(legs, -5.0).position == ORIGIN
    assert state(legs, 10_000.0).position == RETURN_HUB
    assert state(legs, 10_000.0).eta_s == 0.0


# --- landing decision, truncation and diversion ---------------------------------------------------


def test_the_landing_is_decided_60_m_before_the_hub() -> None:
    legs, _ = legs_for()
    final = legs[-1]

    when, where = landing_decision(final, 60.0)

    assert final.start_s < when < final.end_s
    assert distance_km(where, final.target) * 1000 == pytest.approx(60.0, abs=0.5)


def test_a_leg_shorter_than_the_approach_is_decided_at_its_start() -> None:
    legs, _ = build_legs(ORIGIN, DESTINATION, (0.0101, 0.0), total_seconds=40, dwell_s=3)

    when, where = landing_decision(legs[-1], 60.0)  # the return leg is about 11 m long

    assert when == legs[-1].start_s
    assert where == legs[-1].origin


def test_a_diversion_continues_from_the_decision_point_at_the_original_pace() -> None:
    legs, pace = legs_for()
    when, where = landing_decision(legs[-1], 60.0)
    other_hub = (0.02, 0.0)

    truncated = truncate_leg(legs[-1], when, where)
    divert = diversion_leg(where, other_hub, when, pace)
    new_legs = [*legs[:-1], truncated, divert]

    assert truncated.end_s == pytest.approx(when)
    assert divert.start_s == pytest.approx(when)
    assert divert.duration_s == pytest.approx(divert.distance_km * pace)
    assert divert.kind == LegKind.DIVERSION and not divert.loaded
    just_before = state(new_legs, when - 1e-6)
    just_after = state(new_legs, when + 1e-6)
    assert just_before.position == pytest.approx(just_after.position, abs=1e-6)
    assert state(new_legs, divert.end_s).position == other_hub
    assert state(new_legs, divert.end_s).phase == FlightPhase.DIVERTING
    # The diversion costs extra energy at the empty rate.
    assert state(new_legs, divert.end_s).battery_pct == pytest.approx(
        state(legs, when).battery_pct - divert.distance_km * EMPTY
    )


# --- the exact battery crossing and stopping a schedule -----------------------------------------


def crossing(legs: list[Leg], floor: float, after_s: float = 0.0) -> float | None:
    return first_time_below(
        legs,
        floor,
        start_battery=100.0,
        empty_rate=EMPTY,
        loaded_rate=LOADED,
        after_s=after_s,
    )


def test_the_battery_crossing_is_computed_exactly_inside_a_leg() -> None:
    legs, _ = legs_for()
    t = crossing(legs, 95.0)

    assert t is not None
    assert state(legs, t).battery_pct == pytest.approx(95.0)
    assert state(legs, t - 0.01).battery_pct > 95.0
    assert state(legs, t + 0.01).battery_pct < 95.0


def test_there_is_no_crossing_when_the_battery_never_gets_that_low() -> None:
    legs, _ = legs_for()

    assert crossing(legs, 1.0) is None


def test_a_crossing_is_only_searched_from_the_given_offset() -> None:
    legs, _ = legs_for()
    first = crossing(legs, 95.0)
    assert first is not None

    later = crossing(legs, 95.0, after_s=first + 5.0)

    assert later == first + 5.0  # already below the floor at the search start


def test_stopping_a_schedule_keeps_the_flown_legs_and_drops_the_rest() -> None:
    legs, pace = legs_for()
    when, where = landing_decision(legs[-1], 60.0)
    diverted = [
        *legs[:-1],
        truncate_leg(legs[-1], when, where),
        diversion_leg(where, (0.02, 0.0), when, pace),
    ]

    stopped = stop_legs(diverted, when + 1.0, (0.011, 0.0))

    assert [leg.kind for leg in stopped] == [
        LegKind.OUTBOUND,
        LegKind.DELIVERY,
        LegKind.RETURN,
        LegKind.DIVERSION,
    ]
    assert stopped[-1].target == (0.011, 0.0)
    assert stopped[-1].end_s == pytest.approx(when + 1.0)
    earlier = stop_legs(diverted, legs[0].duration_s / 2, (0.005, 0.0))
    assert [leg.kind for leg in earlier] == [LegKind.OUTBOUND]
