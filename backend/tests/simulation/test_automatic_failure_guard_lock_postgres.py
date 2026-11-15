"""The advisory lock of the automatic failure guard, proved deterministically on PostgreSQL.

Opt-in (`uv run pytest -m postgres`), throwaway database only. A randomized race rarely hits the
narrow window between the guard's count and the commit, so this test holds the first attempt open
exactly there: without the lock the second attempt would count the same fleet and both would pass.
Its own module, so the grounded drones set up here do not leak into other tests.
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin
from app.missions import service as missions_service
from app.simulation import failure
from app.simulation import service as simulation_service
from app.simulation.failure import (
    FleetGuardError,
    NoEligibleTargetError,
    fleet_availability,
    trigger_drone_failure,
)
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import MissionFlight

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
PAIRS = [("ORD-009", "DRN-001"), ("ORD-007", "DRN-004")]
FLYING = {drone for _, drone in PAIRS}


def _launch(factory: sessionmaker[Session], order_id: str, drone_id: str) -> None:
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission.id, now, SETTINGS)


class Ordered(random.Random):
    """A chooser that sorts the candidates (lowest or highest mission id first), never shuffles."""

    def __init__(self, reverse: bool) -> None:
        super().__init__(0)
        self.reverse = reverse

    def shuffle(self, x: list[str]) -> None:  # type: ignore[override]
        x.sort(reverse=self.reverse)


def _automatic(factory: sessionmaker[Session], reverse: bool = False) -> str:
    with factory() as session:
        try:
            trigger_drone_failure(
                session,
                datetime.now(UTC),
                SETTINGS,
                origin=EventOrigin.AUTOMATIC,
                rng=Ordered(reverse),
                automatic_safety=True,
            )
        except FleetGuardError:
            return "guard"
        except NoEligibleTargetError:
            return "none"
    return "failed"


def test_a_second_automatic_failure_waits_for_the_first_to_commit_and_is_then_refused(
    temp_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    for order_id, drone_id in PAIRS:
        _launch(factory, order_id, drone_id)
    with factory() as session:  # 12 drones, 5 unavailable: exactly ONE more failure is allowed
        spare = [d for d in session.scalars(select(Drone).order_by(Drone.id)) if d.id not in FLYING]
        for drone in spare[:5]:
            drone.status = DroneStatus.MAINTENANCE.value
        session.commit()
        assert fleet_availability(session) == (12, 5)

    counted = threading.Event()  # the first attempt has counted the fleet (and passed the guard)
    release = threading.Event()  # ... and is held here, before its commit
    calls = {"n": 0}
    guard_lock = threading.Lock()
    real = failure.fleet_availability

    def held_after_counting(session: Session) -> tuple[int, int]:
        result = real(session)
        with guard_lock:
            calls["n"] += 1
            first = calls["n"] == 1
        if first:
            counted.set()
            assert release.wait(30)
        return result

    monkeypatch.setattr(failure, "fleet_availability", held_after_counting)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_automatic, factory, False)  # takes the lowest mission id
        assert counted.wait(30)  # the first attempt holds the guard's lock and has not committed
        # The second attempt takes the OTHER flight, so only the guard's lock can hold it back
        # (it is not waiting on the first attempt's flight, mission or drone row locks).
        second = pool.submit(_automatic, factory, True)
        # Without the lock the second attempt would count the same fleet right now and pass.
        time.sleep(1.0)
        assert not second.done()
        release.set()
        outcomes = sorted([first.result(timeout=60), second.result(timeout=60)])

    assert outcomes == ["failed", "guard"]  # the second one saw the first one's approaching drone
    with factory() as session:
        failed = list(
            session.scalars(select(MissionFlight).where(MissionFlight.failed_at.is_not(None)))
        )
        assert len(failed) == 1
        assert fleet_availability(session) == (12, 6)
