"""Feature 017C: nearest feasible return Hub, with explicit cases (pure functions)."""

from collections import Counter

import pytest

from app.hubs.models import Hub
from app.missions.capacity import choose_return_hub
from app.missions.routing import hubs_by_distance


def _hub(hub_id: str, lon: float, lat: float, capacity: int = 50) -> Hub:
    return Hub(
        id=hub_id, name=hub_id, address="x", longitude=lon, latitude=lat, drone_capacity=capacity
    )


ORIGIN = _hub("hub-origin", 18.60, 54.38)
OTHER = _hub("hub-other", 18.64, 54.35)
FAR = _hub("hub-far", 18.53, 54.50)
HUBS = [ORIGIN, OTHER, FAR]
NOBODY = Counter[str]()


def _choose(destination: tuple[float, float], reachable_up_to_km: float, **kwargs):  # type: ignore[no-untyped-def]
    return choose_return_hub(
        hubs_by_distance(destination, HUBS),
        kwargs.get("occupancy", NOBODY),
        docked_at=ORIGIN,
        is_reachable=lambda km: km <= reachable_up_to_km,
    )


def test_the_origin_hub_is_chosen_when_it_is_nearest_to_the_destination() -> None:
    choice = _choose((18.598, 54.378), reachable_up_to_km=50)

    assert choice.hub is not None and choice.hub.id == "hub-origin"
    assert choice.skipped == []


def test_another_hub_is_chosen_when_the_destination_is_nearer_to_it() -> None:
    choice = _choose((18.642, 54.352), reachable_up_to_km=50)  # next to the other Hub

    assert choice.hub is not None and choice.hub.id == "hub-other"
    assert choice.skipped == []  # nothing nearer was passed over


def test_equal_distances_go_to_the_lower_hub_id() -> None:
    a, b = _hub("hub-a", 18.60, 54.40), _hub("hub-b", 18.62, 54.40)
    destination = (18.61, 54.40)  # exactly halfway on one latitude: the same distance to both

    ranked = hubs_by_distance(destination, [b, a])

    assert ranked[0][1] == pytest.approx(ranked[1][1], rel=1e-9)
    assert [hub.id for hub, _ in ranked] == ["hub-a", "hub-b"]


def test_a_nearest_hub_out_of_range_is_skipped_for_the_next_feasible_one() -> None:
    ranked = hubs_by_distance((18.598, 54.378), HUBS)
    nearest_km, second_km = ranked[0][1], ranked[1][1]
    limit = (nearest_km + second_km) / 2  # the nearest is reachable, so shrink below it instead
    choice = choose_return_hub(
        ranked,
        NOBODY,
        docked_at=None,
        is_reachable=lambda km: km >= limit,  # nearest infeasible, the others feasible
    )

    assert choice.hub is not None and choice.hub.id == ranked[1][0].id
    assert choice.skipped == [(ranked[0][0], "OUT_OF_RANGE")]


def test_when_no_hub_is_feasible_there_is_no_choice_and_every_hub_is_reported() -> None:
    choice = _choose((18.598, 54.378), reachable_up_to_km=0.0)

    assert choice.hub is None
    assert {hub.id for hub, _ in choice.skipped} == {"hub-origin", "hub-other", "hub-far"}
    assert {why for _, why in choice.skipped} == {"OUT_OF_RANGE"}


def test_a_single_eligible_hub_is_chosen_even_if_it_is_far() -> None:
    ranked = hubs_by_distance((18.598, 54.378), HUBS)
    far_id = ranked[-1][0].id
    choice = choose_return_hub(
        ranked, NOBODY, docked_at=None, is_reachable=lambda km: km == ranked[-1][1]
    )

    assert choice.hub is not None and choice.hub.id == far_id
    assert [why for _, why in choice.skipped] == ["OUT_OF_RANGE", "OUT_OF_RANGE"]


def test_a_full_hub_is_skipped_but_never_reported_as_out_of_range() -> None:
    full = Counter({"hub-origin": 50})
    ranked = hubs_by_distance((18.598, 54.378), HUBS)  # the origin Hub is nearest

    choice = choose_return_hub(ranked, full, docked_at=None, is_reachable=lambda _km: True)

    assert choice.hub is not None and choice.hub.id == "hub-other"
    assert choice.skipped == [(ORIGIN, "HUB_FULL")]
