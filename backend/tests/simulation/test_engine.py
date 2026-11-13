"""The simulation engine on SQLite with a controlled clock (deterministic, no worker process)."""

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.missions.routing import distance_km, hub_point
from app.orders import repository as order_repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import engine
from app.simulation.charging import ChargingState, charge_step
from app.simulation.clock import as_utc
from app.simulation.flight import leg_from_dict
from app.simulation.heartbeat import last_heartbeat
from app.simulation.models import EmergencyReason, FlightPhase, MissionFlight

OrderFactory = Callable[..., DeliveryOrder]
Launch = Callable[..., str]

# The same instant as the `launch` fixture's default start time (tests/conftest.py).
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)

# ORD-001 (0.8 kg) starts at Galeria Bałtycka, where DRN-010..012 are docked, and flies about
# 1.37 km: 36 s in total; the delivery stop ends at about 19.4 s; landing is decided at 34 s.
ORDER, DRONE = "ORD-001", "DRN-010"
BALTYCKA, FORUM = "hub-galeria-baltycka", "hub-forum-gdansk"


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


class World:
    """Small helpers to read the database fresh after the engine has committed."""

    def __init__(self, session: Session, factory: sessionmaker[Session], settings: Settings):
        self.session, self.factory, self.settings = session, factory, settings

    def advance(self, mission_id: str, seconds: float, settings: Settings | None = None) -> None:
        engine.advance_flight(self.factory, settings or self.settings, mission_id, at(seconds))
        self.session.expire_all()

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

    def occupancy(self) -> Counter[str]:
        drones = self.session.scalars(select(Drone)).all()
        hubs = self.session.scalars(select(Hub)).all()
        return hub_occupancy(drones, hubs, self.settings.hub_dock_proximity_m)

    def set_capacity(self, capacities: dict[str, int]) -> None:
        for hub_id, capacity in capacities.items():
            self.session.execute(
                update(Hub).where(Hub.id == hub_id).values(drone_capacity=capacity)
            )
        self.session.commit()
        self.session.expire_all()

    def fill_every_other_hub(self) -> None:
        """Make every Hub except Bałtycka full, and leave Bałtycka one place short for a landing."""
        occupancy = self.occupancy()
        self.set_capacity(
            {hub_id: count for hub_id, count in occupancy.items() if hub_id != BALTYCKA}
        )


@pytest.fixture
def world(seeded: Session, session_factory: sessionmaker[Session], sim_settings: Settings) -> World:
    return World(seeded, session_factory, sim_settings)


# --- takeoff and normal flight --------------------------------------------------------------------


