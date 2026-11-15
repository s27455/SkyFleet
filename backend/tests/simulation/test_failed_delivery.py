"""Failed delivery and parcel return (Feature 018D) on SQLite with a controlled clock."""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.common.clock import as_utc
from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events import repository as event_repository
from app.events.models import EventOrigin, OperationalEvent
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionStatus
from app.missions.routing import distance_km
from app.orders import cancellation, repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import engine
from app.simulation.failed_delivery import (
    RecipientUnavailableResult,
    eligible_mission_ids,
    trigger_recipient_unavailable,
)
from app.simulation.failure import (
    FailureStage,
    NoEligibleTargetError,
    trigger_drone_failure,
)
from app.simulation.flight import Leg, LegKind, handover_failed_legs, leg_from_dict
from app.simulation.models import FlightPhase, MissionFlight

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
# ORD-001 (0.8 kg) starts at Galeria Bałtycka: about 36 s in total, the outbound leg ends at about
# 16.4 s, the parcel would be handed over at about 19.4 s and the landing is decided at about 34 s.
ORDER, DRONE = "ORD-001", "DRN-010"
EVENT = "RECIPIENT_UNAVAILABLE"


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


class World:
    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def advance(self, mission_id: str, seconds: float) -> None:
        engine.advance_flight(self.factory, self.settings, mission_id, at(seconds))
        self.session.expire_all()

    def mark(
        self, seconds: float, seed: int = 1, origin: EventOrigin = EventOrigin.MANUAL
    ) -> RecipientUnavailableResult:
        result = trigger_recipient_unavailable(
            self.session, at(seconds), self.settings, origin=origin, rng=random.Random(seed)
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

    def order(self, order_id: str = ORDER) -> DeliveryOrder:
        order = self.session.get(DeliveryOrder, order_id)
        assert order is not None
        return order

    def drone(self, drone_id: str = DRONE) -> Drone:
        drone = self.session.get(Drone, drone_id)
        assert drone is not None
        return drone

    def events(self, order_id: str = ORDER, kind: str = EVENT) -> list[OperationalEvent]:
        found = event_repository.list_events(self.session, order_id=order_id)
        return [event for event in found if event.event_type == kind]


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


# --- the loaded return leg (pure function) --------------------------------------------------


def test_the_handover_failed_legs_keep_the_stop_and_return_loaded_from_the_destination() -> None:
    a, b, c = (18.60, 54.38), (18.62, 54.38), (18.60, 54.39)
    legs = [
        Leg(LegKind.OUTBOUND, 0, 10, a, b, distance_km(a, b), loaded=True),
        Leg(LegKind.DELIVERY, 10, 3, b, b, 0.0, loaded=True),
        Leg(LegKind.RETURN, 13, 10, b, a, distance_km(b, a), loaded=False),
    ]

    new = handover_failed_legs(legs, c, 20.0)

    assert [leg.kind for leg in new] == [LegKind.OUTBOUND, LegKind.DELIVERY, LegKind.RETURN]
    back = new[2]
    assert back.loaded is True  # the parcel is still on board
    assert (back.start_s, back.origin, back.target) == (13, b, c)  # continuous from the stop
    assert back.duration_s == pytest.approx(back.distance_km * 20.0)


# --- no target -------------------------------------------------------------------------------


def test_with_no_flying_delivery_nothing_is_created(world: World) -> None:
    with pytest.raises(NoEligibleTargetError):
        world.mark(5)

    assert world.session.scalars(select(OperationalEvent)).all() == []


def test_the_endpoint_answers_409_with_a_stable_code_when_nothing_flies(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/api/incidents/recipient-unavailable")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "NO_ELIGIBLE_TARGET"
    assert client.get("/api/events", params={"order_id": ORDER}).json() == []


def test_a_flight_past_its_handover_is_no_longer_a_target(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 25)  # delivered

    assert eligible_mission_ids(world.session) == []
    with pytest.raises(NoEligibleTargetError):
        world.mark(25)
    assert world.flight(mission_id).recipient_unavailable_at is None


def test_a_flight_whose_handover_is_already_due_is_left_to_the_worker(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)

    with pytest.raises(NoEligibleTargetError):
        world.mark(21)  # the stop ended at about 19.4 s; the worker has not run yet

    assert world.flight(mission_id).recipient_unavailable_at is None


def test_no_reachable_hub_with_the_parcel_means_no_target(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.settings = sim_settings.model_copy(update={"sim_critical_battery_pct": 99.0})

    with pytest.raises(NoEligibleTargetError):
        world.mark(8)

    assert world.flight(mission_id).recipient_unavailable_at is None


# --- the pending outcome ---------------------------------------------------------------------


def test_the_trigger_only_stores_a_pending_outcome(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    before = world.flight(mission_id)
    position, battery, legs = (
        (before.longitude, before.latitude),
        before.battery_pct,
        list(before.legs),
    )

    result = world.mark(8)

    assert (result.drone_id, result.mission_id, result.order_id) == (DRONE, mission_id, ORDER)
    assert abs((result.attempt_at - at(19.4)).total_seconds()) < 1.0  # the scheduled attempt
    flight = world.flight(mission_id)
    assert flight.recipient_unavailable_at is not None
    assert as_utc(flight.recipient_unavailable_at) == at(8)
    assert flight.handover_failed_at is None
    assert (flight.longitude, flight.latitude) == pytest.approx(position)  # untouched
    assert flight.battery_pct == pytest.approx(battery)
    assert flight.legs == legs  # the route is unchanged: the drone still goes to the recipient
    assert world.order().status == OrderStatus.OUT_FOR_DELIVERY  # nothing failed yet
    assert world.order().delivery_failed_at is None
    assert world.events() == []  # an event only when the handover really fails
    assert world.drone().status == DroneStatus.IN_FLIGHT


def test_the_drone_still_reaches_the_destination_before_anything_fails(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(2)

    world.advance(mission_id, 16)  # still outbound, close to the destination

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.OUTBOUND
    assert world.order().status == OrderStatus.OUT_FOR_DELIVERY
    assert world.events() == []


def test_a_drone_already_at_the_stop_can_still_be_marked(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 18)
    assert world.flight(mission_id).phase == FlightPhase.DELIVERING

    result = world.mark(18)

    assert result.mission_id == mission_id
    world.advance(mission_id, 20)
    assert world.order().status == OrderStatus.DELIVERY_FAILED


def test_a_second_trigger_for_the_same_delivery_finds_no_target(
    world: World, launch: Launch
) -> None:
    launch(ORDER, DRONE)
    world.mark(5)

    with pytest.raises(NoEligibleTargetError):
        world.mark(6)


# --- the failed handover ---------------------------------------------------------------------


def test_at_the_destination_the_parcel_is_not_delivered_and_the_drone_turns_back_loaded(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.mark(8)

    world.advance(mission_id, 21)  # just after the attempt, before the landing decision

    order = world.order()
    assert order.status == OrderStatus.DELIVERY_FAILED
    assert order.delivered_at is None  # never a delivery
    assert order.delivery_failed_at is not None
    assert as_utc(order.delivery_failed_at) == at(
        21
    )  # real UTC of the commit: starts the 120 s window
    flight = world.flight(mission_id)
    assert flight.delivered_at is None and flight.handover_failed_at is not None
    legs = [leg_from_dict(entry) for entry in flight.legs]
    assert [leg.kind for leg in legs] == [LegKind.OUTBOUND, LegKind.DELIVERY, LegKind.RETURN]
    assert legs[-1].loaded is True
    assert flight.phase == FlightPhase.RETURNING
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT  # until it lands
    assert world.drone().status == DroneStatus.IN_FLIGHT
    assert flight.landing_target_hub_id  # the loaded return has a target Hub
    assert flight.tried_hub_ids == []


def test_exactly_one_event_records_the_failed_handover_with_its_references(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.mark(8)

    for seconds in (21, 22, 25, 40, 200, 200):  # worker ticks never add another event
        world.advance(mission_id, seconds)

    (event,) = world.events()
    assert (event.origin, event.mission_id, event.flight_id, event.drone_id) == (
        "MANUAL",
        mission_id,
        mission_id,
        DRONE,
    )
    assert event.dedupe_key == f"{EVENT}:{mission_id}"
    assert event.details is not None and event.details["return_hub_id"]
    assert as_utc(event.occurred_at) == at(21)


def test_a_manual_trigger_is_stored_as_manual_but_the_event_waits_for_the_handover(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.mark(5)

    assert world.flight(mission_id).recipient_unavailable_origin == "MANUAL"
    assert world.events() == []  # timing unchanged: no event at the trigger
    world.advance(mission_id, 21)
    (event,) = world.events()
    assert event.origin == "MANUAL"


def test_an_automatic_trigger_is_recorded_as_automatic_at_the_failed_handover(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.mark(5, origin=EventOrigin.AUTOMATIC)

    assert world.flight(mission_id).recipient_unavailable_origin == "AUTOMATIC"
    assert world.events() == []
    world.advance(mission_id, 21)
    (event,) = world.events()
    assert event.origin == "AUTOMATIC"
    assert as_utc(event.occurred_at) == at(21)  # still recorded when the handover fails


def test_the_origin_survives_a_restart_and_a_late_worker(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(5, origin=EventOrigin.AUTOMATIC)
    world.session.close()  # nothing but the database carries the origin to the worker

    world.advance(mission_id, 500)

    (event,) = world.events()
    assert event.origin == "AUTOMATIC"
    assert len(world.events()) == 1


def test_the_return_is_continuous_and_consumes_energy_at_the_loaded_rate(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 21)
    flight = world.flight(mission_id)
    legs = [leg_from_dict(entry) for entry in flight.legs]
    stop, back = legs[1], legs[2]
    empty, loaded = consumption_rates(
        weight_kg=world.order().package_weight_kg,
        model=world.drone().model,
        payload_energy_factor=world.settings.mission_payload_energy_factor,
    )
    assert loaded > empty
    assert back.start_s == pytest.approx(stop.end_s)  # no gap and no jump
    assert back.origin == stop.target

    world.advance(mission_id, 200)

    landed = world.flight(mission_id)
    drained = flight.start_battery_pct - landed.battery_pct
    expected = (
        legs[0].distance_km * loaded + back.distance_km * loaded
    )  # the parcel never left the drone
    assert drained == pytest.approx(expected, rel=0.02)


def test_after_landing_the_drone_is_operational_and_docked_at_the_return_hub(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 21)
    hub_before = world.drone().hub_id

    world.advance(mission_id, 21)
    assert world.drone().hub_id == hub_before  # hub association only changes on landing

    world.advance(mission_id, 200)

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED
    assert flight.landed_hub_id == flight.landing_target_hub_id
    drone = world.drone()
    assert drone.status == DroneStatus.IDLE  # not MAINTENANCE
    assert drone.hub_id == flight.landed_hub_id
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    order = world.order()
    assert order.status == OrderStatus.DELIVERY_FAILED and order.delivered_at is None


def test_a_late_worker_still_fails_the_handover_once_and_lands_the_drone(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(5)

    world.advance(mission_id, 500)  # the worker was stopped for a long time

    order = world.order()
    assert order.status == OrderStatus.DELIVERY_FAILED
    assert order.delivery_failed_at is not None
    assert as_utc(order.delivery_failed_at) == at(
        500
    )  # real commit time, so the window is not skipped
    assert world.flight(mission_id).phase == FlightPhase.LANDED
    assert len(world.events()) == 1


def test_the_unmarked_flight_next_to_it_is_still_delivered_normally(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 500)

    order = world.order()
    assert order.status == OrderStatus.DELIVERED and order.delivered_at is not None
    assert order.delivery_failed_at is None
    assert world.events() == []


# --- interplay with 018B (cancellation) and 018C (drone failure) -----------------------------


def test_cancelling_while_the_outcome_is_pending_recalls_the_drone_and_nothing_fails(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.mark(8)

    cancellation.cancel_order(world.session, ORDER, at(9), world.settings)
    world.session.expire_all()
    world.advance(mission_id, 500)

    order = world.order()
    assert order.status == OrderStatus.CANCELLED  # the cancellation won
    assert order.delivery_failed_at is None and order.delivered_at is None
    assert world.flight(mission_id).handover_failed_at is None
    assert world.events() == []


def test_a_recalled_flight_is_not_a_target(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    cancellation.cancel_order(world.session, ORDER, at(8), world.settings)
    world.session.expire_all()

    assert eligible_mission_ids(world.session) == []
    with pytest.raises(NoEligibleTargetError):
        world.mark(9)


def test_an_order_whose_delivery_failed_cannot_be_cancelled(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 21)

    with pytest.raises(cancellation.OrderNotCancellableError) as error:
        cancellation.cancel_order(world.session, ORDER, at(22), world.settings)

    assert "delivery was attempted and failed" in str(error.value)
    world.session.expire_all()
    assert world.order().status == OrderStatus.DELIVERY_FAILED
    assert world.flight(mission_id).recalled_at is None  # nothing was recalled or changed


def test_the_cancel_endpoint_explains_the_refusal_with_a_stable_code(
    client: TestClient, world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 21)

    response = client.post(f"/api/orders/{ORDER}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_NOT_CANCELLABLE"
    assert "recipient unavailable" in response.json()["detail"]["message"]


def test_a_drone_failure_while_the_outcome_is_pending_wins(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.mark(8)

    trigger_drone_failure(world.session, at(9), world.settings, rng=random.Random(1))
    world.session.expire_all()
    world.advance(mission_id, 500)

    order = world.order()
    assert order.status == OrderStatus.OUT_FOR_DELIVERY  # interrupted, not failed at the door
    assert order.delivery_failed_at is None
    flight = world.flight(mission_id)
    assert flight.handover_failed_at is None and flight.phase == FlightPhase.EMERGENCY
    assert world.events() == []
    assert world.drone().status == DroneStatus.MAINTENANCE


def test_a_drone_failure_on_the_way_back_keeps_the_failed_delivery(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 25)

    result = trigger_drone_failure(world.session, at(25), world.settings, rng=random.Random(1))
    world.session.expire_all()
    world.advance(mission_id, 500)

    assert result.stage == FailureStage.HANDOVER_FAILED
    assert world.order().status == OrderStatus.DELIVERY_FAILED  # still a failed delivery
    assert world.drone().status == DroneStatus.MAINTENANCE
    assert world.flight(mission_id).phase == FlightPhase.EMERGENCY


# --- visibility and history ------------------------------------------------------------------


def test_a_failed_delivery_stays_in_history_and_leaves_the_active_views_after_the_window(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.mark(1)
    world.advance(mission_id, 25)
    failed_at = world.order().delivery_failed_at
    assert failed_at is not None

    def active_ids(seconds: float) -> list[str]:
        window = world.settings.order_delivered_visibility_seconds
        return [o.id for o in repository.list_active_orders(world.session, at(seconds), window)]

    assert ORDER in active_ids(25 + 119)
    assert ORDER not in active_ids(25 + 120)
    assert ORDER in [o.id for o in repository.list_orders(world.session)]  # full history


# --- API -------------------------------------------------------------------------------------


def test_the_endpoint_reports_the_pending_outcome_and_the_apis_expose_the_new_fields(
    client: TestClient, world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    monkeypatch.setattr(clock, "utcnow", lambda: at(8))

    response = client.post("/api/incidents/recipient-unavailable")

    assert response.status_code == 200
    body = response.json()
    assert (body["drone_id"], body["mission_id"], body["order_id"]) == (DRONE, mission_id, ORDER)
    assert "attempt_at" in body
    flight = next(f for f in client.get("/api/flights").json()["flights"] if f["order_id"] == ORDER)
    assert flight["recipient_unavailable_at"] is not None
    assert flight["handover_failed_at"] is None
    order = client.get(f"/api/orders/{ORDER}").json()
    assert order["status"] == "OUT_FOR_DELIVERY" and order["delivery_failed_at"] is None
