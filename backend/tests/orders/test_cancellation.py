"""Order cancellation and drone recall (Feature 018B) on SQLite with a controlled clock."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events import repository as event_repository
from app.events.models import OperationalEvent
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionStatus
from app.missions.routing import hub_point, hubs_by_distance
from app.orders import cancellation, repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.service import OrderNotFoundError
from app.simulation import engine
from app.simulation.flight import LegKind, leg_from_dict
from app.simulation.models import EmergencyReason, FlightPhase, MissionFlight

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
# ORD-001 (0.8 kg) starts at Galeria Bałtycka, where DRN-010..012 are docked: about 36 s in total,
# the outbound leg ends at about 16.4 s and the parcel is handed over at about 19.4 s.
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

    def cancel(self, order_id: str, seconds: float = 0.0) -> DeliveryOrder:
        order = cancellation.cancel_order(self.session, order_id, at(seconds), self.settings)
        self.session.expire_all()
        return order

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

    def events(self, order_id: str) -> list[OperationalEvent]:
        return list(event_repository.list_events(self.session, order_id=order_id))


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


# --- before takeoff -------------------------------------------------------------------------


def test_an_unassigned_order_is_cancelled_with_one_manual_event(world: World) -> None:
    order = world.cancel("ORD-002", 5)

    assert order.status == OrderStatus.CANCELLED
    assert order.cancelled_at is not None and order.delivered_at is None
    (event,) = world.events("ORD-002")
    assert (event.event_type, event.origin) == ("ORDER_CANCELLED", "MANUAL")
    assert event.mission_id is None and event.drone_id is None
    assert event.occurred_at.replace(tzinfo=UTC) == at(5)


def test_a_cancelled_order_can_no_longer_be_planned_or_dispatched(
    world: World, sim_settings: Settings
) -> None:
    world.cancel("ORD-002")

    plan = missions_service.preview_plan(world.session, "ORD-002", "DRN-010", sim_settings)

    assert plan.eligible is False
    assert repository.count_ready_orders(world.session) == 10  # 11 seeded, one cancelled


def test_an_assigned_order_cancels_its_mission_and_leaves_the_drone_alone(
    world: World, sim_settings: Settings
) -> None:
    mission = missions_service.confirm_mission(world.session, ORDER, DRONE, sim_settings)
    before = world.drone(DRONE).hub_id

    order = world.cancel(ORDER)

    assert order.status == OrderStatus.CANCELLED
    assert world.mission(mission.id).status == MissionStatus.CANCELLED
    drone = world.drone(DRONE)
    assert (drone.status, drone.hub_id) == (DroneStatus.IDLE, before)
    assert world.session.get(MissionFlight, mission.id) is None  # no fictitious flight
    (event,) = world.events(ORDER)
    assert (event.mission_id, event.drone_id) == (mission.id, DRONE)


def test_the_drone_of_a_cancelled_assignment_can_take_another_order(
    world: World, sim_settings: Settings
) -> None:
    missions_service.confirm_mission(world.session, ORDER, DRONE, sim_settings)
    world.cancel(ORDER)

    again = missions_service.confirm_mission(world.session, "ORD-002", DRONE, sim_settings)

    assert again.status == MissionStatus.ASSIGNED


# --- idempotency and rejection --------------------------------------------------------------


def test_cancelling_twice_gives_one_event_and_one_cancellation_time(world: World) -> None:
    first = world.cancel("ORD-002", 5)
    stamped = first.cancelled_at

    second = world.cancel("ORD-002", 50)

    assert second.status == OrderStatus.CANCELLED and second.cancelled_at == stamped
    assert len(world.events("ORD-002")) == 1


def test_repeated_cancellation_in_flight_recalls_exactly_once(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.cancel(ORDER, 8)
    legs = world.flight(mission_id).legs
    recalled_at = world.flight(mission_id).recalled_at

    world.cancel(ORDER, 9)

    assert world.flight(mission_id).legs == legs
    assert world.flight(mission_id).recalled_at == recalled_at
    assert len(world.events(ORDER)) == 1  # seeded orders have no ORDER_CREATED event


def test_a_delivered_order_cannot_be_cancelled(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 25)  # the parcel was handed over at about 19.4 s
    assert world.order(ORDER).status == OrderStatus.DELIVERED

    with pytest.raises(cancellation.OrderAlreadyDeliveredError):
        world.cancel(ORDER, 25)

    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert world.order(ORDER).cancelled_at is None
    assert world.events(ORDER) == []


def test_cancelling_after_the_delivery_time_is_rejected_even_before_the_next_tick(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)

    with pytest.raises(cancellation.OrderAlreadyDeliveredError):
        world.cancel(ORDER, 20)  # past the delivery stop, the worker has not ticked yet

    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.flight(mission_id).recalled_at is None
    assert world.events(ORDER) == []


def test_an_unknown_order_is_not_found(world: World) -> None:
    with pytest.raises(OrderNotFoundError):
        world.cancel("ORD-999")


# --- recall ---------------------------------------------------------------------------------


def test_cancelling_in_flight_recalls_the_drone_with_its_parcel_without_teleporting(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    flight = world.flight(mission_id)
    position, battery = (flight.longitude, flight.latitude), flight.battery_pct
    hub_before = world.drone(DRONE).hub_id

    order = world.cancel(ORDER, 8)

    assert order.status == OrderStatus.CANCELLED
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT  # until it lands
    flight = world.flight(mission_id)
    assert flight.recalled_at is not None
    assert flight.phase == FlightPhase.RETURNING
    assert (flight.longitude, flight.latitude) == pytest.approx(position)  # no teleport
    assert flight.battery_pct == pytest.approx(battery)  # no reset
    recall = leg_from_dict(flight.legs[-1])
    assert recall.kind == LegKind.RECALL and recall.loaded is True
    assert len(flight.legs) == 2  # the cut outbound leg and exactly one recall leg
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.IN_FLIGHT and drone.hub_id == hub_before
    nearest = hubs_by_distance(position, list(world.session.scalars(select(Hub))))[0][0]
    assert flight.landing_target_hub_id == nearest.id
    (event,) = world.events(ORDER)
    assert event.event_type == "ORDER_CANCELLED"
    assert (event.mission_id, event.flight_id, event.drone_id) == (mission_id, mission_id, DRONE)
    assert event.details == {"recall_hub_id": nearest.id}


def test_the_recalled_drone_never_delivers_and_lands_loaded_at_the_hub(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.cancel(ORDER, 8)

    world.advance(mission_id, 25)  # beyond the original delivery time

    assert world.order(ORDER).status == OrderStatus.CANCELLED
    assert world.order(ORDER).delivered_at is None
    assert world.flight(mission_id).delivered_at is None

    world.advance(mission_id, 500)

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED and flight.landed_hub_id is not None
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.IDLE
    assert drone.hub_id == flight.landed_hub_id  # the Hub association changes only on landing
    hub = world.session.get(Hub, flight.landed_hub_id)
    assert hub is not None and (drone.longitude, drone.latitude) == hub_point(hub)
    assert world.order(ORDER).status == OrderStatus.CANCELLED


def test_the_recall_consumes_battery_at_the_loaded_rate(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.cancel(ORDER, 8)
    world.advance(mission_id, 500)

    flight = world.flight(mission_id)
    drone = world.drone(DRONE)
    _, loaded = consumption_rates(
        weight_kg=world.order(ORDER).package_weight_kg,
        model=drone.model,
        payload_energy_factor=sim_settings.mission_payload_energy_factor,
    )
    legs = [leg_from_dict(entry) for entry in flight.legs]
    assert all(leg.loaded for leg in legs)  # the parcel never left the drone
    expected = flight.start_battery_pct - loaded * sum(leg.distance_km for leg in legs)
    assert flight.battery_pct == pytest.approx(expected)
    assert drone.battery_pct == engine.rounded_pct(expected)


def test_recalling_during_the_delivery_stop_returns_from_the_destination(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 18)  # inside the delivery stop (16.4 s to 19.4 s)

    world.cancel(ORDER, 18)

    flight = world.flight(mission_id)
    order = world.order(ORDER)
    assert flight.recalled_at is not None and order.status == OrderStatus.CANCELLED
    destination = (order.destination_longitude, order.destination_latitude)
    assert (flight.longitude, flight.latitude) == pytest.approx(destination)
    world.advance(mission_id, 500)
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.order(ORDER).status == OrderStatus.CANCELLED


def test_a_full_recall_hub_diverts_the_loaded_drone_to_another_hub(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.cancel(ORDER, 8)
    target = world.flight(mission_id).landing_target_hub_id
    world.session.execute(
        update(Hub)
        .where(Hub.id == target)
        .values(
            drone_capacity=sum(
                1
                for d in world.session.scalars(select(Drone))
                if d.hub_id == target and d.status != DroneStatus.IN_FLIGHT
            )
        )
    )
    world.session.commit()

    world.advance(mission_id, 500)

    flight = world.flight(mission_id)
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert flight.landed_hub_id != target
    diversion = [leg_from_dict(entry) for entry in flight.legs if entry["kind"] == "DIVERSION"]
    assert len(diversion) == 1 and diversion[0].loaded is True  # still carrying the parcel
    assert world.order(ORDER).status == OrderStatus.CANCELLED


def test_a_recalled_flight_with_no_free_hub_ends_like_any_other_landing_failure(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.cancel(ORDER, 8)
    occupied: dict[str, int] = {}
    for drone in world.session.scalars(select(Drone)):
        if drone.status != DroneStatus.IN_FLIGHT:
            occupied[drone.hub_id] = occupied.get(drone.hub_id, 0) + 1
    for hub_id, count in occupied.items():
        world.session.execute(update(Hub).where(Hub.id == hub_id).values(drone_capacity=count))
    world.session.commit()

    world.advance(mission_id, 500)

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY
    assert flight.emergency_reason == EmergencyReason.NO_HUB_WITH_CAPACITY
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    assert world.order(ORDER).status == OrderStatus.CANCELLED  # cancellation is not undone


# --- independent drone state, defensive safeguards ------------------------------------------


def test_a_drone_that_is_not_flying_normally_is_not_recalled_and_stays_as_it_is(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.session.execute(
        update(Drone).where(Drone.id == DRONE).values(status=DroneStatus.MAINTENANCE.value)
    )
    world.session.commit()
    legs = world.flight(mission_id).legs

    with pytest.raises(cancellation.DroneNotRecallableError):
        world.cancel(ORDER, 8)

    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE  # not healed or overridden
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.flight(mission_id).legs == legs
    assert world.events(ORDER) == []


def test_without_a_reachable_hub_nothing_is_changed(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    world.settings = sim_settings.model_copy(update={"sim_critical_battery_pct": 100})
    legs = world.flight(mission_id).legs

    with pytest.raises(cancellation.RecallNotPossibleError):
        world.cancel(ORDER, 8)

    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.flight(mission_id).recalled_at is None
    assert world.flight(mission_id).legs == legs
    assert world.events(ORDER) == []


def test_a_failed_cancellation_leaves_no_partial_change(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("event failed")

    monkeypatch.setattr(cancellation, "append_event", boom)

    with pytest.raises(RuntimeError):
        world.cancel("ORD-002")
    monkeypatch.undo()

    assert world.order("ORD-002").status == OrderStatus.READY_FOR_PICKUP
    assert world.order("ORD-002").cancelled_at is None
    assert world.events("ORD-002") == []
    assert world.session.scalar(select(func.count()).select_from(OperationalEvent)) == 0


def test_the_planned_missions_remaining_flights_are_untouched_by_a_cancellation(
    world: World, launch: Launch
) -> None:
    first = launch(ORDER, DRONE)
    second = launch("ORD-004", "DRN-007")
    world.advance(first, 8)
    before = world.flight(second).legs

    world.cancel(ORDER, 8)

    assert world.flight(second).legs == before
    assert world.flight(second).recalled_at is None
    assert world.order("ORD-004").status == OrderStatus.OUT_FOR_DELIVERY


# --- API ------------------------------------------------------------------------------------


def test_the_cancel_endpoint_cancels_is_idempotent_and_reports_conflicts(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)

    first = client.post("/api/orders/ORD-002/cancel")
    second = client.post("/api/orders/ORD-002/cancel")
    unknown = client.post("/api/orders/ORD-999/cancel")

    assert first.status_code == 200 and first.json()["status"] == "CANCELLED"
    assert first.json()["cancelled_at"].startswith("2026-11-12T10:00:00")
    assert second.status_code == 200 and second.json()["status"] == "CANCELLED"
    # SQLite drops the zone on a fresh read, so compare the instants, not the suffix.
    assert second.json()["cancelled_at"][:19] == first.json()["cancelled_at"][:19]
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "ORDER_NOT_FOUND"
    events = client.get("/api/events", params={"order_id": "ORD-002"}).json()
    assert [e["event_type"] for e in events] == ["ORDER_CANCELLED"]


def test_the_endpoint_rejects_a_delivered_order_with_a_stable_code(
    client: TestClient, seeded: Session
) -> None:
    order = seeded.get(DeliveryOrder, "ORD-003")
    assert order is not None
    order.status = OrderStatus.DELIVERED.value
    seeded.commit()

    response = client.post("/api/orders/ORD-003/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_ALREADY_DELIVERED"
    assert client.get("/api/orders/ORD-003").json()["status"] == "DELIVERED"


def test_the_active_view_keeps_a_cancelled_order_for_the_window_and_history_forever(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)
    client.post("/api/orders/ORD-002/cancel")

    monkeypatch.setattr(clock, "utcnow", lambda: NOW + timedelta(seconds=119))
    inside = {o["id"] for o in client.get("/api/orders", params={"active": "true"}).json()}
    monkeypatch.setattr(clock, "utcnow", lambda: NOW + timedelta(seconds=121))
    outside = {o["id"] for o in client.get("/api/orders", params={"active": "true"}).json()}
    everything = {o["id"] for o in client.get("/api/orders").json()}

    assert "ORD-002" in inside and "ORD-002" not in outside and "ORD-002" in everything


def test_the_flights_api_reports_the_recall(
    client: TestClient, world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 8)
    monkeypatch.setattr(clock, "utcnow", lambda: at(8))

    assert client.post(f"/api/orders/{ORDER}/cancel").status_code == 200

    flights = client.get("/api/flights").json()["flights"]
    (flight,) = [f for f in flights if f["mission_id"] == mission_id]
    assert flight["recalled_at"] is not None and flight["phase"] == "RETURNING"
    assert flight["delivered_at"] is None
    assert flight["landing_target_hub_id"] == world.flight(mission_id).landing_target_hub_id


def test_technical_delete_still_refuses_a_cancelled_order(
    client: TestClient, seeded: Session
) -> None:
    client.post("/api/orders/ORD-002/cancel")

    response = client.delete("/api/orders/ORD-002")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ORDER_NOT_EDITABLE"
    assert len(client.get("/api/events", params={"order_id": "ORD-002"}).json()) == 1


def test_a_cancelled_order_is_not_recommended_for_dispatch(
    client: TestClient, seeded: Session
) -> None:
    assert "ORD-002" in str(client.get("/api/dispatch/recommendations").json())
    client.post("/api/orders/ORD-002/cancel")

    after = client.get("/api/dispatch/recommendations").json()

    assert "ORD-002" not in str(after)
