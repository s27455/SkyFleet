"""LPR helicopter scenario and its effect on flights (Feature 018E) on SQLite, controlled clock."""

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
from app.simulation import engine, lpr
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import trigger_drone_failure
from app.simulation.flight import LegKind, leg_from_dict, state_at
from app.simulation.models import (
    EmergencyReason,
    FlightPhase,
    LprScenario,
    LprStatus,
    MissionFlight,
)

Launch = Callable[..., str]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
# ORD-003 starts at Galeria Bałtycka (18.6007, 54.3826) and delivers 1.2 km north-east of it, into
# the helicopter's corridor (the route runs along latitude 54.3925). ORD-001 delivers to the south.
ORDER, DRONE = "ORD-003", "DRN-011"
SOUTH_ORDER, SOUTH_DRONE = "ORD-001", "DRN-010"
CORRIDOR_LONGITUDE = 18.606  # where the helicopter is when it passes the delivery


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def over_hub_at(seconds: float, settings: Settings) -> datetime:
    """The start of a scenario whose helicopter is at the delivery `seconds` into the flight."""
    share = (CORRIDOR_LONGITUDE - lpr.ROUTE_START[0]) / (lpr.ROUTE_END[0] - lpr.ROUTE_START[0])
    return at(seconds) - timedelta(seconds=share * lpr.route_length_m() / settings.sim_lpr_speed_ms)


class World:
    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def start_lpr(self, started: datetime, origin: EventOrigin = EventOrigin.MANUAL) -> lpr.Zone:
        row = lpr.start_scenario(self.session, started, self.settings, origin=origin)
        zone = lpr.zone_of(row)
        self.session.expire_all()
        return zone

    def advance(self, mission_id: str, seconds: float) -> None:
        engine.advance_flight(self.factory, self.settings, mission_id, at(seconds))
        self.session.expire_all()

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

    def holds(self, mission_id: str) -> list[tuple[float, float]]:
        legs = [leg_from_dict(entry) for entry in self.flight(mission_id).legs]
        return [(leg.start_s, leg.end_s) for leg in legs if leg.kind == LegKind.HOLD]

    def events(self, order_id: str = ORDER, kind: str = "LPR_TRANSIT") -> list[OperationalEvent]:
        found = event_repository.list_events(self.session, order_id=order_id)
        return [event for event in found if event.event_type == kind]

    def scenario_events(self) -> list[OperationalEvent]:
        rows = self.session.scalars(
            select(OperationalEvent).where(OperationalEvent.event_type == "LPR_TRANSIT")
        )
        return [event for event in rows if event.order_id is None]

    def flown(
        self, mission_id: str, zone: lpr.Zone, until: float, tick: float = 1.0
    ) -> list[float]:
        """Advance tick by tick; the distance (m) between the drone and the helicopter at each."""
        gaps: list[float] = []
        seconds = 0.0
        while seconds <= until:
            self.advance(mission_id, seconds)
            flight = self.flight(mission_id)
            drone_at = (flight.longitude, flight.latitude)
            gaps.append(distance_km(drone_at, lpr.helicopter_position(zone, at(seconds))) * 1000)
            seconds += tick
        return gaps


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


# --- the scenario lifecycle ---------------------------------------------------------------------


def test_starting_a_scenario_stores_it_once_with_its_parameters(world: World) -> None:
    zone = world.start_lpr(NOW)

    row = world.session.get(LprScenario, zone.scenario_id)
    assert row is not None and row.status == LprStatus.ACTIVE.value
    assert (row.speed_ms, row.radius_m, row.margin_m) == (80.0, 500.0, 250.0)
    assert as_utc(row.ends_at) - as_utc(row.started_at) == timedelta(seconds=zone.duration_s)
    (started,) = world.scenario_events()
    assert started.origin == "MANUAL" and started.details is not None
    assert started.details["phase"] == "STARTED"
    assert started.dedupe_key == f"LPR_TRANSIT:{zone.scenario_id}:STARTED"


def test_a_second_trigger_while_one_runs_changes_nothing(world: World) -> None:
    world.start_lpr(NOW)

    with pytest.raises(lpr.LprAlreadyActiveError):
        lpr.start_scenario(world.session, at(30), world.settings)

    assert len(world.session.scalars(select(LprScenario)).all()) == 1
    assert len(world.scenario_events()) == 1


