"""Order Simulation on PostgreSQL in a temporary database (feature 015B).

Opt-in (`uv run pytest -m postgres`) and skipped when the Docker PostgreSQL is unreachable; it
uses the `temp_engine` fixture (real migrations applied), so the development database is never
touched.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.orders import simulation
from app.orders.models import DeliveryOrder, OrderSimulationState, OrderStatus
from app.simulation.heartbeat import record_heartbeat

pytestmark = pytest.mark.postgres

NOW = datetime.now(UTC)
SETTINGS = Settings(order_sim_max_outstanding_orders=10_000)


@pytest.fixture
def factory(temp_engine: Engine) -> sessionmaker[Session]:
    session_factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with session_factory() as session:
        session.execute(delete(OrderSimulationState))  # the database is shared in this module
        session.commit()
        record_heartbeat(session, NOW)
    return session_factory


def test_the_state_table_comes_from_the_real_migration(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        status = simulation.get_status(session, NOW, SETTINGS)

    assert (status.enabled, status.last_outcome) == (False, None)


def test_simultaneous_first_enables_leave_exactly_one_row(
    factory: sessionmaker[Session],
) -> None:
    barrier = threading.Barrier(8)

    def enable() -> bool:
        barrier.wait(timeout=10)
        with factory() as session:
            return simulation.enable(session, NOW, SETTINGS).enabled

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [future.result(timeout=60) for future in [pool.submit(enable) for _ in range(8)]]

    assert results == [True] * 8
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(OrderSimulationState)) == 1
    assert simulation.is_enabled(factory)


def test_generation_steps_create_distinct_ready_orders(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        simulation.enable(session, NOW, SETTINGS)
        before = set(session.scalars(select(DeliveryOrder.id)))

    outcomes = [
        simulation.run_generation_step(factory, SETTINGS, NOW, random.Random(seed))
        for seed in range(6)
    ]

    assert all(outcome and outcome.startswith("Created") for outcome in outcomes)
    with factory() as session:
        created = set(session.scalars(select(DeliveryOrder.id))) - before
        assert len(created) == 6
        statuses = set(
            session.scalars(select(DeliveryOrder.status).where(DeliveryOrder.id.in_(created)))
        )
    assert statuses == {OrderStatus.READY_FOR_PICKUP.value}


def test_a_disabled_mode_creates_nothing(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(DeliveryOrder))

    assert simulation.run_generation_step(factory, SETTINGS, NOW) is None

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(DeliveryOrder)) == before
