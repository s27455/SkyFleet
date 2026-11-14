"""Concurrent manual relocation on PostgreSQL in a temporary database (Feature 019A).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations (0015 included) to a throwaway database, so the development database is never touched.
"""

import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.service import execute_dispatch
from app.drones.models import Drone
from app.events.models import EventType, OperationalEvent
from app.hubs.models import Hub
from app.missions.models import Mission, MissionPurpose
from app.missions.presence import hub_occupancy
from app.missions.service import MissionError
from app.simulation import engine as sim_engine
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.flight import leg_from_dict
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import MissionFlight
from app.simulation.relocation import RelocationRejectedError, start_relocation

pytestmark = pytest.mark.postgres

SETTINGS = Settings(
    mission_payload_energy_factor=0.5,
    hub_dock_proximity_m=50,
    sim_flight_min_seconds=30,
    sim_flight_max_seconds=90,
    sim_delivery_dwell_seconds=3,
    sim_landing_approach_m=60,
    sim_critical_battery_pct=5,
    sim_heartbeat_stale_seconds=10,
)
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
BALTYCKA, FORUM, OSOWA = (
    "hub-galeria-baltycka",
    "hub-forum-gdansk",
    "hub-centrum-handlowe-osowa",
)


def _beat(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        record_heartbeat(session, NOW)


def _relocate(factory: sessionmaker[Session], drone: str, destination: str) -> str:
    with factory() as session:
        try:
            return start_relocation(session, drone, destination, NOW, SETTINGS).id
        except RelocationRejectedError:
            return "rejected"


def _run_all(jobs: list[Callable[[], str]]) -> list[str]:
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(job) for job in jobs]
        return [future.result() for future in futures]


def _count(factory: sessionmaker[Session], drone: str) -> tuple[int, int]:
    with factory() as session:
        missions = session.scalar(
            select(func.count()).select_from(Mission).where(Mission.drone_id == drone)
        )
        events = session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(
                OperationalEvent.drone_id == drone,
                OperationalEvent.event_type == EventType.DRONE_RELOCATION.value,
            )
        )
        return missions or 0, events or 0


def _end_s(factory: sessionmaker[Session], mission_id: str) -> float:
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        return leg_from_dict(flight.legs[-1]).end_s


def test_concurrent_relocations_of_one_drone_create_exactly_one_flight(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    _beat(factory)
    destinations = [FORUM, OSOWA, FORUM, OSOWA, FORUM, OSOWA]

    results = _run_all([functools.partial(_relocate, factory, "DRN-012", d) for d in destinations])

    assert sum(result != "rejected" for result in results) == 1
    assert _count(factory, "DRN-012") == (1, 1)  # one mission, one STARTED event


def test_relocation_against_dispatch_never_gives_a_drone_two_missions(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    _beat(factory)

    def dispatch() -> str:
        with factory() as session:
            try:
                return execute_dispatch(session, "ORD-007", "DRN-004", NOW, SETTINGS).id
            except MissionError:
                return "rejected"

    results = _run_all([dispatch, lambda: _relocate(factory, "DRN-004", OSOWA)])

    assert sum(result != "rejected" for result in results) == 1
    with factory() as session:
        active = session.scalars(
            select(Mission).where(
                Mission.drone_id == "DRN-004", Mission.status.in_(["ASSIGNED", "IN_FLIGHT"])
            )
        ).all()
        assert len(active) == 1
        assert (active[0].purpose == MissionPurpose.RELOCATION.value) == (
            active[0].order_id is None
        )


def test_a_failure_racing_the_worker_ends_the_relocation_once(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    _beat(factory)
    # The database is shared by this module's tests: land the flights they left, so the failure
    # trigger can only pick the relocation under test.
    with factory() as session:
        leftovers = list(session.scalars(select(Mission.id).where(Mission.status == "IN_FLIGHT")))
    for leftover in leftovers:
        sim_engine.advance_flight(factory, SETTINGS, leftover, NOW + timedelta(hours=1))
    mission_id = _relocate(factory, "DRN-007", BALTYCKA)
    assert mission_id != "rejected"
    end = _end_s(factory, mission_id)
    when = NOW + timedelta(seconds=end / 3)

    def fail() -> str:
        with factory() as session:
            try:
                return trigger_drone_failure(session, when, SETTINGS).mission_id
            except NoEligibleTargetError:
                return "none"

    def tick() -> str:
        sim_engine.advance_flight(factory, SETTINGS, mission_id, when)
        return "ticked"

    _run_all([fail, tick, fail, tick])
    sim_engine.advance_flight(factory, SETTINGS, mission_id, NOW + timedelta(seconds=end + 60))

    with factory() as session:
        drone = session.get(Drone, "DRN-007")
        assert drone is not None
        assert (drone.status, drone.hub_id) == ("MAINTENANCE", FORUM)  # never reassigned
        failures = session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(
                OperationalEvent.mission_id == mission_id,
                OperationalEvent.event_type == EventType.DRONE_FAILURE.value,
            )
        )
        assert failures == 1


def test_two_relocations_landing_at_a_nearly_full_hub_never_exceed_its_capacity(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    _beat(factory)
    with factory() as session:
        hubs = list(session.scalars(select(Hub)))
        docked = hub_occupancy(list(session.scalars(select(Drone))), hubs, 50)[FORUM]
        forum = session.get(Hub, FORUM)
        assert forum is not None
        forum.drone_capacity = docked + 2  # both pass the start check, only one fits at landing
        for drone_id in (
            "DRN-001",
            "DRN-002",
        ):  # full batteries: the diverted one must still fly on
            drone = session.get(Drone, drone_id)
            assert drone is not None
            drone.battery_pct = 100
        session.commit()
    first = _relocate(factory, "DRN-001", FORUM)
    second = _relocate(factory, "DRN-002", FORUM)
    assert "rejected" not in (first, second)
    with factory() as session:
        forum = session.get(Hub, FORUM)
        assert forum is not None
        forum.drone_capacity = docked + 1  # it fills up while they fly
        session.commit()
    end = max(_end_s(factory, first), _end_s(factory, second))

    def land(mission_id: str) -> str:
        sim_engine.advance_flight(factory, SETTINGS, mission_id, NOW + timedelta(seconds=end + 1))
        return "done"

    _run_all([lambda: land(first), lambda: land(second)])
    for mission_id in (first, second):  # a diverted drone still has its diversion leg to fly
        sim_engine.advance_flight(factory, SETTINGS, mission_id, NOW + timedelta(seconds=end + 600))

    with factory() as session:
        hubs = list(session.scalars(select(Hub)))
        drones = list(session.scalars(select(Drone)))
        occupancy = hub_occupancy(drones, hubs, 50)
        assert occupancy[FORUM] <= docked + 1
        landed = [
            flight.landed_hub_id
            for flight in session.scalars(
                select(MissionFlight).where(MissionFlight.mission_id.in_([first, second]))
            )
        ]
        assert None not in landed and landed.count(FORUM) == 1
