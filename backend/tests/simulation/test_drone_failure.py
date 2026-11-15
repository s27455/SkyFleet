"""Drone failure and emergency landing (Feature 018C) on SQLite with a controlled clock."""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events import repository as event_repository
from app.events.models import OperationalEvent
from app.hubs.models import Hub
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import distance_km
from app.orders import cancellation, repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import engine
from app.simulation.failure import (
    FailureResult,
    FailureStage,
    NoEligibleTargetError,
    eligible_mission_ids,
    trigger_drone_failure,
)
from app.simulation.flight import (
    Leg,
    LegKind,
    emergency_landing_point,
    emergency_legs,
    leg_from_dict,
)
from app.simulation.models import EmergencyReason, FlightPhase, MissionFlight

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
# ORD-001 (0.8 kg) starts at Galeria Bałtycka: about 36 s in total, the outbound leg ends at about
# 16.4 s, the parcel is handed over at about 19.4 s and the landing is decided at about 34 s.
ORDER, DRONE = "ORD-001", "DRN-010"
BALTYCKA = "hub-galeria-baltycka"


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


class World:
    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def advance(self, mission_id: str, seconds: float) -> None:
        engine.advance_flight(self.factory, self.settings, mission_id, at(seconds))
        self.session.expire_all()

    def fail(self, seconds: float, seed: int = 1) -> FailureResult:
        result = trigger_drone_failure(
            self.session, at(seconds), self.settings, rng=random.Random(seed)
        )
        self.session.expire_all()
        return result

    def flight(self, mission_id: str) -> MissionFlight:
        flight = self.session.get(MissionFlight, mission_id)
        assert flight is not None
        return flight

    def mission(self, mission_id: str) -> Mission:
        mission = self.session.get(Mission, mission_id)
        assert mission is not None
        return mission

    def order(self, order_id: str) -> DeliveryOrder:
        order = self.session.get(DeliveryOrder, order_id)
        assert order is not None
        return order

    def drone(self, drone_id: str) -> Drone:
        drone = self.session.get(Drone, drone_id)
        assert drone is not None
        return drone

    def events(self, order_id: str, kind: str = "DRONE_FAILURE") -> list[OperationalEvent]:
        found = event_repository.list_events(self.session, order_id=order_id)
        return [event for event in found if event.event_type == kind]


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


# --- the landing point and the emergency leg (pure functions) -------------------------------


def _leg(
    kind: LegKind, start: float, dur: float, a: tuple[float, float], b: tuple[float, float]
) -> Leg:
    return Leg(kind, start, dur, a, b, distance_km(a, b), loaded=True)


def test_the_emergency_landing_point_is_250_m_along_the_current_heading() -> None:
    origin, target = (18.60, 54.38), (18.62, 54.38)  # due east
    legs = [_leg(LegKind.OUTBOUND, 0, 10, origin, target)]
    position = (18.61, 54.38)

    point = emergency_landing_point(legs, 5, position, 250.0)

    assert distance_km(position, point) * 1000 == pytest.approx(250.0, abs=0.5)
    assert point[1] == pytest.approx(54.38, abs=1e-6)  # still due east
    assert point[0] > position[0]


def test_while_stationary_the_heading_of_the_last_moving_leg_is_used() -> None:
    origin, target = (18.60, 54.38), (18.60, 54.40)  # due north, then the delivery stop
    legs = [
        _leg(LegKind.OUTBOUND, 0, 10, origin, target),
        _leg(LegKind.DELIVERY, 10, 3, target, target),
    ]

    point = emergency_landing_point(legs, 11, target, 250.0)

    assert distance_km(target, point) * 1000 == pytest.approx(250.0, abs=0.5)
    assert point[1] > target[1] and point[0] == pytest.approx(target[0], abs=1e-6)


def test_the_landing_point_is_deterministic() -> None:
    legs = [_leg(LegKind.OUTBOUND, 0, 10, (18.6, 54.38), (18.63, 54.40))]

    assert emergency_landing_point(legs, 4, (18.61, 54.385), 250.0) == emergency_landing_point(
        legs, 4, (18.61, 54.385), 250.0
    )


