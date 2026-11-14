"""Automatic fleet rebalancing under concurrency on PostgreSQL, in a temporary database (019B).

Opt-in (`uv run pytest -m postgres`) with the `temp_engine` fixture: the real migrations run in a
uniquely named database on the local Docker PostgreSQL, which is dropped afterwards. The
development database is never touched. The seed gives each Hub three drones (100, 90, 80 %) and
orders; `_scenario` leaves Forum short of drones and Bałtycka with two 100 % drones.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.rebalancing import run_rebalancing
from app.dispatch.service import execute_dispatch
from app.drones.models import Drone, DroneStatus
from app.events.models import OperationalEvent
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission, MissionPurpose
from app.missions.service import MissionError
from app.orders.models import DeliveryOrder
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import MissionFlight
from app.simulation.relocation import RelocationRejectedError, start_relocation

pytestmark = pytest.mark.postgres

SETTINGS = Settings(mission_payload_energy_factor=0.5, hub_dock_proximity_m=50)
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
OSOWA = "hub-centrum-handlowe-osowa"


def _scenario(factory: sessionmaker[Session], keep_orders: list[str]) -> None:
    """Forum has no 100 % drone; Bałtycka has DRN-010 and DRN-011 at 100 %; only `keep_orders`."""
    with factory() as session:
        for table in (OperationalEvent, MissionFlight):
            session.execute(delete(table))
        session.execute(delete(Mission))
        session.execute(delete(DeliveryOrder).where(DeliveryOrder.id.not_in(keep_orders)))
        for drone_id, pct in {"DRN-007": 50, "DRN-010": 100, "DRN-011": 100}.items():
            drone = session.get(Drone, drone_id)
            assert drone is not None
            drone.battery_pct = pct
            drone.status = DroneStatus.IDLE.value
        record_heartbeat(session, NOW)
        session.commit()


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def _race(actions: list[Callable[[], object]]) -> list[object]:
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], object]) -> object:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(run, a) for a in actions]]


def _rebalance(factory: sessionmaker[Session]) -> str | None:
    return run_rebalancing(factory, SETTINGS, NOW, lambda: True)


def _active(factory: sessionmaker[Session], drone_id: str | None = None) -> list[Mission]:
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    statement = select(Mission).where(Mission.status.in_(active))
    if drone_id is not None:
        statement = statement.where(Mission.drone_id == drone_id)
    with factory() as session:
        return list(session.scalars(statement))


def test_overlapping_rebalancing_passes_send_exactly_one_drone(
    factory: sessionmaker[Session],
) -> None:
    _scenario(factory, keep_orders=["ORD-004"])  # one waiting order at Forum

    _race([lambda: _rebalance(factory) for _ in range(4)])

    [mission] = _active(factory)
    assert mission.purpose == MissionPurpose.RELOCATION.value and mission.order_id is None
    assert mission.drone_id == "DRN-010"


def test_rebalancing_against_a_manual_relocation_never_double_books_a_drone(
    factory: sessionmaker[Session],
) -> None:
    _scenario(factory, keep_orders=["ORD-004"])

    def manual() -> str:
        with factory() as session:
            try:
                return start_relocation(session, "DRN-010", OSOWA, NOW, SETTINGS).id
            except RelocationRejectedError:
                return "rejected"

    _race([manual, lambda: _rebalance(factory)])

    assert len(_active(factory, "DRN-010")) == 1


def test_rebalancing_against_dispatch_never_gives_a_drone_two_missions(
    factory: sessionmaker[Session],
) -> None:
    # Bałtycka keeps ORD-001 (dispatch would send DRN-010) and still has a spare drone.
    _scenario(factory, keep_orders=["ORD-004", "ORD-001"])

    def dispatch() -> str:
        with factory() as session:
            try:
                return execute_dispatch(session, "ORD-001", "DRN-010", NOW, SETTINGS).id
            except MissionError:
                return "rejected"

    _race([dispatch, lambda: _rebalance(factory)])

    active = _active(factory, "DRN-010")
    assert len(active) == 1
    assert (active[0].purpose == MissionPurpose.RELOCATION.value) == (active[0].order_id is None)
