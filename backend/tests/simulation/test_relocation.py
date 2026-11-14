"""Manual drone relocation (Feature 019A) on SQLite with a controlled clock."""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.service import recommend_for_session
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, OperationalEvent
from app.hubs.models import Hub
from app.missions.models import Mission, MissionPurpose, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import distance_km, hub_point
from app.missions.service import DroneNotFoundError
from app.orders.models import DeliveryOrder
from app.simulation import engine, lpr
from app.simulation.failed_delivery import eligible_mission_ids as recipient_targets
from app.simulation.failure import FailureStage, trigger_drone_failure
from app.simulation.flight import LegKind, leg_from_dict
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import EmergencyReason, FlightPhase, MissionFlight
from app.simulation.relocation import (
    HubNotFoundError,
    RelocationRejectedError,
    preview_relocation,
    start_relocation,
)
from app.simulation.schemas import RelocationReasonCode
from app.simulation.service import WorkerUnavailableError

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
BALTYCKA, FORUM, OSOWA, RIVIERA = (
    "hub-galeria-baltycka",
    "hub-forum-gdansk",
    "hub-centrum-handlowe-osowa",
    "hub-centrum-riviera",
)
DRONE = "DRN-010"  # docked at Galeria Bałtycka, 100%


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


class World:
    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def relocate(self, drone: str = DRONE, destination: str = FORUM, now: datetime = NOW) -> str:
        record_heartbeat(self.session, now)
        mission = start_relocation(self.session, drone, destination, now, self.settings)
        self.session.expire_all()
        return mission.id

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

    def drone(self, drone_id: str = DRONE) -> Drone:
        drone = self.session.get(Drone, drone_id)
        assert drone is not None
        return drone

    def hub(self, hub_id: str) -> Hub:
        hub = self.session.get(Hub, hub_id)
        assert hub is not None
        return hub

    def end_s(self, mission_id: str) -> float:
        return leg_from_dict(self.flight(mission_id).legs[-1]).end_s

    def events(self, mission_id: str, kind: str = "DRONE_RELOCATION") -> list[OperationalEvent]:
        rows = self.session.scalars(
            select(OperationalEvent)
            .where(OperationalEvent.mission_id == mission_id, OperationalEvent.event_type == kind)
            .order_by(OperationalEvent.id)
        )
        return list(rows)

    def phases(self, mission_id: str) -> list[str]:
        return [str((e.details or {}).get("phase")) for e in self.events(mission_id)]


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


def reasons(error: RelocationRejectedError) -> set[RelocationReasonCode]:
    return {reason.code for reason in error.plan.reasons}


# --- eligibility and validation -----------------------------------------------------------------


def test_the_preview_is_read_only_and_reports_the_route(world: World) -> None:
    plan = preview_relocation(world.session, DRONE, FORUM, world.settings)

    assert plan.eligible and plan.reasons == []
    assert plan.origin_hub_id == BALTYCKA and plan.destination_hub_id == FORUM
    expected = distance_km(hub_point(world.hub(BALTYCKA)), hub_point(world.hub(FORUM)))
    assert plan.distance_km == pytest.approx(expected)
    assert plan.expected_battery_use_pct == pytest.approx(expected * 5.0)  # the empty rate
    assert world.session.scalars(select(Mission)).first() is None
    assert world.drone().status == DroneStatus.IDLE.value


def test_a_relocation_starts_an_order_less_mission_and_flight(world: World) -> None:
    orders_before = [(o.id, o.status) for o in world.session.scalars(select(DeliveryOrder))]

    mission_id = world.relocate()

    mission, flight, drone = world.mission(mission_id), world.flight(mission_id), world.drone()
    assert mission.purpose == MissionPurpose.RELOCATION.value and mission.order_id is None
    assert mission.status == MissionStatus.IN_FLIGHT.value
    assert (mission.origin_hub_id, mission.return_hub_id) == (BALTYCKA, FORUM)
    assert flight.phase == FlightPhase.RELOCATING.value
    assert [leg_from_dict(e).kind for e in flight.legs] == [LegKind.RELOCATE]
    assert (flight.planned_return_hub_id, flight.landing_target_hub_id) == (FORUM, FORUM)
    assert drone.status == DroneStatus.IN_FLIGHT.value and drone.hub_id == BALTYCKA
    started = world.events(mission_id)
    assert len(started) == 1 and started[0].details is not None
    assert started[0].details["phase"] == "STARTED"
    assert (started[0].origin, started[0].order_id) == (EventOrigin.MANUAL.value, None)
    assert [(o.id, o.status) for o in world.session.scalars(select(DeliveryOrder))] == orders_before


