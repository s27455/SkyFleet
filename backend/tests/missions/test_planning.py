"""Mission feasibility rules, tested on plain objects (no database)."""

import math
from collections import Counter

import pytest

from app.drones.models import Drone, DroneModel, DroneStatus
from app.drones.seed import build_sf1_model
from app.hubs.models import Hub
from app.missions.capacity import choose_return_hub
from app.missions.planning import evaluate_plan
from app.missions.schemas import PlanResponse, ReasonCode
from app.orders.models import DeliveryOrder, OrderStatus

EQUATOR_KM_PER_DEGREE = 2 * math.pi * 6371.0 / 360


def hub(hub_id: str, lng: float, capacity: int = 50) -> Hub:
    return Hub(
        id=hub_id, name=hub_id, address="a", longitude=lng, latitude=0.0, drone_capacity=capacity
    )


def drone(
    drone_id: str,
    lng: float,
    *,
    status: DroneStatus = DroneStatus.IDLE,
    battery: int = 100,
    model: DroneModel | None = None,
) -> Drone:
    unit = Drone(
        id=drone_id,
        model_id="SF-1",
        hub_id="hub-a",
        status=status.value,
        battery_pct=battery,
        longitude=lng,
        latitude=0.0,
    )
    unit.model = model or build_sf1_model()
    return unit


def order(
    dest_lng: float,
    *,
    weight: float = 1.5,
    status: OrderStatus = OrderStatus.READY_FOR_PICKUP,
    origin: str = "hub-a",
) -> DeliveryOrder:
    return DeliveryOrder(
        id="ORD-1",
        origin_hub_id=origin,
        destination_address="ul. Test 1",
        destination_longitude=dest_lng,
        destination_latitude=0.0,
        package_weight_kg=weight,
        status=status.value,
    )


def plan(
    the_order: DeliveryOrder,
    the_drone: Drone,
    hubs: list[Hub],
    others: list[Drone] | None = None,
    *,
    order_active: bool = False,
    drone_active: bool = False,
    factor: float = 0.5,
) -> PlanResponse:
    return evaluate_plan(
        order=the_order,
        drone=the_drone,
        hubs=hubs,
        drones=[the_drone, *(others or [])],
        order_has_active_mission=order_active,
        drone_has_active_mission=drone_active,
        payload_energy_factor=factor,
        dock_proximity_m=50,
    )


def codes(result: PlanResponse) -> set[ReasonCode]:
    return {reason.code for reason in result.reasons}


def km(degrees_of_longitude: float) -> float:
    return degrees_of_longitude * EQUATOR_KM_PER_DEGREE


# Hubs on the equator: A at 0 km, B about 3.3 km east, C about 6.7 km east.
A, B, C = hub("hub-a", 0.0), hub("hub-b", 0.03), hub("hub-c", 0.06)
HUBS = [A, B, C]
DESTINATION = 0.035  # about 3.9 km from A; nearest Hub B, then C, then A


def test_a_ready_order_and_a_docked_idle_drone_get_a_deterministic_eligible_plan() -> None:
    first = plan(order(DESTINATION), drone("D1", 0.0), HUBS)
    second = plan(order(DESTINATION), drone("D1", 0.0), HUBS)

    assert first.eligible
    assert first.reasons == []
    assert first == second
    assert first.route.origin_hub_id == "hub-a"
    assert first.route.return_hub_id == "hub-b"  # nearest Hub to the destination
    assert first.route.basis_hub_id == "hub-b"
    assert first.route.origin_to_destination_km == pytest.approx(km(DESTINATION))
    assert first.route.destination_to_return_km == pytest.approx(km(0.005))
    assert first.route.total_km == pytest.approx(km(DESTINATION) + km(0.005))
    assert first.distance_budget_km == 14.0
    assert first.skipped_return_hubs == []
    assert any("not reserved" in note for note in first.notes)