def test_the_emergency_legs_cut_the_plan_and_add_one_approach_at_the_original_pace() -> None:
    a, b = (18.60, 54.38), (18.62, 54.38)
    legs = [
        _leg(LegKind.OUTBOUND, 0, 10, a, b),
        _leg(LegKind.DELIVERY, 10, 3, b, b),
        _leg(LegKind.RETURN, 13, 10, b, a),
    ]
    position, landing = (18.61, 54.38), (18.6134, 54.38)

    new = emergency_legs(legs, 5, position, landing, 20.0, loaded=True)

    assert [leg.kind for leg in new] == [LegKind.OUTBOUND, LegKind.EMERGENCY]
    assert new[0].target == position and new[0].duration_s == pytest.approx(5)
    approach = new[1]
    assert approach.start_s == 5 and approach.loaded is True
    assert approach.duration_s == pytest.approx(approach.distance_km * 20.0)


# --- no target ------------------------------------------------------------------------------


def test_with_no_flying_drone_nothing_is_created(world: World) -> None:
    with pytest.raises(NoEligibleTargetError):
        world.fail(5)

    assert world.session.scalars(select(OperationalEvent)).all() == []


def test_the_endpoint_answers_409_with_a_stable_code_when_nothing_flies(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/api/incidents/drone-failure")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_ELIGIBLE_TARGET"
    assert client.get("/api/events", params={"drone_id": DRONE}).json() == []


def test_a_drone_that_is_not_flying_a_mission_is_never_a_target(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    assert eligible_mission_ids(world.session) == [mission_id]
    drone = world.drone("DRN-001")
    assert drone.status == DroneStatus.IDLE  # docked drones are not eligible
    assert eligible_mission_ids(world.session) == [mission_id]


# --- failure before the delivery ------------------------------------------------------------


def test_a_failure_in_flight_starts_a_continuous_approach_without_teleport_or_reset(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    before = world.flight(mission_id)
    position, battery = (before.longitude, before.latitude), before.battery_pct

    result = world.fail(8)

    assert (result.drone_id, result.mission_id, result.order_id) == (DRONE, mission_id, ORDER)
    assert result.stage == FailureStage.BEFORE_DELIVERY
    flight = world.flight(mission_id)
    assert flight.failed_at is not None and flight.phase == FlightPhase.EMERGENCY_APPROACH
    assert (flight.longitude, flight.latitude) == pytest.approx(position)  # no teleport
    assert flight.battery_pct == pytest.approx(battery)  # no reset
    approach = leg_from_dict(flight.legs[-1])
    assert approach.kind == LegKind.EMERGENCY and approach.loaded is True
    assert distance_km(approach.origin, approach.target) * 1000 == pytest.approx(250.0, abs=0.5)
    assert (flight.target_longitude, flight.target_latitude) == pytest.approx(approach.target)
    assert world.drone(DRONE).status == DroneStatus.IN_FLIGHT  # still flying, not yet grounded
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY


def test_the_failure_is_recorded_once_with_its_references_and_the_landing_point(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)

    for seconds in (9, 12, 40, 200):  # worker ticks never add another incident
        world.advance(mission_id, seconds)

    (event,) = world.events(ORDER)
    assert (event.origin, event.mission_id, event.flight_id, event.drone_id) == (
        "MANUAL",
        mission_id,
        mission_id,
        DRONE,
    )
    assert event.occurred_at.replace(tzinfo=UTC) == at(8)
    assert event.details is not None and event.details["stage"] == "BEFORE_DELIVERY"
    landing = world.flight(mission_id)
    assert event.details["landing_position"] == pytest.approx([landing.longitude, landing.latitude])


def test_the_drone_flies_the_approach_then_is_grounded_and_the_mission_never_resumes(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    start = (world.flight(mission_id).longitude, world.flight(mission_id).latitude)
    world.fail(8)
    approach = leg_from_dict(world.flight(mission_id).legs[-1])

    world.advance(mission_id, 8 + approach.duration_s / 2)  # halfway down the approach
    halfway = world.flight(mission_id)
    assert halfway.phase == FlightPhase.EMERGENCY_APPROACH
    here = (halfway.longitude, halfway.latitude)
    assert 0 < distance_km(start, here) * 1000 < 250  # moving continuously, not there yet
    assert world.drone(DRONE).status == DroneStatus.IN_FLIGHT

    world.advance(mission_id, 500)  # far beyond the original delivery and landing

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY
    assert flight.emergency_reason == EmergencyReason.DRONE_FAILURE
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.MAINTENANCE
    assert (drone.longitude, drone.latitude) == pytest.approx(approach.target)
    assert distance_km(start, (drone.longitude, drone.latitude)) * 1000 == pytest.approx(
        250.0, abs=0.5
    )
    order = world.order(ORDER)
    assert order.status == OrderStatus.OUT_FOR_DELIVERY  # not DELIVERED, no new status
    assert order.delivered_at is None and flight.delivered_at is None
    assert 0 < flight.battery_pct < 100


def test_a_grounded_drone_counts_at_no_hub_and_cannot_be_assigned_or_charged(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)
    world.advance(mission_id, 500)

    drones = world.session.scalars(select(Drone)).all()
    hubs = world.session.scalars(select(Hub)).all()
    occupancy = hub_occupancy(drones, hubs, sim_settings.hub_dock_proximity_m)
    assert occupancy[BALTYCKA] == 2  # DRN-011 and DRN-012 only
    from app.missions import service as missions_service
    from app.simulation.charging import ChargingState, charge_step

    plan = missions_service.preview_plan(world.session, "ORD-002", DRONE, sim_settings)
    assert plan.eligible is False
    before = world.drone(DRONE).battery_pct
    charge_step(world.factory, sim_settings, at(600), ChargingState())
    world.session.expire_all()
    assert (world.drone(DRONE).status, world.drone(DRONE).battery_pct) == (
        DroneStatus.MAINTENANCE,
        before,
    )


def test_the_grounded_state_survives_a_restart_and_repeated_ticks(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)
    world.advance(mission_id, 500)
    grounded = world.flight(mission_id)
    snapshot = (grounded.phase, grounded.longitude, grounded.latitude, grounded.ended_at)

    world.advance(mission_id, 900)  # a tick after a long downtime, or after a restart
    world.advance(mission_id, 900)

    again = world.flight(mission_id)
    assert (again.phase, again.longitude, again.latitude, again.ended_at) == snapshot
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert len(world.events(ORDER)) == 1


def test_a_late_worker_finishes_the_approach_exactly_once_after_a_downtime(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)

    world.advance(mission_id, 1000)  # the first tick after the approach long ended

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY
    assert flight.ended_at is not None and flight.ended_at.replace(tzinfo=UTC) == at(1000)


# --- one incident per flight ----------------------------------------------------------------


def test_a_second_trigger_finds_no_eligible_target_and_adds_no_event(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)

    with pytest.raises(NoEligibleTargetError):
        world.fail(9)

    assert len(world.events(ORDER)) == 1


def test_the_trigger_chooses_among_several_flying_drones_and_fails_exactly_one(
    world: World, launch: Launch
) -> None:
    first = launch(ORDER, DRONE)
    second = launch("ORD-004", "DRN-007")
    world.advance(first, 8)
    world.advance(second, 8)

    result = world.fail(8, seed=3)

    failed = [m for m in (first, second) if world.flight(m).failed_at is not None]
    assert failed == [result.mission_id]
    other = second if result.mission_id == first else first
    assert world.flight(other).phase == FlightPhase.OUTBOUND  # the other flight is untouched


def test_the_same_seed_chooses_the_same_drone(world: World, launch: Launch) -> None:
    launch(ORDER, DRONE)
    launch("ORD-004", "DRN-007")
    ids = eligible_mission_ids(world.session)
    first = random.Random(7)
    second = random.Random(7)
    one, two = list(ids), list(ids)
    first.shuffle(one)
    second.shuffle(two)
    assert one == two


def test_a_flight_whose_next_milestone_is_already_due_is_left_to_the_worker(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)

    with pytest.raises(NoEligibleTargetError):
        world.fail(20)  # past the handover time, the worker has not ticked yet

    assert world.flight(mission_id).failed_at is None
    assert world.events(ORDER) == []


# --- the other stages -----------------------------------------------------------------------


def test_a_failure_on_the_way_back_does_not_undo_the_delivery(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 25)  # delivered at about 19.4 s; landing is decided at about 34 s
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    delivered_at = world.order(ORDER).delivered_at

    result = world.fail(26)

    assert result.stage == FailureStage.AFTER_DELIVERY
    approach = leg_from_dict(world.flight(mission_id).legs[-1])
    assert approach.loaded is False  # the parcel is gone
    world.advance(mission_id, 500)
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert world.order(ORDER).delivered_at == delivered_at
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert world.flight(mission_id).delivered_at is not None


def test_a_failure_during_a_recall_keeps_the_cancellation_and_the_drone_grounded(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    cancellation.cancel_order(world.session, ORDER, at(8), world.settings)
    world.session.expire_all()
    assert world.flight(mission_id).recalled_at is not None

    result = world.fail(10)

    assert result.stage == FailureStage.RECALL
    world.advance(mission_id, 500)
    assert world.order(ORDER).status == OrderStatus.CANCELLED  # not revived
    assert world.flight(mission_id).recalled_at is not None
    assert world.flight(mission_id).phase == FlightPhase.EMERGENCY
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert len(world.events(ORDER)) == 1
    assert len(world.events(ORDER, "ORDER_CANCELLED")) == 1


# --- cancellation of an order whose drone failed --------------------------------------------


def test_cancelling_during_the_approach_is_refused_with_a_clear_reason(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)

    with pytest.raises(cancellation.DroneFailedError) as refused:
        cancellation.cancel_order(world.session, ORDER, at(9), world.settings)

    assert "making an emergency landing" in str(refused.value)
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.flight(mission_id).phase == FlightPhase.EMERGENCY_APPROACH


def test_cancelling_after_the_grounding_is_refused_and_never_repairs_the_drone(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)
    world.advance(mission_id, 500)

    with pytest.raises(cancellation.DroneFailedError) as refused:
        cancellation.cancel_order(world.session, ORDER, at(501), world.settings)

    assert "grounded, requiring service" in str(refused.value)
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.order(ORDER).cancelled_at is None
    assert world.events(ORDER, "ORDER_CANCELLED") == []


def test_the_cancel_endpoint_explains_the_refusal_with_a_stable_code(
    client: TestClient, world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)
    world.advance(mission_id, 500)
    monkeypatch.setattr(clock, "utcnow", lambda: at(501))

    response = client.post(f"/api/orders/{ORDER}/cancel")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "DRONE_FAILED"
    assert "interrupted" in detail["message"] and "requiring service" in detail["message"]


# --- visibility of an interrupted order -----------------------------------------------------


def test_an_interrupted_order_leaves_the_active_views_120_s_after_the_landing_completed(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)
    world.advance(mission_id, 500)  # grounded at the real time "500 s": ended_at
    window = 120.0

    inside = repository.list_active_orders(world.session, at(500 + window - 1), window)
    outside = repository.list_active_orders(world.session, at(500 + window + 1), window)
    history = repository.list_orders(world.session)

    assert ORDER in [o.id for o in inside]
    assert ORDER not in [o.id for o in outside]
    assert ORDER in [o.id for o in history]  # never deleted
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY


def test_the_order_stays_visible_during_the_approach(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.fail(8)

    active = repository.list_active_orders(world.session, at(5000), 120.0)  # no landing yet

    assert ORDER in [o.id for o in active]


# --- API ------------------------------------------------------------------------------------


def test_the_endpoint_fails_a_flying_drone_and_the_flights_api_reports_it(
    client: TestClient, world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    monkeypatch.setattr(clock, "utcnow", lambda: at(8))

    response = client.post("/api/incidents/drone-failure")

    assert response.status_code == 200
    body = response.json()
    assert (body["drone_id"], body["mission_id"], body["order_id"]) == (DRONE, mission_id, ORDER)
    assert body["stage"] == "BEFORE_DELIVERY" and len(body["landing_position"]) == 2
    flights = client.get("/api/flights").json()["flights"]
    (flight,) = [f for f in flights if f["mission_id"] == mission_id]
    assert flight["phase"] == "EMERGENCY_APPROACH" and flight["failed_at"] is not None
    events = client.get("/api/events", params={"order_id": ORDER}).json()
    assert [e["event_type"] for e in events] == ["DRONE_FAILURE"]
    assert events[0]["origin"] == "MANUAL"
