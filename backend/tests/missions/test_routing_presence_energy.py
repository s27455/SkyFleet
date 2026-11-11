"""Pure-function tests: routing, physical presence and occupancy, and the energy model."""

import math

import pytest

from app.drones.models import Drone, DroneStatus
from app.drones.seed import build_sf1_model
from app.hubs.models import Hub
from app.missions.energy import EnergyEstimate, estimate_energy, has_enough_battery
from app.missions.presence import docked_hub, hub_occupancy
from app.missions.routing import distance_km, hubs_by_distance

EQUATOR_KM_PER_DEGREE = 2 * math.pi * 6371.0 / 360


def hub(hub_id: str, lng: float = 0.0, lat: float = 0.0, capacity: int = 50) -> Hub:
    return Hub(
        id=hub_id,
        name=hub_id,
        address="a",
        longitude=lng,
        latitude=lat,
        drone_capacity=capacity,
    )


def drone(drone_id: str, lng: float, lat: float, status: DroneStatus = DroneStatus.IDLE) -> Drone:
    return Drone(
        id=drone_id,
        model_id="SF-1",
        hub_id="hub-a",
        status=status.value,
        battery_pct=100,
        longitude=lng,
        latitude=lat,
    )


def metres_east(meters: float) -> float:
    """Longitude offset (degrees, on the equator) for a distance in metres."""
    return meters / 1000 / EQUATOR_KM_PER_DEGREE


# --- routing -------------------------------------------------------------------------------------


def test_distance_is_zero_for_the_same_point_and_symmetric() -> None:
    a, b = (18.6, 54.4), (18.7, 54.5)

    assert distance_km(a, a) == 0
    assert distance_km(a, b) == pytest.approx(distance_km(b, a))


def test_one_degree_of_latitude_is_about_111_km() -> None:
    assert distance_km((0, 0), (0, 1)) == pytest.approx(EQUATOR_KM_PER_DEGREE, rel=1e-9)
    assert EQUATOR_KM_PER_DEGREE == pytest.approx(111.19, abs=0.01)


def test_hubs_are_sorted_nearest_first_with_ties_to_the_lower_id() -> None:
    hubs = [hub("hub-c", 0.03), hub("hub-b", 0.01), hub("hub-a", -0.01)]  # b and a tie at 0

    ordered = hubs_by_distance((0.0, 0.0), hubs)

    assert [h.id for h, _ in ordered] == ["hub-a", "hub-b", "hub-c"]
    assert ordered[0][1] == pytest.approx(ordered[1][1])


# --- presence and occupancy ----------------------------------------------------------------------


def test_drone_within_50_m_is_docked_and_beyond_is_not() -> None:
    hubs = [hub("hub-a")]

    assert docked_hub(drone("D1", metres_east(45), 0), hubs, 50) is hubs[0]
    assert docked_hub(drone("D2", metres_east(55), 0), hubs, 50) is None


def test_the_radius_is_configurable() -> None:
    hubs = [hub("hub-a")]

    assert docked_hub(drone("D1", metres_east(120), 0), hubs, 150) is hubs[0]
    assert docked_hub(drone("D1", metres_east(120), 0), hubs, 100) is None


def test_an_in_flight_drone_is_never_docked_even_exactly_over_a_hub() -> None:
    hubs = [hub("hub-a")]

    assert docked_hub(drone("D1", 0, 0, DroneStatus.IN_FLIGHT), hubs, 50) is None


@pytest.mark.parametrize(
    "status", [DroneStatus.IDLE, DroneStatus.CHARGING, DroneStatus.MAINTENANCE]
)
def test_non_flying_drones_are_docked(status: DroneStatus) -> None:
    hubs = [hub("hub-a")]

    assert docked_hub(drone("D1", 0, 0, status), hubs, 50) is hubs[0]


def test_the_nearest_hub_wins_and_ties_go_to_the_lower_id() -> None:
    near, far = hub("hub-b", metres_east(10)), hub("hub-a", metres_east(30))
    assert docked_hub(drone("D1", 0, 0), [far, near], 50) is near

    left, right = hub("hub-z", metres_east(-20)), hub("hub-y", metres_east(20))
    assert docked_hub(drone("D2", 0, 0), [left, right], 50) is right