def test_the_plan_reports_the_energy_estimate_and_hub_occupancy() -> None:
    result = plan(order(DESTINATION, weight=3.0), drone("D1", 0.0), HUBS, [drone("D2", 0.03)])

    assert result.energy.loaded_rate_pct_per_km == pytest.approx(7.5)
    assert result.energy.required_battery_pct == pytest.approx(result.route.total_km * 7.5 + 20)
    assert result.energy.worst_case_pct >= result.energy.expected_pct
    assert result.energy.drone_battery_pct == 100
    assert [(h.hub_id, h.docked_drones, h.capacity) for h in result.hub_occupancy] == [
        ("hub-a", 1, 50),
        ("hub-b", 1, 50),
        ("hub-c", 0, 50),
    ]


def test_planning_does_not_modify_its_inputs() -> None:
    the_order, the_drone = order(DESTINATION), drone("D1", 0.0)
    before = (
        the_order.status,
        the_order.package_weight_kg,
        the_drone.status,
        the_drone.battery_pct,
        the_drone.longitude,
        the_drone.latitude,
        [(h.id, h.drone_capacity) for h in HUBS],
    )

    plan(the_order, the_drone, HUBS)

    assert before == (
        the_order.status,
        the_order.package_weight_kg,
        the_drone.status,
        the_drone.battery_pct,
        the_drone.longitude,
        the_drone.latitude,
        [(h.id, h.drone_capacity) for h in HUBS],
    )


# --- one reason at a time ------------------------------------------------------------------------


@pytest.mark.parametrize("status", [OrderStatus.CREATED, OrderStatus.AWAITING_HANDOVER])
def test_an_order_not_yet_at_the_hub_is_not_assignable(status: OrderStatus) -> None:
    result = plan(order(DESTINATION, status=status), drone("D1", 0.0), HUBS)

    assert codes(result) == {ReasonCode.ORDER_NOT_READY}
    assert not result.eligible


def test_an_order_with_an_active_mission_is_not_assignable() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0), HUBS, order_active=True)

    assert codes(result) == {ReasonCode.ORDER_ALREADY_ASSIGNED}


def test_a_drone_with_an_active_mission_is_not_assignable() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0), HUBS, drone_active=True)

    assert codes(result) == {ReasonCode.DRONE_ALREADY_ASSIGNED}


def test_only_an_idle_drone_is_available() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0, status=DroneStatus.CHARGING), HUBS)

    assert codes(result) == {ReasonCode.DRONE_NOT_AVAILABLE}


def test_a_drone_in_maintenance_is_unavailable_and_never_docked_at_the_origin_hub() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0, status=DroneStatus.MAINTENANCE), HUBS)

    assert codes(result) == {ReasonCode.DRONE_NOT_AVAILABLE, ReasonCode.DRONE_NOT_AT_ORIGIN_HUB}


def test_an_in_flight_drone_is_neither_available_nor_at_the_hub() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0, status=DroneStatus.IN_FLIGHT), HUBS)

    assert codes(result) == {ReasonCode.DRONE_NOT_AVAILABLE, ReasonCode.DRONE_NOT_AT_ORIGIN_HUB}


def test_a_drone_docked_at_another_hub_is_not_at_the_origin_hub() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.03), HUBS)

    assert codes(result) == {ReasonCode.DRONE_NOT_AT_ORIGIN_HUB}


def test_a_drone_away_from_every_hub_is_not_at_the_origin_hub() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.015), HUBS)

    assert codes(result) == {ReasonCode.DRONE_NOT_AT_ORIGIN_HUB}


def test_a_parcel_above_the_model_payload_is_overweight() -> None:
    result = plan(order(DESTINATION, weight=3.5), drone("D1", 0.0), HUBS)

    assert ReasonCode.OVERWEIGHT in codes(result)


def test_the_payload_limit_comes_from_the_drone_model() -> None:
    model = build_sf1_model()
    model.max_payload_kg = 5.0

    result = plan(order(DESTINATION, weight=4.0), drone("D1", 0.0, model=model), HUBS)

    assert result.eligible