def test_the_worker_completes_the_scenario_once_when_it_is_over(world: World) -> None:
    zone = world.start_lpr(NOW)

    assert lpr.complete_due(world.session, at(zone.duration_s - 1)) is False
    assert lpr.complete_due(world.session, at(zone.duration_s + 1)) is True
    assert lpr.complete_due(world.session, at(zone.duration_s + 2)) is False  # idempotent

    row = world.session.get(LprScenario, zone.scenario_id)
    assert row is not None and row.status == LprStatus.COMPLETED.value
    phases = sorted(event.details["phase"] for event in world.scenario_events() if event.details)
    assert phases == ["COMPLETED", "STARTED"]  # the lifecycle, once each
    assert lpr.active_zone(world.session, at(zone.duration_s + 2)) is None


def test_a_finished_scenario_does_not_block_a_new_one_even_if_the_worker_missed_it(
    world: World,
) -> None:
    first = world.start_lpr(NOW)

    second = lpr.start_scenario(world.session, at(first.duration_s + 60), world.settings)

    assert second.id != first.scenario_id
    rows = {row.id: row.status for row in world.session.scalars(select(LprScenario))}
    assert rows == {first.scenario_id: "COMPLETED", second.id: "ACTIVE"}


def test_the_zone_ends_by_the_clock_even_if_the_worker_never_completed_it(world: World) -> None:
    zone = world.start_lpr(NOW)

    assert lpr.active_zone(world.session, at(zone.duration_s - 1)) is not None
    assert lpr.active_zone(world.session, at(zone.duration_s + 1)) is None  # no stale zone


def test_the_state_is_in_the_database_not_in_the_process(
    world: World, session_factory: sessionmaker[Session]
) -> None:
    zone = world.start_lpr(NOW)

    with session_factory() as other:  # a different session, as after an API or worker restart
        again = lpr.active_zone(other, at(10))
    assert again == zone


def test_the_helicopter_follows_its_route_at_a_constant_speed(world: World) -> None:
    zone = world.start_lpr(NOW)

    assert lpr.helicopter_position(zone, at(0)) == pytest.approx(lpr.ROUTE_START)
    moved = distance_km(lpr.ROUTE_START, lpr.helicopter_position(zone, at(10))) * 1000
    assert moved == pytest.approx(10 * 80.0, rel=0.01)
    assert lpr.helicopter_position(zone, at(zone.duration_s + 50)) == pytest.approx(lpr.ROUTE_END)


# --- API ----------------------------------------------------------------------------------------


def test_the_endpoint_starts_one_scenario_and_refuses_a_second(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: at(0))

    first = client.post("/api/incidents/lpr-helicopter")
    second = client.post("/api/incidents/lpr-helicopter")

    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "ACTIVE" and body["radius_m"] == 500.0 and body["origin"] == "MANUAL"
    assert body["position"] == pytest.approx(list(lpr.ROUTE_START))
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "LPR_ALREADY_ACTIVE"


def test_the_status_endpoint_shows_the_moving_helicopter_or_nothing(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clock, "utcnow", lambda: at(0))
    assert client.get("/api/incidents/lpr").json()["scenario"] is None
    client.post("/api/incidents/lpr-helicopter")

    monkeypatch.setattr(clock, "utcnow", lambda: at(20))
    moving = client.get("/api/incidents/lpr").json()["scenario"]
    monkeypatch.setattr(clock, "utcnow", lambda: at(500))
    over = client.get("/api/incidents/lpr").json()["scenario"]

    assert moving is not None and moving["position"][0] > lpr.ROUTE_START[0]
    assert over is None  # the zone is gone once the pass is over


# --- drones yield ---------------------------------------------------------------------------------


def test_a_drone_in_the_way_stands_still_outside_the_zone_and_then_delivers(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))

    gaps = world.flown(mission_id, zone, 120)

    holds = world.holds(mission_id)
    assert len(holds) >= 1  # it did yield
    assert min(gaps) >= zone.radius_m  # and was never inside the drawn zone at any tick
    assert world.order().status == OrderStatus.DELIVERED  # the delivery still happens
    assert world.flight(mission_id).phase == FlightPhase.LANDED  # and the flight lands normally
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.drone().status == DroneStatus.IDLE