def _set_charging(world: World) -> None:
    world.drone().status = DroneStatus.CHARGING.value


def _set_maintenance(world: World) -> None:
    world.drone().status = DroneStatus.MAINTENANCE.value


def _set_low_battery(world: World) -> None:
    world.drone().battery_pct = 30


def _move_away(world: World) -> None:
    world.drone().longitude = 18.55


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        (_set_charging, RelocationReasonCode.DRONE_NOT_AVAILABLE),
        (_set_maintenance, RelocationReasonCode.DRONE_NOT_AVAILABLE),
        (_set_low_battery, RelocationReasonCode.INSUFFICIENT_BATTERY),
        (_move_away, RelocationReasonCode.DRONE_NOT_AT_HUB),
    ],
)
def test_an_ineligible_drone_is_rejected_and_nothing_is_written(
    world: World, setup: Callable[[World], None], code: RelocationReasonCode
) -> None:
    setup(world)
    world.session.commit()
    record_heartbeat(world.session, NOW)

    with pytest.raises(RelocationRejectedError) as error:
        start_relocation(world.session, DRONE, FORUM, NOW, world.settings)

    assert code in reasons(error.value)
    assert world.session.scalars(select(Mission)).first() is None
    assert world.session.scalars(select(OperationalEvent)).first() is None


def test_the_same_hub_is_rejected(world: World) -> None:
    record_heartbeat(world.session, NOW)
    with pytest.raises(RelocationRejectedError) as error:
        start_relocation(world.session, DRONE, BALTYCKA, NOW, world.settings)
    assert reasons(error.value) == {RelocationReasonCode.SAME_HUB}


def test_a_route_beyond_the_mission_budget_is_rejected(world: World) -> None:
    record_heartbeat(world.session, NOW)
    with pytest.raises(RelocationRejectedError) as error:
        start_relocation(world.session, DRONE, RIVIERA, NOW, world.settings)  # about 14.3 km
    assert RelocationReasonCode.ROUTE_TOO_LONG in reasons(error.value)


def test_a_full_destination_is_rejected_at_the_start(world: World) -> None:
    world.hub(FORUM).drone_capacity = 3  # Forum Gdańsk already has three docked drones
    world.session.commit()
    record_heartbeat(world.session, NOW)

    with pytest.raises(RelocationRejectedError) as error:
        start_relocation(world.session, DRONE, FORUM, NOW, world.settings)

    assert reasons(error.value) == {RelocationReasonCode.DESTINATION_FULL}


def test_an_unknown_drone_or_hub_is_not_found(world: World) -> None:
    record_heartbeat(world.session, NOW)
    with pytest.raises(DroneNotFoundError):
        start_relocation(world.session, "DRN-999", FORUM, NOW, world.settings)
    with pytest.raises(HubNotFoundError):
        start_relocation(world.session, DRONE, "hub-nowhere", NOW, world.settings)


def test_without_a_fresh_worker_heartbeat_nothing_starts(world: World) -> None:
    with pytest.raises(WorkerUnavailableError):
        start_relocation(world.session, DRONE, FORUM, NOW, world.settings)
    record_heartbeat(world.session, NOW - timedelta(seconds=60))
    with pytest.raises(WorkerUnavailableError):
        start_relocation(world.session, DRONE, FORUM, NOW, world.settings)
    assert world.session.scalars(select(Mission)).first() is None