def test_takeoff_moves_mission_drone_and_order_and_frees_the_origin_place(
    world: World, launch: Launch
) -> None:
    before = world.occupancy()[BALTYCKA]

    mission_id = launch(ORDER, DRONE)
    world.session.expire_all()

    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT
    assert world.drone(DRONE).status == DroneStatus.IN_FLIGHT
    assert world.order(ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.OUTBOUND
    assert (flight.longitude, flight.latitude) == pytest.approx(
        hub_point(world.session.get(Hub, BALTYCKA))  # type: ignore[arg-type]
    )
    assert world.occupancy()[BALTYCKA] == before - 1  # the drone left the Hub's count at once
    assert flight.landing_target_hub_id == flight.planned_return_hub_id == BALTYCKA


def test_a_complete_mission_takes_between_30_and_90_seconds(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 500)

    flight = world.flight(mission_id)
    assert flight.ended_at is not None
    duration = (as_utc(flight.ended_at) - at(0)).total_seconds()
    assert 30 <= duration <= 90
    assert duration == pytest.approx(35.9, abs=0.2)  # a 1.37 km route


def test_in_flight_the_position_and_battery_follow_the_schedule(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    origin = hub_point(world.session.get(Hub, BALTYCKA))  # type: ignore[arg-type]
    order = world.order(ORDER)
    destination = (order.destination_longitude, order.destination_latitude)

    world.advance(mission_id, 8.0)  # about halfway through the 16.4 s outbound leg

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.OUTBOUND
    here = (flight.longitude, flight.latitude)
    assert 0.3 < distance_km(origin, here) / distance_km(origin, destination) < 0.7
    assert flight.battery_pct < 100
    assert 0 < flight.progress < 0.5
    assert flight.target_eta_s is not None and flight.target_eta_s > 0
    # The drone row mirrors the flight, so the fleet endpoint shows the flying drone.
    drone = world.drone(DRONE)
    assert (drone.longitude, drone.latitude) == pytest.approx(here)
    assert drone.battery_pct == round(flight.battery_pct)
    assert world.occupancy()[BALTYCKA] == 2  # a flying drone occupies no Hub


def test_the_order_is_delivered_before_the_drone_returns_and_the_mission_completes(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 21.0)  # past the delivery stop, still on the return leg

    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT
    assert world.drone(DRONE).status == DroneStatus.IN_FLIGHT
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.RETURNING
    assert flight.delivered_at is not None
    assert as_utc(world.order(ORDER).delivered_at) == at(21.0)  # type: ignore[arg-type]


def test_a_delivered_order_stays_in_the_active_list_for_the_window_after_the_engine_delivers_it(
    world: World, launch: Launch
) -> None:
    """Engine and active-orders query together (Feature 017A regression).

    A worker that set DELIVERED without `delivered_at` made every delivery vanish at once, because
    a delivered order without a delivery time is hidden. Each piece was tested alone; not this.
    """
    mission_id = launch(ORDER, DRONE)
    window = world.settings.order_delivered_visibility_seconds

    world.advance(mission_id, 21.0)

    delivered_at = as_utc(world.order(ORDER).delivered_at)  # type: ignore[arg-type]
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert delivered_at == at(21.0)

    def listed(moment: datetime) -> bool:
        active = order_repository.list_active_orders(world.session, moment, window)
        return ORDER in {order.id for order in active}

    assert listed(delivered_at)  # 0 s
    assert listed(delivered_at + timedelta(seconds=window - 1))  # 119 s
    assert not listed(delivered_at + timedelta(seconds=window))  # exactly 120 s
    assert not listed(delivered_at + timedelta(seconds=window + 1))


def test_the_order_delivery_time_is_the_actual_transition_not_the_flights_scheduled_instant(
    world: World, launch: Launch
) -> None:
    """The flight keeps its timeline timestamp; the order is stamped when the worker commits."""
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 21.0)

    order, flight = world.order(ORDER), world.flight(mission_id)
    scheduled = as_utc(flight.delivered_at)  # type: ignore[arg-type]
    assert scheduled < at(21.0)  # the parcel was due at about 19.4 s
    assert as_utc(order.delivered_at) == at(21.0)  # type: ignore[arg-type]


def test_a_late_worker_still_gives_the_full_window_from_the_moment_it_delivers(
    world: World, launch: Launch
) -> None:
    """A worker that was stopped past the whole window must not make the order vanish at once."""
    mission_id = launch(ORDER, DRONE)
    window = world.settings.order_delivered_visibility_seconds

    world.advance(mission_id, 500.0)  # the delivery was due at ~19 s; the worker only runs now

    order, flight = world.order(ORDER), world.flight(mission_id)
    assert as_utc(flight.delivered_at) < at(500.0 - window)  # type: ignore[arg-type]
    assert as_utc(order.delivered_at) == at(500.0)  # type: ignore[arg-type]
    active = order_repository.list_active_orders(world.session, at(500.0 + window - 1), window)
    assert ORDER in {o.id for o in active}  # visible at 119 s from the actual transition


def test_every_delivery_the_engine_records_has_a_delivery_time(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 60.0)  # delivered, returned and landed

    order = world.order(ORDER)
    assert order.status == OrderStatus.DELIVERED
    assert order.delivered_at is not None


def test_landing_docks_the_drone_completes_the_mission_and_keeps_the_order_delivered(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    mission = world.mission(mission_id)
    expected_energy = mission.expected_energy_pct

    world.advance(mission_id, 60.0)

    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.IDLE
    hub = world.session.get(Hub, BALTYCKA)
    assert hub is not None
    assert (drone.longitude, drone.latitude) == hub_point(hub)  # docked exactly at the Hub
    assert drone.battery_pct == round(100 - expected_energy)  # carried over, not recharged
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED
    assert flight.landed_hub_id == BALTYCKA == mission.origin_hub_id  # back at the origin Hub
    assert flight.battery_pct == pytest.approx(100 - expected_energy)
    assert world.occupancy()[BALTYCKA] == 3  # the drone counts again, now that it docked


def test_the_drone_can_fly_again_with_its_remaining_battery(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 60.0)

    plan = missions_service.preview_plan(world.session, "ORD-002", DRONE, world.settings)

    assert plan.energy.drone_battery_pct == 93  # the actual battery, not 100
    assert plan.eligible


def test_planning_after_takeoff_counts_the_flying_drone_nowhere(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 10.0)

    plan = missions_service.preview_plan(world.session, "ORD-002", "DRN-011", world.settings)

    assert {h.hub_id: h.docked_drones for h in plan.hub_occupancy}[BALTYCKA] == 2


# --- idempotency, catch-up and restart ------------------------------------------------------------


def test_running_the_same_tick_twice_changes_nothing_the_second_time(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 25.0)
    first = world.flight(mission_id)
    snapshot = (
        first.phase,
        first.delivered_at,
        first.battery_pct,
        first.longitude,
        first.updated_at,
    )

    world.advance(mission_id, 25.0)

    second = world.flight(mission_id)
    assert (
        second.phase,
        second.delivered_at,
        second.battery_pct,
        second.longitude,
        second.updated_at,
    ) == snapshot
    assert world.order(ORDER).status == OrderStatus.DELIVERED


def test_a_tick_after_a_long_downtime_applies_every_milestone_in_order(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)

    world.advance(mission_id, 10_000.0)  # the worker was down for hours

    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.LANDED
    assert flight.delivered_at is not None and flight.ended_at is not None
    assert flight.delivered_at < flight.ended_at  # delivery is recorded at its scheduled time


def test_progress_continues_from_the_stored_schedule_after_a_restart(
    world: World, launch: Launch, session_factory: sessionmaker[Session], sim_settings: Settings
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 5.0)
    early = world.flight(mission_id).progress

    # A "restarted" worker has no memory: a fresh session factory and a later clock reading.
    restarted = sessionmaker(bind=session_factory.kw["bind"], expire_on_commit=False)
    engine.advance_flight(restarted, sim_settings, mission_id, at(20.0))
    world.session.expire_all()

    later = world.flight(mission_id).progress
    assert later > early > 0  # neither reset to 0 nor invented
    assert later == pytest.approx(20.0 / 35.9, abs=0.03)


def test_a_step_records_the_heartbeat_and_advances_active_flights(
    world: World, launch: Launch, session_factory: sessionmaker[Session]
) -> None:
    mission_id = launch(ORDER, DRONE)

    advanced = engine.run_step(session_factory, world.settings, at(12.0))

    world.session.expire_all()
    assert advanced == 1
    assert last_heartbeat(world.session) == at(12.0)
    assert world.flight(mission_id).progress > 0


def test_a_landed_flight_is_not_processed_again(
    world: World, launch: Launch, session_factory: sessionmaker[Session]
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 60.0)

    assert engine.run_step(session_factory, world.settings, at(70.0)) == 0


# --- full planned Hub: diversion ------------------------------------------------------------------


def test_a_full_planned_hub_diverts_to_the_nearest_other_hub_with_a_place(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})  # DRN-011 and DRN-012 fill it while DRN-010 is away

    world.advance(mission_id, 34.7)  # just after the landing decision

    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.DIVERTING
    assert flight.landing_target_hub_id == FORUM  # the nearest other Hub, and it has room
    assert flight.planned_return_hub_id == BALTYCKA  # the plan itself is unchanged
    assert flight.tried_hub_ids == [BALTYCKA]
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT
    assert world.drone(DRONE).status == DroneStatus.IN_FLIGHT

    world.advance(mission_id, 500.0)

    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.flight(mission_id).landed_hub_id == FORUM
    forum = world.session.get(Hub, FORUM)
    assert forum is not None
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.IDLE
    assert (drone.longitude, drone.latitude) == hub_point(forum)
    assert world.occupancy()[FORUM] == 4
    assert world.occupancy()[BALTYCKA] == 2  # never above its capacity
    assert world.order(ORDER).status == OrderStatus.DELIVERED


def test_two_arrivals_for_the_last_place_never_overfill_the_hub(
    world: World, launch: Launch
) -> None:
    first = launch("ORD-001", "DRN-010")
    second = launch("ORD-002", "DRN-011")
    world.set_capacity({BALTYCKA: 2})  # only DRN-012 is docked, so exactly one place is free

    world.advance(first, 300.0)
    world.advance(second, 300.0)

    landed = {
        world.flight(first).landed_hub_id,
        world.flight(second).landed_hub_id,
    }
    assert landed == {BALTYCKA, FORUM}  # one took the last place, the other was diverted
    assert world.occupancy()[BALTYCKA] == 2
    assert all(count <= 50 for count in world.occupancy().values())
    for mission_id in (first, second):
        assert world.mission(mission_id).status == MissionStatus.COMPLETED


def test_no_place_is_reserved_for_a_flight_that_has_not_landed(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 3})  # one free place, which the flying drone does not hold

    world.advance(mission_id, 10.0)
    # Another drone takes the place while the first is still in the air.
    other = world.drone("DRN-001")
    other.longitude, other.latitude = hub_point(world.session.get(Hub, BALTYCKA))  # type: ignore[arg-type]
    world.session.commit()

    world.advance(mission_id, 34.7)

    assert world.flight(mission_id).landing_target_hub_id == FORUM  # the Hub was full on arrival


