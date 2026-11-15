"""Drone creation on PostgreSQL in a temporary database (Feature 021D).

Opt-in (`uv run pytest -m postgres`). Concurrent creators must get distinct, consecutive ids, and
a creator must wait for the one that holds the lock: the development database is never touched.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones import repository
from app.drones.models import Drone
from app.drones.schemas import DroneCreateRequest
from app.drones.seed import SF1_MODEL_ID
from app.drones.service import create_drone

pytestmark = pytest.mark.postgres

HUBS = ["hub-forum-gdansk", "hub-centrum-handlowe-osowa", "hub-galeria-baltycka"]


def _factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def _numbers(factory: sessionmaker[Session]) -> list[int]:
    with factory() as session:
        return sorted(int(i.removeprefix("DRN-")) for i in session.scalars(select(Drone.id)))


def test_concurrent_creators_get_distinct_consecutive_ids(temp_engine: Engine) -> None:
    factory = _factory(temp_engine)
    before = _numbers(factory)
    count = 9
    barrier = threading.Barrier(count)

    def create(n: int) -> str:
        barrier.wait()  # start together to provoke the race
        with factory() as session:
            drone = create_drone(
                session, DroneCreateRequest(hub_id=HUBS[n % len(HUBS)]), Settings()
            )
            assert drone.battery_pct == 100
            return drone.id

    with ThreadPoolExecutor(max_workers=count) as pool:
        ids = [future.result() for future in [pool.submit(create, n) for n in range(count)]]

    top = max(before)
    assert sorted(ids) == [
        f"DRN-{n:03d}" for n in range(top + 1, top + count + 1)
    ]  # no gap, no twin
    assert len(_numbers(factory)) == len(before) + count


def test_a_creator_waits_for_the_one_holding_the_model_lock(temp_engine: Engine) -> None:
    factory = _factory(temp_engine)
    holder = factory()
    assert repository.get_model_for_update(holder, SF1_MODEL_ID) is not None  # lock, uncommitted
    finished = threading.Event()
    result: list[str] = []

    def create() -> None:
        with factory() as session:
            result.append(create_drone(session, DroneCreateRequest(hub_id=HUBS[0]), Settings()).id)
        finished.set()

    thread = threading.Thread(target=create)
    thread.start()
    assert not finished.wait(1.0)  # serialised: blocked behind the lock holder
    holder.commit()  # release
    assert finished.wait(15)
    thread.join()
    assert len(result) == 1
