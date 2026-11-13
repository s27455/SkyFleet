"""The delivery stop is found by kind, not by position (Feature 018E refactor)."""

import pytest

from app.missions.routing import distance_km
from app.simulation.flight import (
    Leg,
    LegKind,
    delivery_leg,
    delivery_leg_index,
    handover_failed_legs,
)

A, B, HUB = (18.60, 54.38), (18.62, 54.38), (18.60, 54.39)


def leg(
    kind: LegKind, start: float, dur: float, a: tuple[float, float], b: tuple[float, float]
) -> Leg:
    return Leg(kind, start, dur, a, b, distance_km(a, b), loaded=kind != LegKind.RETURN)


PLAIN = [
    leg(LegKind.OUTBOUND, 0, 10, A, B),
    leg(LegKind.DELIVERY, 10, 3, B, B),
    leg(LegKind.RETURN, 13, 10, B, A),
]


def test_the_stop_of_a_plain_schedule_is_its_second_leg() -> None:
    assert delivery_leg_index(PLAIN) == 1
    assert delivery_leg(PLAIN) is PLAIN[1]


def test_a_leg_before_the_stop_does_not_move_the_stop_out_of_reach() -> None:
    # The outbound leg was split by an extra stationary leg: the stop is now the fourth leg.
    midway = (18.61, 54.38)
    legs = [
        leg(LegKind.OUTBOUND, 0, 5, A, midway),
        Leg(LegKind.OUTBOUND, 5, 4, midway, midway, 0.0, loaded=True),  # stands in for a pause
        leg(LegKind.OUTBOUND, 9, 5, midway, B),
        leg(LegKind.DELIVERY, 14, 3, B, B),
        leg(LegKind.RETURN, 17, 10, B, A),
    ]

    stop = delivery_leg(legs)

    assert delivery_leg_index(legs) == 3
    assert stop is not None and stop.end_s == 17


def test_a_stop_split_in_two_ends_at_its_last_part() -> None:
    legs = [
        leg(LegKind.OUTBOUND, 0, 10, A, B),
        leg(LegKind.DELIVERY, 10, 1, B, B),
        Leg(LegKind.DELIVERY, 11, 6, B, B, 0.0, loaded=True),  # a pause inside the stop
        leg(LegKind.DELIVERY, 17, 2, B, B),
        leg(LegKind.RETURN, 19, 10, B, A),
    ]

    stop = delivery_leg(legs)

    assert stop is not None and stop.end_s == 19  # the handover waits for the whole stop
    assert delivery_leg_index(legs) == 3


def test_a_schedule_cut_short_before_the_stop_has_none() -> None:
    recalled = [leg(LegKind.OUTBOUND, 0, 4, A, (18.61, 54.38)), leg(LegKind.RECALL, 4, 5, B, A)]

    assert delivery_leg(recalled) is None
    assert delivery_leg_index(recalled) is None


def test_a_failed_handover_keeps_everything_up_to_the_last_stop_and_returns_loaded() -> None:
    legs = [
        leg(LegKind.OUTBOUND, 0, 10, A, B),
        leg(LegKind.DELIVERY, 10, 1, B, B),
        Leg(LegKind.DELIVERY, 11, 6, B, B, 0.0, loaded=True),
        leg(LegKind.DELIVERY, 17, 2, B, B),
        leg(LegKind.RETURN, 19, 10, B, A),
    ]

    new = handover_failed_legs(legs, HUB, 20.0)

    assert [item.kind for item in new] == [
        LegKind.OUTBOUND,
        *[LegKind.DELIVERY] * 3,
        LegKind.RETURN,
    ]
    back = new[-1]
    assert back.loaded is True and back.start_s == 19 and back.origin == B and back.target == HUB


def test_a_failed_handover_without_a_stop_is_refused() -> None:
    with pytest.raises(ValueError):
        handover_failed_legs([leg(LegKind.OUTBOUND, 0, 4, A, B)], HUB, 20.0)