def test_a_second_request_for_the_same_drone_creates_no_second_flight(world: World) -> None:
    world.relocate()

    with pytest.raises(RelocationRejectedError) as error:
        start_relocation(world.session, DRONE, OSOWA, NOW, world.settings)

    assert RelocationReasonCode.DRONE_ALREADY_ASSIGNED in reasons(error.value)
    assert len(list(world.session.scalars(select(Mission)))) == 1
    assert len(list(world.session.scalars(select(MissionFlight)))) == 1
    assert len(list(world.session.scalars(select(OperationalEvent)))) == 1


def test_a_relocating_drone_is_not_offered_to_dispatch(world: World) -> None:
    world.relocate()

    recommendation = recommend_for_session(world.session, world.settings)

    assert DRONE not in {item.drone_id for item in recommendation.recommendations}


# --- the flight ---------------------------------------------------------------------------------


def test_the_drone_flies_continuously_and_keeps_its_hub_until_it_lands(world: World) -> None:
    mission_id = world.relocate()
    end = world.end_s(mission_id)
    origin, target = world.hub(BALTYCKA), world.hub(FORUM)
    total_km = distance_km(hub_point(origin), hub_point(target))

    world.advance(mission_id, end / 2)

    flight, drone = world.flight(mission_id), world.drone()
    assert flight.phase == FlightPhase.RELOCATING.value
    assert drone.status == DroneStatus.IN_FLIGHT.value and drone.hub_id == BALTYCKA
    assert flight.progress == pytest.approx(0.5, abs=0.02)
    midpoint = (
        (origin.longitude + target.longitude) / 2,
        (origin.latitude + target.latitude) / 2,
    )
    assert distance_km((flight.longitude, flight.latitude), midpoint) < 0.05
    assert flight.battery_pct == pytest.approx(100.0 - total_km / 2 * 5.0, abs=0.1)
    assert world.phases(mission_id) == ["STARTED"]


def test_landing_docks_the_drone_at_the_destination_exactly_once(world: World) -> None:
    mission_id = world.relocate()
    end = world.end_s(mission_id)

    world.advance(mission_id, end + 5)
    world.advance(mission_id, end + 10)  # a later tick, or a restarted worker, repeats nothing

    drone, mission, flight = world.drone(), world.mission(mission_id), world.flight(mission_id)
    assert (drone.status, drone.hub_id) == (DroneStatus.IDLE.value, FORUM)
    assert (drone.longitude, drone.latitude) == hub_point(world.hub(FORUM))
    assert mission.status == MissionStatus.COMPLETED.value
    assert (flight.phase, flight.landed_hub_id) == (FlightPhase.LANDED.value, FORUM)
    assert drone.battery_pct < 100  # the empty-flight rate was spent
    assert world.phases(mission_id) == ["STARTED", "COMPLETED"]
    done = world.events(mission_id)[-1]
    assert done.details is not None and done.details["diverted"] is False
    assert done.order_id is None


def test_a_landed_drone_counts_at_the_destination_and_charges_normally(world: World) -> None:
    mission_id = world.relocate()
    world.advance(mission_id, world.end_s(mission_id) + 5)

    hubs = list(world.session.scalars(select(Hub)))
    occupancy = hub_occupancy(list(world.session.scalars(select(Drone))), hubs, 50)
    assert occupancy[FORUM] == 4 and occupancy[BALTYCKA] == 2  # the docked count follows the drone
    drone = world.drone()
    assert drone.status == DroneStatus.IDLE.value and drone.battery_pct < 100  # charging is next


def test_a_destination_that_fills_up_meanwhile_is_handled_by_the_landing_logic(
    world: World,
) -> None:
    mission_id = world.relocate()
    world.hub(FORUM).drone_capacity = 3  # the three docked drones now fill it
    world.session.commit()

    world.advance(mission_id, world.end_s(mission_id) + 300)  # the diversion leg is flown too

    drone, flight = world.drone(), world.flight(mission_id)
    assert drone.status == DroneStatus.IDLE.value and drone.hub_id != FORUM
    assert flight.landed_hub_id == drone.hub_id and FORUM in flight.tried_hub_ids
    done = world.events(mission_id)[-1]
    assert done.details is not None and done.details["diverted"] is True