def test_yielding_delays_the_schedule_but_never_moves_the_drone(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    before = [leg_from_dict(entry) for entry in world.flight(mission_id).legs]
    zone = world.start_lpr(over_hub_at(8, world.settings))

    world.flown(mission_id, zone, 120)

    after = [leg_from_dict(entry) for entry in world.flight(mission_id).legs]
    waited = sum(end - start for start, end in world.holds(mission_id))
    assert waited > 0
    assert after[-1].end_s == pytest.approx(before[-1].end_s + waited)  # later, by what it waited
    assert after[-1].target == before[-1].target  # same landing point
    stops = [leg for leg in after if leg.kind == LegKind.DELIVERY]
    assert stops[-1].end_s == pytest.approx(before[1].end_s + waited)  # the handover waited too
    assert world.flight(mission_id).delivered_at is not None


def test_holding_costs_battery_explicitly(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))
    world.flown(mission_id, zone, 120)
    flight = world.flight(mission_id)
    legs = [leg_from_dict(entry) for entry in flight.legs]
    empty, loaded = consumption_rates(
        weight_kg=world.order().package_weight_kg,
        model=world.drone().model,
        payload_energy_factor=world.settings.mission_payload_energy_factor,
    )
    kwargs = {"start_battery": flight.start_battery_pct, "empty_rate": empty, "loaded_rate": loaded}
    without = [leg for leg in legs if leg.kind != LegKind.HOLD]

    drained_extra = state_at(without, without[-1].end_s, **kwargs).battery_pct - flight.battery_pct

    expected = sum(
        leg.distance_km * (loaded if leg.loaded else empty)
        for leg in legs
        if leg.kind == LegKind.HOLD
    )
    assert expected > 0
    assert drained_extra == pytest.approx(expected, rel=0.02)


def test_a_drone_not_in_the_way_is_untouched(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    planned = list(world.flight(mission_id).legs)
    zone = world.start_lpr(over_hub_at(200, world.settings))  # the helicopter comes long after

    gaps = world.flown(mission_id, zone, 120)

    assert world.holds(mission_id) == []
    assert min(gaps) > zone.hold_threshold_m
    assert world.flight(mission_id).phase == FlightPhase.LANDED
    assert [leg_from_dict(e).kind for e in world.flight(mission_id).legs] == [
        leg_from_dict(e).kind for e in planned
    ]
    assert world.events() == []


def test_a_drone_going_elsewhere_flies_on_while_another_one_yields(
    world: World, launch: Launch
) -> None:
    north = launch(ORDER, DRONE)
    south = launch(SOUTH_ORDER, SOUTH_DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))
    south_planned = [leg_from_dict(e) for e in world.flight(south).legs]

    for seconds in range(0, 140):
        world.advance(north, seconds)
        world.advance(south, seconds)

    assert world.holds(north)  # the drone heading into the corridor yielded
    assert world.holds(south) == []  # the one heading south did not
    after = [leg_from_dict(e) for e in world.flight(south).legs]
    assert [(leg.kind, leg.start_s, leg.end_s) for leg in after] == [
        (leg.kind, leg.start_s, leg.end_s) for leg in south_planned
    ]  # on its original schedule, to the second
    assert world.order(SOUTH_ORDER).status == OrderStatus.DELIVERED
    assert zone.scenario_id


@pytest.mark.parametrize("tick", [1.0, 4.0])
def test_a_slow_worker_still_keeps_the_drone_out_of_the_zone(
    world: World, launch: Launch, tick: float
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))

    gaps = world.flown(mission_id, zone, 160, tick=tick)

    assert world.holds(mission_id)
    assert min(gaps) >= zone.radius_m  # the look-ahead grows with the tick spacing


def test_a_hold_is_inserted_once_however_often_the_worker_ticks(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))

    world.flown(mission_id, zone, 120, tick=0.25)  # four ticks per second

    holds = world.holds(mission_id)
    assert 1 <= len(holds) <= 2  # one pass of the zone, not one hold per tick
    ordered = sorted(holds)
    assert all(ordered[i][1] <= ordered[i + 1][0] + 1e-6 for i in range(len(ordered) - 1))