def test_occupancy_counts_only_docked_drones_and_in_flight_drones_count_nowhere() -> None:
    hubs = [hub("hub-a"), hub("hub-b", 1.0)]
    drones = [
        drone("D1", 0, 0),
        drone("D2", 0, 0, DroneStatus.CHARGING),
        drone("D3", 0, 0, DroneStatus.IN_FLIGHT),
        drone("D4", 1.0, 0),
        drone("D5", 0.5, 0),  # away from every Hub
    ]

    counts = hub_occupancy(drones, hubs, 50)

    assert counts["hub-a"] == 2
    assert counts["hub-b"] == 1
    assert sum(counts.values()) == 3


def test_the_administrative_hub_id_does_not_affect_presence() -> None:
    hubs = [hub("hub-a"), hub("hub-b", 1.0)]
    landed_elsewhere = drone("D1", 1.0, 0)  # hub_id is "hub-a", it sits at hub-b

    assert docked_hub(landed_elsewhere, hubs, 50) is hubs[1]


# --- energy --------------------------------------------------------------------------------------


def energy(out_km: float, back_km: float, weight: float, factor: float = 0.5) -> EnergyEstimate:
    return estimate_energy(
        outbound_km=out_km,
        return_km=back_km,
        weight_kg=weight,
        model=build_sf1_model(),
        payload_energy_factor=factor,
    )


def test_rates_follow_the_nominal_range_and_the_payload_factor() -> None:
    light = energy(5, 5, 0.3)
    heavy = energy(5, 5, 3.0)

    assert light.empty_rate_pct_per_km == pytest.approx(5.0)  # 100 % / 20 km
    assert light.loaded_rate_pct_per_km == pytest.approx(5.25)
    assert heavy.loaded_rate_pct_per_km == pytest.approx(7.5)
    assert heavy.reserve_pct == 20


def test_the_documented_examples_hold() -> None:
    light, heavy = energy(5, 5, 0.3), energy(5, 5, 3.0)

    assert light.expected_pct == pytest.approx(51.25)
    assert light.worst_case_pct == pytest.approx(52.5)
    assert light.required_battery_pct == pytest.approx(72.5)
    assert heavy.expected_pct == pytest.approx(62.5)
    assert heavy.worst_case_pct == pytest.approx(75.0)
    assert heavy.required_battery_pct == pytest.approx(95.0)


def test_a_heavier_parcel_needs_more_battery_for_the_same_route() -> None:
    assert energy(5, 5, 3.0).required_battery_pct > energy(5, 5, 1.5).required_battery_pct
    assert energy(5, 5, 1.5).required_battery_pct > energy(5, 5, 0.3).required_battery_pct


def test_outbound_carries_the_parcel_and_the_return_does_not() -> None:
    # Same total distance: moving distance to the loaded leg raises the expected energy.
    assert energy(8, 2, 3.0).expected_pct > energy(2, 8, 3.0).expected_pct


def test_the_worst_case_is_never_below_the_expected_case() -> None:
    for weight in (0.1, 1.5, 3.0):
        for out_km, back_km in ((1, 9), (5, 5), (9, 1)):
            estimate = energy(out_km, back_km, weight)
            assert estimate.worst_case_pct >= estimate.expected_pct - 1e-9


def test_a_zero_factor_makes_the_parcel_weight_irrelevant() -> None:
    assert energy(5, 5, 3.0, factor=0.0).worst_case_pct == pytest.approx(50.0)
    assert energy(5, 5, 0.3, factor=0.0).worst_case_pct == pytest.approx(50.0)


def test_longest_full_battery_routes_by_weight() -> None:
    # Total km at which required battery reaches 100 %: (100 - reserve) / loaded rate.
    assert 80 / energy(1, 0, 3.0).loaded_rate_pct_per_km == pytest.approx(10.67, abs=0.01)
    assert 80 / energy(1, 0, 1.5).loaded_rate_pct_per_km == pytest.approx(12.8, abs=0.01)
    assert 80 / energy(1, 0, 0.3).loaded_rate_pct_per_km > 14  # the 14 km budget binds instead


def test_battery_exactly_at_the_requirement_passes_and_below_fails() -> None:
    estimate = energy(5, 5, 3.0)  # requires exactly 95 %

    assert estimate.required_battery_pct == 95.0
    assert has_enough_battery(95, estimate)
    assert has_enough_battery(100, estimate)
    assert not has_enough_battery(94, estimate)
    assert not has_enough_battery(94.99, estimate)
