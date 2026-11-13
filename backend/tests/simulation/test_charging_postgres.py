"""Charging against concurrent mission confirmation, on PostgreSQL in a temporary database (014D).

Opt-in (`uv run pytest -m postgres`) with the `temp_engine` fixture: the real migrations run in a
uniquely named database on the local Docker PostgreSQL, which is dropped afterwards. The development
database is never touched; an unreachable server skips the tests. Each test uses its own drones.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.missions import service as missions_service
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.simulation.charging import ChargingState, charge_step

pytestmark = pytest.mark.postgres

SETTINGS = Settings(
    mission_payload_energy_factor=0.5, hub_dock_proximity_m=50, sim_charge_rate_pct_per_minute=600
)
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def race(actions: list[Callable[[], str]]) -> list[str]:
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], str]) -> str:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(run, a) for a in actions]]


def confirm(factory: sessionmaker[Session], order_id: str, drone_id: str) -> Callable[[], str]:
    def action() -> str:
        with factory() as session:
            try:
                missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
            except missions_service.PlanRejectedError:
                return "rejected"
            return "assigned"

    return action


def charge(factory: sessionmaker[Session]) -> Callable[[], str]:
    def action() -> str:
        charge_step(factory, SETTINGS, NOW, ChargingState())
        return "charged"

    return action


def assert_never_both(factory: sessionmaker[Session], drone_ids: list[str]) -> None:
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    with factory() as session:
        for drone_id in drone_ids:
            drone = session.get(Drone, drone_id)
            assert drone is not None
            assigned = session.scalars(
                select(Mission).where(Mission.drone_id == drone_id, Mission.status.in_(active))
            ).first()
            # A drone is either claimed by a mission or charging, never both.
            assert not (assigned is not None and drone.status == DroneStatus.CHARGING), drone_id


def test_charging_never_overlaps_a_mission_confirmed_at_the_same_moment(
    factory: sessionmaker[Session],
) -> None:
    pairs = [
        ("ORD-004", "DRN-008"),  # Forum, 90 %
        ("ORD-005", "DRN-009"),  # Forum, 80 %
        ("ORD-001", "DRN-011"),  # Bałtycka, 90 %
        ("ORD-002", "DRN-012"),  # Bałtycka, 80 %
    ]

    outcomes = race([confirm(factory, order, drone) for order, drone in pairs] + [charge(factory)])

    assert "charged" in outcomes
    assert_never_both(factory, [drone for _, drone in pairs])


def test_overlapping_charging_steps_keep_the_battery_in_range(
    factory: sessionmaker[Session],
) -> None:
    race([charge(factory) for _ in range(4)])  # two workers by mistake: redundant, not corrupt
    race([charge(factory) for _ in range(4)])

    with factory() as session:
        for drone in session.scalars(select(Drone)):
            assert 0 <= drone.battery_pct <= 100
            assert drone.status in {DroneStatus.IDLE, DroneStatus.CHARGING}


def test_a_drone_charges_to_exactly_100_and_becomes_idle(
    factory: sessionmaker[Session],
) -> None:
    drone_id = "DRN-006"  # Riviera, 80 %
    state = ChargingState()

    for second in range(0, 6):
        charge_step(factory, SETTINGS, NOW + timedelta(seconds=second), state)

    with factory() as session:
        drone = session.get(Drone, drone_id)
        assert drone is not None
        assert (drone.status, drone.battery_pct) == (DroneStatus.IDLE, 100)