def test_the_first_yield_of_each_mission_is_recorded_once_in_its_activity(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings), origin=EventOrigin.AUTOMATIC)

    world.flown(mission_id, zone, 120)

    (event,) = world.events()
    assert (event.mission_id, event.drone_id, event.flight_id) == (mission_id, DRONE, mission_id)
    assert event.origin == "AUTOMATIC"  # the scenario's origin, not invented
    assert event.details is not None and event.details["phase"] == "YIELDED"
    assert event.dedupe_key == f"LPR_TRANSIT:{zone.scenario_id}:YIELDED:{mission_id}"


def test_the_flights_api_says_which_drone_is_yielding(
    client: TestClient, world: World, launch: Launch, monkeypatch: pytest.MonkeyPatch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))
    world.flown(mission_id, zone, 4)
    start, end = world.holds(mission_id)[0]

    def yielding(seconds: float) -> bool:
        monkeypatch.setattr(clock, "utcnow", lambda: at(seconds))
        flights = client.get("/api/flights").json()["flights"]
        flight = next(f for f in flights if f["mission_id"] == mission_id)
        return bool(flight["yielding_to_lpr"])

    assert yielding(start - 0.5) is False
    assert yielding((start + end) / 2) is True
    assert yielding(end + 0.5) is False  # resumed: the normal label returns


# --- when the drone cannot afford to wait ---------------------------------------------------------


