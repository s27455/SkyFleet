"""Concurrent drone failure on PostgreSQL in a temporary database (Feature 018C).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations to a throwaway database, so the development database is never touched.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.events.models import EventType, OperationalEvent
from app.missions import service as missions_service
from app.orders import cancellation
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.service import OrderManagementError
from app.simulation import engine as sim_engine
from app.simulation import service as simulation_service
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import FlightPhase, MissionFlight

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


def _trigger(factory: sessionmaker) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            trigger_drone_failure(session, datetime.now(UTC), SETTINGS)
        except NoEligibleTargetError:
            return "none"
    return "failed"


def _cancel(factory: sessionmaker, order_id: str) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            cancellation.cancel_order(session, order_id, datetime.now(UTC), SETTINGS)
        except OrderManagementError as error:
            return type(error).__name__
    return "cancelled"


def _count(factory: sessionmaker, order_id: str, kind: EventType) -> int:  # type: ignore[type-arg]
    with factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(
                    OperationalEvent.order_id == order_id,
                    OperationalEvent.event_type == kind.value,
                )
            )
            or 0
        )


def _launch(factory: sessionmaker, order_id: str, drone_id: str) -> str:  # type: ignore[type-arg]
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission.id, now, SETTINGS)
        return mission.id


def test_concurrent_triggers_fail_one_drone_once(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-001", "DRN-010")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_trigger, factory) for _ in range(6)]
        outcomes = [future.result(timeout=60) for future in futures]

    assert outcomes.count("failed") == 1 and outcomes.count("none") == 5
    assert _count(factory, "ORD-001", EventType.DRONE_FAILURE) == 1
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        assert flight.failed_at is not None
        assert flight.phase == FlightPhase.EMERGENCY_APPROACH.value


def test_failure_cancellation_and_worker_ticks_racing_stay_consistent(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-004", "DRN-007")

    def tick() -> None:
        for _ in range(20):
            sim_engine.advance_flight(factory, SETTINGS, mission_id, datetime.now(UTC))

    with ThreadPoolExecutor(max_workers=10) as pool:
        ticks = [pool.submit(tick) for _ in range(2)]
        cancels = [pool.submit(_cancel, factory, "ORD-004") for _ in range(3)]
        triggers = [pool.submit(_trigger, factory) for _ in range(3)]
        cancel_outcomes = [f.result(timeout=120) for f in cancels]
        trigger_outcomes = [f.result(timeout=120) for f in triggers]
        for t in ticks:
            t.result(timeout=120)

    assert trigger_outcomes.count("failed") <= 1
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-004")
        flight = session.get(MissionFlight, mission_id)
        assert order is not None and flight is not None
        failed = flight.failed_at is not None
        cancelled = order.status == OrderStatus.CANCELLED.value
        # Each incident is recorded exactly when it happened, and only once.
        assert _count(factory, "ORD-004", EventType.DRONE_FAILURE) == (1 if failed else 0)
        assert _count(factory, "ORD-004", EventType.ORDER_CANCELLED) == (1 if cancelled else 0)
        assert failed == (trigger_outcomes.count("failed") == 1)
        if cancelled:
            assert flight.recalled_at is not None  # the cancellation always recalled the drone
        else:
            assert set(cancel_outcomes) <= {"DroneFailedError", "OrderNotCancellableError"}
        if failed:
            assert flight.phase in (
                FlightPhase.EMERGENCY_APPROACH.value,
                FlightPhase.EMERGENCY.value,
            )
            assert order.status != OrderStatus.DELIVERED.value  # the delivery never completed
