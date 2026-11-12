"""Flight concurrency on real PostgreSQL, in a uniquely named temporary database.

Opt-in (`uv run pytest -m postgres`); see the `temp_engine` fixture in tests/conftest.py, which
refuses anything but the local Docker PostgreSQL (port 55432), never touches the development
database, and drops the temporary database afterwards. Real sessions race in threads.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.drones.seed import seed_drones
from app.hubs.models import Hub
from app.hubs.seed import seed_hubs
from app.missions import service as missions_service
from app.missions.models import Mission, MissionStatus
from app.missions.presence import hub_occupancy
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.seed import seed_orders
from app.simulation import engine
from app.simulation import service as simulation_service
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import FlightPhase, MissionFlight

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
BALTYCKA, FORUM = "hub-galeria-baltycka", "hub-forum-gdansk"
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


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    reset(temp_engine)
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def reset(pg: Engine) -> None:
    """Back to the seeded state (the drone model row is kept)."""
    with pg.begin() as connection:
        for table in (
            "mission_flights",
            "simulation_heartbeats",
            "missions",
            "orders",
            "drones",
            "hubs",
        ):
            connection.execute(text(f"DELETE FROM {table}"))
    with sessionmaker(bind=pg)() as session:
        seed_hubs(session)
        seed_drones(session)
        seed_orders(session)


def launch(factory: sessionmaker[Session], order_id: str, drone_id: str) -> str:
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, NOW)
        simulation_service.start_mission(session, mission.id, NOW, SETTINGS)
        return mission.id


def race(actions: list[Callable[[], Any]]) -> list[Any]:
    """Run all actions at the same moment in separate threads; exceptions are returned."""
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], Any]) -> Any:
        barrier.wait(timeout=10)
        try:
            return action()
        except Exception as error:  # the outcome is what the test inspects
            return error

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(run, a) for a in actions]]


def occupancy(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        drones = session.scalars(select(Drone)).all()
        hubs = session.scalars(select(Hub)).all()
        return dict(hub_occupancy(drones, hubs, 50))


def test_simultaneous_arrivals_never_push_a_hub_above_its_capacity(
    factory: sessionmaker[Session], temp_engine: Engine
) -> None:
    for _ in range(3):  # repeat: a race that passes once could be luck
        reset(temp_engine)
        missions = [
            launch(factory, "ORD-001", "DRN-010"),
            launch(factory, "ORD-002", "DRN-011"),
            launch(factory, "ORD-003", "DRN-012"),
        ]
        with factory() as session:  # all three left Bałtycka; allow exactly one to land back
            session.execute(update(Hub).where(Hub.id == BALTYCKA).values(drone_capacity=1))
            session.commit()

        def land(mission_id: str) -> Callable[[], None]:
            return lambda: engine.advance_flight(factory, SETTINGS, mission_id, at(500.0))

        outcomes = race([land(m) for m in missions])

        assert all(outcome is None for outcome in outcomes), outcomes  # no errors or deadlocks
        with factory() as session:
            flights = [session.get(MissionFlight, m) for m in missions]
            landed = sorted(f.landed_hub_id for f in flights if f and f.landed_hub_id)
            # One took the single place, the other two were diverted.
            assert landed == sorted([BALTYCKA, FORUM, FORUM])
            assert all(f and f.phase == FlightPhase.LANDED for f in flights)
            assert all(
                session.get(Mission, m).status == MissionStatus.COMPLETED  # type: ignore[union-attr]
                for m in missions
            )
        counts = occupancy(factory)
        assert counts[BALTYCKA] == 1  # never above the capacity of 1
        assert counts[FORUM] == 5  # 3 already docked + 2 diverted
        assert all(count <= 50 for count in counts.values())


def test_concurrent_starts_take_off_exactly_once(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        mission_id = missions_service.confirm_mission(session, "ORD-001", "DRN-010", SETTINGS).id
        record_heartbeat(session, NOW)

    def start() -> str:
        with factory() as session:
            simulation_service.start_mission(session, mission_id, NOW, SETTINGS)
            return "started"

    outcomes = race([start for _ in range(6)])

    assert outcomes.count("started") == 1
    refused = [o for o in outcomes if o != "started"]
    assert len(refused) == 5
    assert all(isinstance(o, simulation_service.MissionNotStartableError) for o in refused)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(MissionFlight)) == 1
        drone = session.get(Drone, "DRN-010")
        order = session.get(DeliveryOrder, "ORD-001")
        assert drone is not None and drone.status == DroneStatus.IN_FLIGHT
        assert order is not None and order.status == OrderStatus.OUT_FOR_DELIVERY


def test_starting_while_cancelling_has_exactly_one_winner(
    factory: sessionmaker[Session], temp_engine: Engine
) -> None:
    for _ in range(3):
        with factory() as session:
            mission_id = missions_service.confirm_mission(
                session, "ORD-001", "DRN-010", SETTINGS
            ).id
            record_heartbeat(session, NOW)

        def start(mid: str = mission_id) -> str:
            with factory() as session:
                simulation_service.start_mission(session, mid, NOW, SETTINGS)
                return "started"

        def cancel(mid: str = mission_id) -> str:
            with factory() as session:
                missions_service.cancel_mission(session, mid)
                return "cancelled"

        outcomes = race([start, cancel])

        assert sorted(o for o in outcomes if isinstance(o, str)) in (["cancelled"], ["started"])
        loser = next(o for o in outcomes if not isinstance(o, str))
        with factory() as session:
            mission = session.get(Mission, mission_id)
            drone = session.get(Drone, "DRN-010")
            order = session.get(DeliveryOrder, "ORD-001")
            flights = session.scalar(select(func.count()).select_from(MissionFlight))
            assert mission and drone and order
            if "started" in outcomes:
                assert isinstance(loser, missions_service.MissionNotCancellableError)
                assert mission.status == MissionStatus.IN_FLIGHT and flights == 1
                assert drone.status == DroneStatus.IN_FLIGHT
                assert order.status == OrderStatus.OUT_FOR_DELIVERY
            else:
                assert isinstance(loser, simulation_service.MissionNotStartableError)
                assert mission.status == MissionStatus.CANCELLED and flights == 0
                assert drone.status == DroneStatus.IDLE
                assert order.status == OrderStatus.READY_FOR_PICKUP
        reset(temp_engine)


def test_several_workers_on_the_same_flight_apply_each_milestone_once(
    factory: sessionmaker[Session],
) -> None:
    mission_id = launch(factory, "ORD-001", "DRN-010")

    outcomes = race(
        [lambda: engine.advance_flight(factory, SETTINGS, mission_id, at(25.0)) for _ in range(4)]
    )

    assert all(outcome is None for outcome in outcomes), outcomes
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        order = session.get(DeliveryOrder, "ORD-001")
        assert flight is not None and order is not None
        assert order.status == OrderStatus.DELIVERED
        assert flight.delivered_at is not None
        assert flight.phase == FlightPhase.RETURNING
        assert session.get(Mission, mission_id).status == MissionStatus.IN_FLIGHT  # type: ignore[union-attr]


def test_a_flight_that_catches_up_after_downtime_lands_once(
    factory: sessionmaker[Session],
) -> None:
    mission_id = launch(factory, "ORD-001", "DRN-010")

    engine.advance_flight(factory, SETTINGS, mission_id, at(10_000.0))
    engine.advance_flight(factory, SETTINGS, mission_id, at(10_001.0))  # a duplicate tick

    with factory() as session:
        assert session.get(Mission, mission_id).status == MissionStatus.COMPLETED  # type: ignore[union-attr]
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None and flight.landed_hub_id == BALTYCKA
    assert occupancy(factory)[BALTYCKA] == 3


def test_migration_0005_round_trips_on_postgres(temp_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[2] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", temp_engine.url.render_as_string(hide_password=False))
    reset(temp_engine)

    command.downgrade(config, "0004")
    with temp_engine.connect() as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert not {"mission_flights", "simulation_heartbeats"} & remaining
    with pytest.raises(IntegrityError), temp_engine.begin() as connection:
        connection.execute(text("UPDATE orders SET status = 'DELIVERED' WHERE id = 'ORD-001'"))

    command.upgrade(config, "head")
    with temp_engine.begin() as connection:
        connection.execute(text("UPDATE orders SET status = 'DELIVERED' WHERE id = 'ORD-001'"))
        connection.execute(text("UPDATE orders SET status = 'READY_FOR_PICKUP'"))
    with temp_engine.connect() as connection:
        definitions = {
            row[0]: row[1]
            for row in connection.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'missions'")
            )
        }
    assert "WHERE" in definitions["uq_missions_active_order"]  # still a partial unique index
    assert "WHERE" in definitions["uq_missions_active_drone"]
