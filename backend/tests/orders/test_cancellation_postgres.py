"""Concurrent cancellation on PostgreSQL in a temporary database (Feature 018B).

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


def _cancel(factory: sessionmaker, order_id: str) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            cancellation.cancel_order(session, order_id, datetime.now(UTC), SETTINGS)
        except OrderManagementError as error:
            return type(error).__name__
    return "cancelled"


def _events(factory: sessionmaker, order_id: str) -> int:  # type: ignore[type-arg]
    with factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(
                    OperationalEvent.order_id == order_id,
                    OperationalEvent.event_type == EventType.ORDER_CANCELLED.value,
                )
            )
            or 0
        )


def test_concurrent_cancellations_of_a_pending_order_record_one_event(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_cancel, factory, "ORD-002") for _ in range(6)]
        results = [future.result(timeout=60) for future in futures]

    assert set(results) == {"cancelled"}  # every call succeeds; the repeats are idempotent
    assert _events(factory, "ORD-002") == 1
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-002")
        assert order is not None and order.status == OrderStatus.CANCELLED.value


def test_cancellation_racing_the_worker_keeps_the_order_flight_and_events_consistent(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, "ORD-001", "DRN-010", SETTINGS)
        mission_id = mission.id
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission_id, now, SETTINGS)

    def tick() -> None:
        for _ in range(20):
            sim_engine.advance_flight(factory, SETTINGS, mission_id, datetime.now(UTC))

    with ThreadPoolExecutor(max_workers=8) as pool:
        ticks = [pool.submit(tick) for _ in range(2)]
        cancels = [pool.submit(_cancel, factory, "ORD-001") for _ in range(5)]
        outcomes = [f.result(timeout=120) for f in cancels]
        for t in ticks:
            t.result(timeout=120)

    assert set(outcomes) <= {"cancelled", "OrderAlreadyDeliveredError"}
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-001")
        flight = session.get(MissionFlight, mission_id)
        assert order is not None and flight is not None
        if order.status == OrderStatus.CANCELLED.value:
            assert flight.recalled_at is not None and flight.delivered_at is None
            assert order.delivered_at is None
            assert len(flight.legs) == 2  # one cut leg and exactly one recall leg
            assert _events(factory, "ORD-001") == 1
        else:  # the worker delivered first: nothing about the cancellation may be recorded
            assert order.status == OrderStatus.DELIVERED.value
            assert flight.recalled_at is None and order.cancelled_at is None
            assert _events(factory, "ORD-001") == 0