def test_a_route_beyond_the_distance_budget_is_too_long() -> None:
    far = 0.13  # about 14.5 km from A, and Hub A is the only Hub
    result = plan(order(far), drone("D1", 0.0), [A])

    assert ReasonCode.ROUTE_TOO_LONG in codes(result)
    assert result.route.return_hub_id is None


def test_a_low_battery_is_insufficient() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0, battery=10), HUBS)

    assert codes(result) == {ReasonCode.INSUFFICIENT_BATTERY}
    assert result.route.return_hub_id is None


def test_several_reasons_are_reported_together() -> None:
    result = plan(
        order(DESTINATION, status=OrderStatus.CREATED, weight=3.5),
        drone("D1", 0.03, status=DroneStatus.CHARGING, battery=5),
        HUBS,
        order_active=True,
        drone_active=True,
    )

    assert codes(result) == {
        ReasonCode.ORDER_NOT_READY,
        ReasonCode.ORDER_ALREADY_ASSIGNED,
        ReasonCode.DRONE_ALREADY_ASSIGNED,
        ReasonCode.DRONE_NOT_AVAILABLE,
        ReasonCode.DRONE_NOT_AT_ORIGIN_HUB,
        ReasonCode.OVERWEIGHT,
        ReasonCode.INSUFFICIENT_BATTERY,
    }


# --- energy: weight, battery and distance limits -------------------------------------------------

LONG_DESTINATION = 0.08  # about 8.9 km from A; the nearest Hub (0.075) is only about 0.6 km away
LONG_HUBS = [A, hub("hub-b", 0.075)]


def test_a_heavy_parcel_is_refused_where_a_light_one_is_accepted() -> None:
    battery = 90
    light = plan(order(LONG_DESTINATION, weight=0.3), drone("D1", 0.0, battery=battery), LONG_HUBS)
    heavy = plan(order(LONG_DESTINATION, weight=3.0), drone("D1", 0.0, battery=battery), LONG_HUBS)

    assert light.eligible
    assert codes(heavy) == {ReasonCode.INSUFFICIENT_BATTERY}
    assert heavy.energy.required_battery_pct > battery > light.energy.required_battery_pct


def test_the_battery_requirement_is_exact_at_the_boundary() -> None:
    required = plan(order(LONG_DESTINATION, weight=3.0), drone("D1", 0.0), LONG_HUBS).energy
    needed = required.required_battery_pct
    assert math.floor(needed) < needed < math.ceil(needed)

    below = plan(
        order(LONG_DESTINATION, weight=3.0), drone("D1", 0.0, battery=math.floor(needed)), LONG_HUBS
    )
    enough = plan(
        order(LONG_DESTINATION, weight=3.0), drone("D1", 0.0, battery=math.ceil(needed)), LONG_HUBS
    )

    assert ReasonCode.INSUFFICIENT_BATTERY in codes(below)
    assert enough.eligible


def test_the_distance_budget_is_inclusive() -> None:
    base = plan(order(DESTINATION), drone("D1", 0.0), HUBS)
    total = base.route.total_km

    at_limit = build_sf1_model()
    at_limit.recommended_mission_range_km = total
    just_over = build_sf1_model()
    just_over.recommended_mission_range_km = total - 1e-9

    assert plan(order(DESTINATION), drone("D1", 0.0, model=at_limit), HUBS).eligible
    assert ReasonCode.ROUTE_TOO_LONG in codes(
        plan(order(DESTINATION), drone("D1", 0.0, model=just_over), HUBS)
    )


