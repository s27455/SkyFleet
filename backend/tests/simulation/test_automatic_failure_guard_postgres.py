"""The automatic drone failure guard under concurrency on PostgreSQL (Feature 021D-2).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations (0017 included) to a throwaway database, so the development database is never touched.
Its own module, so the grounded drones set up here do not leak into other tests.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.missions import service as missions_service
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
PAIRS = [
    ("ORD-009", "DRN-001"),
    ("ORD-007", "DRN-004"),
    ("ORD-004", "DRN-007"),
    ("ORD-001", "DRN-010"),
]
FLYING = {drone for _, drone in PAIRS}


def _launch(factory: sessionmaker[Session], order_id: str, drone_id: str) -> str:
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission.id, now, SETTINGS)
        return mission.id


def _automatic(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        try:
            trigger_drone_failure(
                session,
                datetime.now(UTC),
                SETTINGS,
                origin=EventOrigin.AUTOMATIC,
                automatic_safety=True,
            )
        except FleetGuardError:
            return "guard"
        except NoEligibleTargetError:
            return "none"
    return "failed"


def test_overlapping_automatic_failures_cannot_pass_the_guard_together(
    temp_engine: Engine,
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

    attempts = 8
    barrier = threading.Barrier(attempts)

    def attempt() -> str:
        barrier.wait()  # start together to provoke the race
        return _automatic(factory)

    with ThreadPoolExecutor(max_workers=attempts) as pool:
        futures = [pool.submit(attempt) for _ in range(attempts)]
        outcomes = [future.result(timeout=60) for future in futures]

    assert outcomes.count("failed") == 1  # never two
    assert outcomes.count("failed") + outcomes.count("guard") + outcomes.count("none") == attempts
    assert outcomes.count("guard") >= 1
    with factory() as session:
        failed = list(
            session.scalars(select(MissionFlight).where(MissionFlight.failed_at.is_not(None)))
        )
        assert len(failed) == 1
        events = session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(OperationalEvent.event_type == EventType.DRONE_FAILURE.value)
        )
        assert events == 1
        total, unavailable = fleet_availability(session)
        assert (total, unavailable) == (12, 6)  # exactly half the fleet is still operational
        assert total - unavailable >= 6