# --- emergencies ----------------------------------------------------------------------------------


def test_with_no_hub_available_the_flight_ends_in_a_simulated_emergency(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.fill_every_other_hub()

    world.advance(mission_id, 100.0)

    mission = world.mission(mission_id)
    assert mission.status == MissionStatus.EMERGENCY  # not COMPLETED
    flight = world.flight(mission_id)
    assert flight.phase == FlightPhase.EMERGENCY
    assert flight.emergency_reason == EmergencyReason.NO_HUB_WITH_CAPACITY
    assert flight.emergency_at is not None and flight.ended_at == flight.emergency_at
    drone = world.drone(DRONE)
    assert drone.status == DroneStatus.MAINTENANCE
    baltycka = world.session.get(Hub, BALTYCKA)
    assert baltycka is not None
    stop = (drone.longitude, drone.latitude)
    assert distance_km(stop, hub_point(baltycka)) * 1000 == pytest.approx(60.0, abs=1.0)
    assert (flight.longitude, flight.latitude) == pytest.approx(stop)
    # The parcel was handed over before the return: the order stays delivered.
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    # No Hub is overfilled and the emergency drone counts at none.
    occupancy = world.occupancy()
    assert occupancy[BALTYCKA] == 2 and occupancy[FORUM] == 3
    for hub in world.session.scalars(select(Hub)):
        assert occupancy[hub.id] <= hub.drone_capacity


def test_an_emergency_never_counts_toward_a_hub_even_inside_its_docking_radius(
    world: World, launch: Launch, make_order: OrderFactory
) -> None:
    # A destination 20 m from Bałtycka: the landing is decided at the destination, so an emergency
    # stops the drone inside the Hub's 50 m docking radius. MAINTENANCE must still not count.
    world.session.add(
        make_order(
            id="ORD-960",
            origin_hub_id=BALTYCKA,
            destination_longitude=18.6010034,
            destination_latitude=54.3826244,
            package_weight_kg=1.0,
        )
    )
    world.session.commit()
    mission_id = launch("ORD-960", DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.fill_every_other_hub()

    world.advance(mission_id, 100.0)

    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    drone = world.drone(DRONE)
    baltycka = world.session.get(Hub, BALTYCKA)
    assert baltycka is not None
    assert distance_km((drone.longitude, drone.latitude), hub_point(baltycka)) * 1000 < 50
    assert drone.status == DroneStatus.MAINTENANCE
    assert world.occupancy()[BALTYCKA] == 2  # unchanged: the stopped drone is not docked


def test_with_other_hubs_out_of_battery_range_the_emergency_says_so(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    strict = world.settings.model_copy(update={"sim_critical_battery_pct": 90.0})

    world.advance(mission_id, 100.0, settings=strict)  # other Hubs would arrive below 90 %

    flight = world.flight(mission_id)
    assert flight.emergency_reason == EmergencyReason.BATTERY_INSUFFICIENT
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE


@pytest.mark.parametrize("tick_at", [30.0, 10_000.0])
def test_a_battery_that_falls_below_the_critical_floor_in_flight_is_an_emergency(
    world: World, launch: Launch, tick_at: float
) -> None:
    mission_id = launch(ORDER, DRONE)
    strict = world.settings.model_copy(update={"sim_critical_battery_pct": 95.0})

    # Whether the tick is on time (30 s) or hours late, the outcome is identical: the emergency is
    # placed at the exact moment the battery crossed the floor (about 24.8 s), never "when noticed".
    world.advance(mission_id, tick_at, settings=strict)

    flight = world.flight(mission_id)
    assert flight.emergency_reason == EmergencyReason.BATTERY_CRITICAL
    assert flight.phase == FlightPhase.EMERGENCY
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert world.order(ORDER).status == OrderStatus.DELIVERED
    assert flight.emergency_at is not None
    assert (as_utc(flight.emergency_at) - at(0)).total_seconds() == pytest.approx(24.8, abs=0.3)
    assert flight.battery_pct == pytest.approx(95.0, abs=1e-6)  # exactly at the floor


def test_an_emergency_releases_the_order_and_keeps_the_drone_out_of_service(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.fill_every_other_hub()
    world.advance(mission_id, 100.0)

    plan = missions_service.preview_plan(world.session, "ORD-002", DRONE, world.settings)

    assert not plan.eligible
    codes = {reason.code for reason in plan.reasons}
    assert "DRONE_NOT_AVAILABLE" in codes  # MAINTENANCE: needs an operator (a later feature)
    assert "DRONE_ALREADY_ASSIGNED" not in codes  # the emergency mission is no longer active
    with pytest.raises(missions_service.MissionNotCancellableError):
        missions_service.cancel_mission(world.session, mission_id)


def test_cancelling_after_takeoff_is_still_refused(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)

    with pytest.raises(missions_service.MissionNotCancellableError) as refused:
        missions_service.cancel_mission(world.session, mission_id)

    assert refused.value.status == "IN_FLIGHT"
    assert world.mission(mission_id).status == MissionStatus.IN_FLIGHT


def test_a_completed_mission_frees_the_order_claim_and_the_drone(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.advance(mission_id, 60.0)

    plan = missions_service.preview_plan(world.session, "ORD-002", DRONE, world.settings)

    assert "DRONE_ALREADY_ASSIGNED" not in {reason.code for reason in plan.reasons}
    assert plan.eligible


OSOWA = "hub-centrum-handlowe-osowa"


def test_a_diversion_target_that_fills_up_diverts_again(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.advance(mission_id, 34.7)  # diverting to Forum, which has room
    assert world.flight(mission_id).landing_target_hub_id == FORUM

    world.set_capacity({FORUM: 3})  # Forum fills up while the drone is on its way

    world.advance(mission_id, 500.0)

    flight = world.flight(mission_id)
    assert flight.tried_hub_ids == [BALTYCKA, FORUM]  # each Hub is tried at most once
    assert flight.landed_hub_id == OSOWA  # still within the battery's reach
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.drone(DRONE).status == DroneStatus.IDLE
    # The battery floor was respected: the drone arrived with at least the critical 5 %.
    assert flight.battery_pct >= world.settings.sim_critical_battery_pct
    assert world.occupancy()[OSOWA] == 4
    assert world.occupancy()[FORUM] == 3 and world.occupancy()[BALTYCKA] == 2


def test_a_chain_of_full_hubs_ends_in_an_emergency_when_nothing_else_is_reachable(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.advance(mission_id, 34.7)  # diverting to Forum
    world.set_capacity({FORUM: 3})
    world.advance(mission_id, 200.0)  # now diverting to Osowa
    assert world.flight(mission_id).landing_target_hub_id == OSOWA
    world.set_capacity({OSOWA: 3})  # Osowa fills up as well

    world.advance(mission_id, 2000.0)

    flight = world.flight(mission_id)
    assert flight.tried_hub_ids == [BALTYCKA, FORUM, OSOWA]
    assert flight.emergency_reason == EmergencyReason.BATTERY_INSUFFICIENT  # Riviera is too far
    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    drone = world.drone(DRONE)
    osowa = world.session.get(Hub, OSOWA)
    assert osowa is not None
    assert drone.status == DroneStatus.MAINTENANCE
    assert distance_km((drone.longitude, drone.latitude), hub_point(osowa)) * 1000 == pytest.approx(
        60.0, abs=1.0
    )
    assert world.occupancy()[OSOWA] == 3  # never above its capacity
    assert world.order(ORDER).status == OrderStatus.DELIVERED


def test_one_failing_flight_does_not_stall_the_others(
    world: World,
    launch: Launch,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = launch("ORD-001", "DRN-010")
    healthy = launch("ORD-004", "DRN-007")  # starts at Forum, a different Hub
    # Corrupt the older flight so that advancing it raises.
    world.session.execute(
        update(MissionFlight).where(MissionFlight.mission_id == broken).values(legs=[])
    )
    world.session.commit()

    with caplog.at_level("ERROR", logger="skyfleet.simulation"):
        advanced = engine.run_step(session_factory, world.settings, at(500.0))
    world.session.expire_all()

    assert advanced == 2
    assert f"Could not advance flight {broken}" in caplog.text
    assert world.mission(healthy).status == MissionStatus.COMPLETED  # the other flight landed
    assert world.mission(broken).status == MissionStatus.IN_FLIGHT  # untouched, retried next tick
    assert last_heartbeat(world.session) == at(500.0)


def test_a_drone_can_fly_from_one_hub_and_land_at_another(world: World, launch: Launch) -> None:
    """ORD-011: picked up at Bałtycka, delivered at Forum Gdańsk, landed at Forum Gdańsk."""
    before = world.occupancy()  # all three Hubs are full of their docked drones, as seeded
    mission_id = launch("ORD-011", "DRN-011")
    world.session.expire_all()
    mission = world.mission(mission_id)
    assert mission.origin_hub_id == BALTYCKA
    assert mission.return_hub_id == FORUM
    world.advance(mission_id, 10.0)
    assert world.occupancy()[BALTYCKA] == before[BALTYCKA] - 1  # it left Bałtycka at takeoff
    assert world.occupancy()[FORUM] == before[FORUM]  # in flight: it counts at no Hub

    world.advance(mission_id, 500.0)

    flight = world.flight(mission_id)
    forum = world.session.get(Hub, FORUM)
    assert forum is not None
    assert flight.phase == FlightPhase.LANDED
    assert flight.landed_hub_id == FORUM != mission.origin_hub_id
    assert world.mission(mission_id).status == MissionStatus.COMPLETED
    assert world.order("ORD-011").status == OrderStatus.DELIVERED
    drone = world.drone("DRN-011")
    assert drone.status == DroneStatus.IDLE
    assert (drone.longitude, drone.latitude) == hub_point(forum)  # docked at the other Hub
    assert drone.hub_id == FORUM  # Feature 017C: the Hub where it last docked successfully
    assert world.occupancy()[FORUM] == before[FORUM] + 1
    assert world.occupancy()[BALTYCKA] == before[BALTYCKA] - 1


# --- Feature 017C: the drone's hub_id follows its last successful docking ---------------------

# ORD-011 is a seeded cross-Hub order: picked up at Bałtycka, delivered next to Forum Gdańsk,
# whose Hub is the nearest return Hub. DRN-011 is docked at Bałtycka.
CROSS_ORDER, CROSS_DRONE = "ORD-011", "DRN-011"


def test_a_return_to_the_origin_hub_leaves_hub_id_unchanged(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    assert world.drone(DRONE).hub_id == BALTYCKA

    world.advance(mission_id, 60.0)

    assert world.flight(mission_id).landed_hub_id == BALTYCKA
    assert world.drone(DRONE).hub_id == BALTYCKA


def test_a_planned_cross_hub_return_lands_there_and_moves_hub_id_only_at_landing(
    world: World, launch: Launch
) -> None:
    mission_id = launch(CROSS_ORDER, CROSS_DRONE)
    mission = world.mission(mission_id)
    assert (mission.origin_hub_id, mission.return_hub_id) == (BALTYCKA, FORUM)
    delivery_end = leg_from_dict(world.flight(mission_id).legs[1]).end_s

    world.advance(mission_id, delivery_end - 1.0)  # still carrying the parcel, in the air
    assert world.order(CROSS_ORDER).status == OrderStatus.OUT_FOR_DELIVERY
    assert world.drone(CROSS_DRONE).status == DroneStatus.IN_FLIGHT
    assert world.drone(CROSS_DRONE).hub_id == BALTYCKA  # unchanged in flight

    world.advance(mission_id, 600.0)

    flight, mission = world.flight(mission_id), world.mission(mission_id)
    forum = world.session.get(Hub, FORUM)
    assert forum is not None
    assert mission.status == MissionStatus.COMPLETED
    assert flight.landed_hub_id == FORUM == flight.planned_return_hub_id
    drone = world.drone(CROSS_DRONE)
    assert drone.hub_id == FORUM  # now the Hub where it last docked
    assert drone.status == DroneStatus.IDLE
    assert (drone.longitude, drone.latitude) == hub_point(forum)  # exactly at the Hub: no teleport
    # History keeps where the drone really started and where the plan sent it.
    assert (mission.origin_hub_id, mission.return_hub_id) == (BALTYCKA, FORUM)
    assert world.order(CROSS_ORDER).origin_hub_id == BALTYCKA


def test_a_drone_that_landed_elsewhere_charges_there_and_is_dispatched_from_the_new_hub(
    world: World, launch: Launch
) -> None:
    mission_id = launch(CROSS_ORDER, CROSS_DRONE)
    world.advance(mission_id, 600.0)
    assert world.drone(CROSS_DRONE).hub_id == FORUM
    assert world.drone(CROSS_DRONE).battery_pct < 100

    fast = world.settings.model_copy(update={"sim_charge_rate_pct_per_minute": 600.0})
    state = ChargingState()
    for second in range(1000, 1060):
        charge_step(world.factory, fast, at(second), state)
    world.session.expire_all()

    drone = world.drone(CROSS_DRONE)
    assert (drone.status, drone.battery_pct) == (DroneStatus.IDLE, 100)  # charged at Forum
    # A Forum order can now be served by this drone, because it is docked at Forum.
    new_mission = missions_service.confirm_mission(
        world.session, "ORD-004", CROSS_DRONE, world.settings
    )
    assert new_mission.origin_hub_id == FORUM
    assert new_mission.drone_id == CROSS_DRONE


def test_a_diversion_that_lands_moves_hub_id_to_the_hub_it_landed_at(
    world: World, launch: Launch
) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})  # full on arrival: the drone is diverted to Forum

    world.advance(mission_id, 34.7)
    assert world.flight(mission_id).phase == FlightPhase.DIVERTING
    assert world.drone(DRONE).hub_id == BALTYCKA  # still in flight: unchanged

    world.advance(mission_id, 500.0)

    assert world.flight(mission_id).landed_hub_id == FORUM
    assert world.drone(DRONE).hub_id == FORUM
    assert world.mission(mission_id).origin_hub_id == BALTYCKA  # history is not rewritten


def test_an_emergency_never_changes_hub_id(world: World, launch: Launch) -> None:
    mission_id = launch(ORDER, DRONE)
    world.set_capacity({BALTYCKA: 2})
    world.fill_every_other_hub()

    world.advance(mission_id, 2000.0)

    assert world.mission(mission_id).status == MissionStatus.EMERGENCY
    assert world.drone(DRONE).status == DroneStatus.MAINTENANCE
    assert world.drone(DRONE).hub_id == BALTYCKA  # never docked, so nothing changed
