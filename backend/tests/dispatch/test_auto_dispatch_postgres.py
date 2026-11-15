"""Overlapping automatic-dispatch passes on PostgreSQL, in a temporary database (feature 014C).

Opt-in (`uv run pytest -m postgres`) with the `temp_engine` fixture: the real migrations (including
0006) run in a uniquely named database on the local Docker PostgreSQL, which is dropped afterwards.
The development database is never touched; an unreachable server skips the tests.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.config import Settings
from app.dispatch import auto
from app.dispatch.models import DispatchAutoState
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.simulation.heartbeat import record_heartbeat

pytestmark = pytest.mark.postgres

SETTINGS = Settings(mission_payload_energy_factor=0.5, hub_dock_proximity_m=50)


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    session_factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with session_factory() as session:
        record_heartbeat(session, clock.utcnow())
    yield session_factory


def race(actions: list[Callable[[], str | None]]) -> list[str | None]:
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], str | None]) -> str | None:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(run, a) for a in actions]]


def test_the_mode_is_off_until_enabled_and_a_pass_then_does_nothing(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        assert session.get(DispatchAutoState, "auto-dispatch") is None  # no row: OFF
    assert auto.run_dispatch_pass(factory, SETTINGS, clock.utcnow()) is None
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Mission)) == 0


def test_overlapping_passes_never_start_a_drone_or_an_order_twice(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        auto.enable(session, clock.utcnow(), SETTINGS)

    outcomes = race(
        [lambda: auto.run_dispatch_pass(factory, SETTINGS, clock.utcnow()) for _ in range(4)]
    )

    assert all(outcome is not None for outcome in outcomes)  # no pass raised
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    with factory() as session:
        missions = list(session.scalars(select(Mission).where(Mission.status.in_(active))))
    # One 100 % drone per Hub in the seed data: four missions, none duplicated.
    assert len(missions) == 4
    assert len({m.order_id for m in missions}) == 4
    assert len({m.drone_id for m in missions}) == 4
    assert {m.status for m in missions} == {"IN_FLIGHT"}


def test_disabling_stops_the_next_pass(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        auto.disable(session, clock.utcnow(), SETTINGS)

    assert auto.run_dispatch_pass(factory, SETTINGS, clock.utcnow()) is None