def test_a_drone_that_cannot_afford_the_hold_makes_a_battery_emergency_outside_the_zone(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    flight = world.flight(mission_id)
    empty, loaded = consumption_rates(
        weight_kg=world.order().package_weight_kg,
        model=world.drone().model,
        payload_energy_factor=sim_settings.mission_payload_energy_factor,
    )
    legs = [leg_from_dict(entry) for entry in flight.legs]
    end_battery = state_at(
        legs,
        legs[-1].end_s,
        start_battery=flight.start_battery_pct,
        empty_rate=empty,
        loaded_rate=loaded,
    ).battery_pct
    # The flight is fine on its own, but one second of waiting more than it can spare is not.
    world.settings = sim_settings.model_copy(update={"sim_critical_battery_pct": end_battery - 0.2})
    zone = world.start_lpr(over_hub_at(8, world.settings))

    gaps = world.flown(mission_id, zone, 40)

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY  # the existing emergency, no new workflow
    assert flight.emergency_reason == EmergencyReason.BATTERY_CRITICAL.value
    assert world.holds(mission_id) == []  # it did not wait, and did not fly on
    assert min(gaps) >= zone.radius_m  # and it never entered the zone
    assert world.drone().status == DroneStatus.MAINTENANCE
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    order = world.order()
    assert order.status == OrderStatus.OUT_FOR_DELIVERY and order.delivered_at is None


def test_that_interrupted_order_leaves_the_active_views_after_the_window(
    world: World, launch: Launch, sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    flight = world.flight(mission_id)
    empty, loaded = consumption_rates(
        weight_kg=world.order().package_weight_kg,
        model=world.drone().model,
        payload_energy_factor=sim_settings.mission_payload_energy_factor,
    )
    legs = [leg_from_dict(entry) for entry in flight.legs]
    end_battery = state_at(
        legs,
        legs[-1].end_s,
        start_battery=flight.start_battery_pct,
        empty_rate=empty,
        loaded_rate=loaded,
    ).battery_pct
    world.settings = sim_settings.model_copy(update={"sim_critical_battery_pct": end_battery - 0.2})
    zone = world.start_lpr(over_hub_at(8, world.settings))
    world.flown(mission_id, zone, 40)
    ended = as_utc(world.flight(mission_id).ended_at or NOW)
    window = world.settings.order_delivered_visibility_seconds

    def active(moment: datetime) -> list[str]:
        return [o.id for o in repository.list_active_orders(world.session, moment, window)]

    assert ORDER in active(ended + timedelta(seconds=window - 1))
    assert ORDER not in active(ended + timedelta(seconds=window))
    assert ORDER in [o.id for o in repository.list_orders(world.session)]  # the history keeps it


# --- overlap with 018B, 018C and 018D -----------------------------------------------------------


def test_a_recall_during_a_hold_respects_the_zone_and_returns_loaded(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))
    world.flown(mission_id, zone, 4)
    start, end = world.holds(mission_id)[0]
    middle = (start + end) / 2
    world.flown(mission_id, zone, middle)  # now standing in the hold

    cancellation.cancel_order(world.session, ORDER, at(middle), world.settings)
    world.session.expire_all()
    gaps = [
        distance_km(
            (world.flight(mission_id).longitude, world.flight(mission_id).latitude),
            lpr.helicopter_position(zone, at(middle)),
        )
        * 1000
    ]
    tail = middle
    while tail < 200:
        tail += 1.0
        world.advance(mission_id, tail)
        flight = world.flight(mission_id)
        gaps.append(
            distance_km(
                (flight.longitude, flight.latitude), lpr.helicopter_position(zone, at(tail))
            )
            * 1000
        )

    assert min(gaps) >= zone.radius_m  # the recalled drone never entered the zone either
    flight = world.flight(mission_id)
    assert flight.recalled_at is not None and flight.phase == FlightPhase.LANDED
    assert world.order().status == OrderStatus.CANCELLED  # the cancellation's outcome is intact
    assert world.order().delivered_at is None


def test_a_drone_failure_overrides_the_yield_and_never_resumes(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    zone = world.start_lpr(over_hub_at(8, world.settings))
    world.flown(mission_id, zone, 4)
    start, end = world.holds(mission_id)[0]
    middle = (start + end) / 2
    world.flown(mission_id, zone, middle)

    trigger_drone_failure(world.session, at(middle), world.settings, rng=random.Random(1))
    world.session.expire_all()
    for seconds in range(int(middle) + 1, 200):
        world.advance(mission_id, seconds)

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY and flight.emergency_reason == "DRONE_FAILURE"
    assert world.drone().status == DroneStatus.MAINTENANCE  # the zone clearing did not revive it
    assert world.order().status == OrderStatus.OUT_FOR_DELIVERY
    assert zone.scenario_id  # the scenario itself carried on without it


def test_a_failing_drone_is_never_held_by_the_zone(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 2)
    trigger_drone_failure(world.session, at(2), world.settings, rng=random.Random(1))
    world.session.expire_all()
    zone = world.start_lpr(over_hub_at(8, world.settings))

    for seconds in range(3, 40):
        world.advance(mission_id, seconds)

    assert world.holds(mission_id) == []  # it lands where it was going to, ignoring the zone
    assert world.flight(mission_id).phase == FlightPhase.EMERGENCY
    assert zone.scenario_id


def test_a_pending_recipient_unavailable_cannot_fail_before_the_drone_arrives(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    original_stop = [leg_from_dict(e) for e in world.flight(mission_id).legs][1].end_s
    trigger_recipient_unavailable(world.session, at(1), world.settings, rng=random.Random(1))
    world.session.expire_all()
    zone = world.start_lpr(over_hub_at(8, world.settings))

    world.flown(mission_id, zone, original_stop + 1)  # past when it would have failed

    waited = sum(end - start for start, end in world.holds(mission_id))
    assert waited > 0
    assert world.order().status == OrderStatus.OUT_FOR_DELIVERY  # not before it arrives

    world.flown(mission_id, zone, 200)
    order = world.order()
    assert order.status == OrderStatus.DELIVERY_FAILED and order.delivered_at is None
    assert world.flight(mission_id).phase == FlightPhase.LANDED
    (failed,) = world.events(kind="RECIPIENT_UNAVAILABLE")
    assert failed.origin == "MANUAL"


def test_a_loaded_failed_delivery_return_yields_and_keeps_its_outcome(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    trigger_recipient_unavailable(world.session, at(1), world.settings, rng=random.Random(1))
    world.session.expire_all()
    # The helicopter arrives while the drone, still inside the corridor at the delivery address,
    # starts its loaded return. It cannot leave in time, so it stands still where it is (the one
    # case where the zone passes over a drone: nothing better exists for a drone that cannot leave).
    world.start_lpr(over_hub_at(30, world.settings))

    for seconds in range(0, 200):
        world.advance(mission_id, seconds)

    legs = [leg_from_dict(entry) for entry in world.flight(mission_id).legs]
    holds = [leg for leg in legs if leg.kind == LegKind.HOLD]
    assert holds and all(leg.loaded for leg in holds)  # it waits with the parcel on board
    assert world.order().status == OrderStatus.DELIVERY_FAILED  # unchanged by the yield
    assert world.order().delivered_at is None
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED and flight.handover_failed_at is not None
    assert world.drone().status == DroneStatus.IDLE
    assert world.drone().hub_id == flight.landed_hub_id  # the hub changes on landing only
