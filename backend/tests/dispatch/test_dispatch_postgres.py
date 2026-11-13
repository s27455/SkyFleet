"""Dispatch execution under real concurrency, on PostgreSQL in a temporary database (feature 014B).

Opt-in (`uv run pytest -m postgres`), like `tests/missions/test_missions_postgres.py`: it uses the
`temp_engine` fixture, a uniquely named database on the local Docker PostgreSQL that is dropped
afterwards. The development database is never touched; if the server is unreachable the tests are
skipped. Each test uses its own orders and drones, so none depends on another.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch import service
from app.drones.models import Drone, DroneStatus
from app.missions import service as missions_service
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.simulation import clock
from app.simulation.heartbeat import record_heartbeat

pytestmark = pytest.mark.postgres

SETTINGS = Settings(mission_payload_energy_factor=0.5, hub_dock_proximity_m=50)


@dataclass(frozen=True)
class Outcome:
    kind: str  # "started", "already-assigned", "rejected" or "error:<name>"
    detail: str = ""


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    session_factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with session_factory() as session:
        record_heartbeat(session, clock.utcnow())  # takeoff needs a fresh worker heartbeat
    yield session_factory


def charge(factory: sessionmaker[Session], *drone_ids: str) -> None:
    with factory() as session:
        for drone_id in drone_ids:
            drone = session.get(Drone, drone_id)
            assert drone is not None
            drone.battery_pct = 100
        session.commit()


def execute(factory: sessionmaker[Session], order_id: str, drone_id: str) -> Callable[[], Outcome]:
    def action() -> Outcome:
        with factory() as session:
            try:
                mission = service.execute_dispatch(
                    session, order_id, drone_id, clock.utcnow(), SETTINGS
                )
            except service.MissionAlreadyAssignedError:
                return Outcome("already-assigned")
            except missions_service.PlanRejectedError as error:
                return Outcome("rejected", ",".join(r.code for r in error.plan.reasons))
            except Exception as error:  # anything else is a bug the test must show
                return Outcome(f"error:{type(error).__name__}", str(error))
            return Outcome("started", mission.id)

    return action


def race(actions: list[Callable[[], Outcome]]) -> list[Outcome]:
    """Run all actions at the same moment in separate threads and collect their outcomes."""
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], Outcome]) -> Outcome:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(run, a) for a in actions]]


def kinds(outcomes: list[Outcome]) -> list[str]:
    return sorted(outcome.kind for outcome in outcomes)


def active_count(factory: sessionmaker[Session], column: str, value: str) -> int:
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    with factory() as session:
        statement = (
            select(func.count())
            .select_from(Mission)
            .where(getattr(Mission, column) == value, Mission.status.in_(active))
        )
        return session.scalar(statement) or 0


def drone_status(factory: sessionmaker[Session], drone_id: str) -> str:
    with factory() as session:
        drone = session.get(Drone, drone_id)
        assert drone is not None
        return drone.status


def test_two_dispatches_of_one_order_to_different_drones_start_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    charge(factory, "DRN-010", "DRN-011")

    outcomes = race(
        [execute(factory, "ORD-001", "DRN-010"), execute(factory, "ORD-001", "DRN-011")]
    )

    assert kinds(outcomes).count("started") == 1
    assert not [o for o in outcomes if o.kind.startswith("error:")], outcomes
    assert active_count(factory, "order_id", "ORD-001") == 1
    flying = [
        d for d in ("DRN-010", "DRN-011") if drone_status(factory, d) == DroneStatus.IN_FLIGHT
    ]
    assert len(flying) == 1  # the loser's drone was never touched


def test_two_dispatches_of_different_orders_to_one_drone_start_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    outcomes = race(
        [execute(factory, "ORD-009", "DRN-001"), execute(factory, "ORD-010", "DRN-001")]
    )

    assert kinds(outcomes).count("started") == 1
    assert not [o for o in outcomes if o.kind.startswith("error:")], outcomes
    assert active_count(factory, "drone_id", "DRN-001") == 1
    loser = next(o for o in outcomes if o.kind != "started")
    assert loser.kind in {"rejected", "already-assigned"}


def test_many_identical_dispatches_start_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    outcomes = race([execute(factory, "ORD-004", "DRN-007") for _ in range(8)])

    assert kinds(outcomes).count("started") == 1
    assert not [o for o in outcomes if o.kind.startswith("error:")], outcomes
    assert active_count(factory, "order_id", "ORD-004") == 1
    assert active_count(factory, "drone_id", "DRN-007") == 1
    assert drone_status(factory, "DRN-007") == DroneStatus.IN_FLIGHT


def test_independent_dispatches_all_succeed(factory: sessionmaker[Session]) -> None:
    charge(factory, "DRN-008")

    outcomes = race(
        [execute(factory, "ORD-007", "DRN-004"), execute(factory, "ORD-005", "DRN-008")]
    )

    assert kinds(outcomes) == ["started", "started"]