def test_a_battery_emergency_during_a_relocation_is_recorded_once(world: World) -> None:
    mission_id = world.relocate()
    world.flight(mission_id).start_battery_pct = 20.0  # simulated drain: it cannot get there
    world.session.commit()

    world.advance(mission_id, world.end_s(mission_id) + 5)
    world.advance(mission_id, world.end_s(mission_id) + 6)

    flight, mission, drone = world.flight(mission_id), world.mission(mission_id), world.drone()
    assert flight.emergency_reason == EmergencyReason.BATTERY_CRITICAL.value
    assert mission.status == MissionStatus.EMERGENCY.value
    assert drone.status == DroneStatus.MAINTENANCE.value and drone.hub_id == BALTYCKA
    assert world.phases(mission_id) == ["STARTED", "EMERGENCY"]


# --- compatibility with the incidents -----------------------------------------------------------


def test_a_drone_failure_ends_the_relocation_without_assigning_the_destination(
    world: World,
) -> None:
    mission_id = world.relocate()
    elapsed = world.end_s(mission_id) / 3

    result = trigger_drone_failure(world.session, at(elapsed), world.settings, rng=random.Random(1))
    world.session.expire_all()

    assert (result.mission_id, result.order_id) == (mission_id, None)
    assert result.stage is FailureStage.RELOCATION
    world.advance(mission_id, world.end_s(mission_id) + 30)
    drone, mission, flight = world.drone(), world.mission(mission_id), world.flight(mission_id)
    assert drone.status == DroneStatus.MAINTENANCE.value and drone.hub_id == BALTYCKA
    assert mission.status == MissionStatus.EMERGENCY.value
    assert flight.emergency_reason == EmergencyReason.DRONE_FAILURE.value
    failure = world.events(mission_id, "DRONE_FAILURE")
    assert len(failure) == 1 and failure[0].order_id is None and failure[0].drone_id == DRONE


def test_a_relocation_is_not_a_target_for_a_failed_handover(world: World) -> None:
    world.relocate()

    assert recipient_targets(world.session) == []


def test_the_lpr_helicopter_holds_a_relocating_drone_like_any_other_flight(world: World) -> None:
    # Galeria Bałtycka -> Osowa crosses the helicopter's corridor (latitude 54.3925) early on.
    mission_id = world.relocate(destination=OSOWA)
    leg = leg_from_dict(world.flight(mission_id).legs[0])
    cross = (lpr.ROUTE_START[1] - leg.origin[1]) / (leg.target[1] - leg.origin[1])
    cross_s = cross * leg.duration_s
    cross_x = leg.origin[0] + cross * (leg.target[0] - leg.origin[0])
    share = (cross_x - lpr.ROUTE_START[0]) / (lpr.ROUTE_END[0] - lpr.ROUTE_START[0])
    start = at(cross_s) - timedelta(
        seconds=share * lpr.route_length_m() / world.settings.sim_lpr_speed_ms
    )
    lpr.start_scenario(world.session, start, world.settings, origin=EventOrigin.MANUAL)
    world.session.expire_all()

    seconds, held = 0.0, False
    while seconds <= leg.end_s + 400 and world.flight(mission_id).phase != "LANDED":
        world.advance(mission_id, seconds)
        flight = world.flight(mission_id)
        held = held or any(leg_from_dict(e).kind == LegKind.HOLD for e in flight.legs)
        if held and flight.phase != "LANDED":
            assert flight.phase == FlightPhase.RELOCATING.value  # a hold keeps the phase
        seconds += 1.0

    assert held, "the drone should have yielded"
    drone, flight = world.drone(), world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED.value and flight.ended_at is not None
    assert (drone.status, drone.hub_id) == (DroneStatus.IDLE.value, OSOWA)
    yielded = world.events(mission_id, "LPR_TRANSIT")
    assert len(yielded) == 1 and yielded[0].order_id is None
    assert world.mission(mission_id).status == MissionStatus.COMPLETED.value