def test_the_payload_energy_factor_is_configurable() -> None:
    cheap = plan(order(DESTINATION, weight=3.0), drone("D1", 0.0), HUBS, factor=0.0)
    costly = plan(order(DESTINATION, weight=3.0), drone("D1", 0.0), HUBS, factor=1.0)

    assert cheap.energy.loaded_rate_pct_per_km == pytest.approx(5.0)
    assert costly.energy.loaded_rate_pct_per_km == pytest.approx(10.0)
    assert costly.energy.required_battery_pct > cheap.energy.required_battery_pct


def test_the_safety_check_assumes_the_parcel_stays_on_board_for_the_whole_route() -> None:
    result = plan(order(DESTINATION, weight=3.0), drone("D1", 0.0), HUBS)

    assert result.energy.worst_case_pct == pytest.approx(result.route.total_km * 7.5)
    assert result.energy.required_battery_pct == pytest.approx(result.energy.worst_case_pct + 20)
    assert result.energy.expected_pct < result.energy.worst_case_pct


# --- return Hub and physical capacity -------------------------------------------------------------


def test_the_return_hub_may_be_the_origin_hub() -> None:
    result = plan(order(0.001), drone("D1", 0.0), HUBS)

    assert result.eligible
    assert result.route.return_hub_id == "hub-a"


def test_a_drone_docked_at_its_own_full_origin_hub_can_plan_to_return_there() -> None:
    full_a = hub("hub-a", 0.0, capacity=2)
    unit, other = drone("D1", 0.0), drone("D2", 0.0)  # A holds 2 of 2

    result = plan(order(0.001), unit, [full_a, B, C], [other])

    assert result.route.return_hub_id == "hub-a"  # it vacates its own place on takeoff


def test_a_full_nearest_hub_is_skipped_for_the_next_nearest() -> None:
    full_b = hub("hub-b", 0.03, capacity=1)
    squatter = drone("D2", 0.03)  # B holds 1 of 1

    result = plan(order(DESTINATION), drone("D1", 0.0), [A, full_b, C], [squatter])

    assert result.eligible
    assert result.route.return_hub_id == "hub-c"
    assert [(s.hub_id, s.reason) for s in result.skipped_return_hubs] == [("hub-b", "HUB_FULL")]
    assert result.route.destination_to_return_km == pytest.approx(km(0.06 - DESTINATION))


def test_all_reachable_hubs_full_means_no_return_hub() -> None:
    far = 0.072  # about 8.0 km from A; B (0.07) is the nearest Hub, A would make 16 km
    full_b = hub("hub-b", 0.07, capacity=1)

    result = plan(order(far), drone("D1", 0.0), [A, full_b], [drone("D2", 0.07)])

    assert codes(result) == {ReasonCode.RETURN_HUBS_FULL}
    assert result.route.return_hub_id is None
    assert {(s.hub_id, s.reason) for s in result.skipped_return_hubs} == {
        ("hub-b", "HUB_FULL"),
        ("hub-a", "OUT_OF_RANGE"),
    }


def test_in_flight_drones_do_not_occupy_a_hub() -> None:
    full_b = hub("hub-b", 0.03, capacity=1)
    flying = drone("D2", 0.03, status=DroneStatus.IN_FLIGHT)  # over B but not docked

    result = plan(order(DESTINATION), drone("D1", 0.0), [A, full_b, C], [flying])

    assert result.route.return_hub_id == "hub-b"
    assert result.skipped_return_hubs == []


def test_the_planned_return_hub_never_skips_a_nearer_hub_with_room() -> None:
    result = plan(order(DESTINATION), drone("D1", 0.0), HUBS, [drone("D2", 0.06)])

    assert result.route.return_hub_id == "hub-b"


def test_choose_return_hub_reports_no_choice_when_nothing_is_reachable() -> None:
    candidates = [(B, 0.5), (C, 2.8)]

    def reachable(distance: float) -> bool:
        return False

    choice = choose_return_hub(candidates, Counter(), docked_at=None, is_reachable=reachable)

    assert choice.hub is None
    assert [reason for _, reason in choice.skipped] == ["OUT_OF_RANGE", "OUT_OF_RANGE"]
