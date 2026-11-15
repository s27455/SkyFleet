"""Concurrent "recipient unavailable" on PostgreSQL in a temporary database (Feature 018D).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations to a throwaway database, so the development database is never touched.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from app.common.clock import as_utc
from app.config import Settings
from app.events.models import EventType, OperationalEvent
from app.missions import service as missions_service
from app.orders import cancellation
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.service import OrderManagementError
from app.simulation import engine as sim_engine
from app.simulation import service as simulation_service
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.flight import leg_from_dict
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
KIND = EventType.RECIPIENT_UNAVAILABLE


def _mark(factory: sessionmaker, now: datetime | None = None) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            trigger_recipient_unavailable(session, now or datetime.now(UTC), SETTINGS)
        except NoEligibleTargetError:
            return "none"
    return "marked"


def _cancel(factory: sessionmaker, order_id: str) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            cancellation.cancel_order(session, order_id, datetime.now(UTC), SETTINGS)
        except OrderManagementError as error:
            return type(error).__name__
    return "cancelled"


def _fail_drone(factory: sessionmaker) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            trigger_drone_failure(session, datetime.now(UTC), SETTINGS)
        except NoEligibleTargetError:
            return "none"
    return "failed"


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


def _settle(factory: sessionmaker, mission_id: str) -> None:  # type: ignore[type-arg]
    """Let the worker finish the flight, far in the future, as a late worker would."""
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        end = as_utc(flight.started_at) + timedelta(hours=1)
    for _ in range(3):
        sim_engine.advance_flight(factory, SETTINGS, mission_id, end)


def test_concurrent_triggers_mark_one_delivery_once(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-001", "DRN-010")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_mark, factory) for _ in range(6)]
        outcomes = [future.result(timeout=60) for future in futures]

    assert outcomes.count("marked") == 1 and outcomes.count("none") == 5
    assert _count(factory, "ORD-001", KIND) == 0  # nothing failed yet
    _settle(factory, mission_id)
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-001")
        assert order is not None
        assert order.status == OrderStatus.DELIVERY_FAILED.value and order.delivered_at is None
    assert _count(factory, "ORD-001", KIND) == 1  # one outcome, one event


def test_a_trigger_racing_the_worker_at_the_handover_never_gives_both_outcomes(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-002", "DRN-011")
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        attempt = as_utc(flight.started_at) + timedelta(seconds=leg_from_dict(flight.legs[1]).end_s)
    before, after = attempt - timedelta(seconds=1), attempt + timedelta(seconds=1)

    def tick() -> None:
        for _ in range(5):
            sim_engine.advance_flight(factory, SETTINGS, mission_id, after)

    with ThreadPoolExecutor(max_workers=6) as pool:
        ticks = [pool.submit(tick) for _ in range(2)]
        marks = [pool.submit(_mark, factory, before) for _ in range(3)]
        for t in ticks:
            t.result(timeout=120)
        outcomes = [m.result(timeout=120) for m in marks]

    assert outcomes.count("marked") <= 1
    _settle(factory, mission_id)
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-002")
        flight = session.get(MissionFlight, mission_id)
        assert order is not None and flight is not None
        if order.status == OrderStatus.DELIVERED.value:  # the worker delivered first
            assert flight.recipient_unavailable_at is None and flight.handover_failed_at is None
            assert order.delivery_failed_at is None
            assert _count(factory, "ORD-002", KIND) == 0
        else:  # the trigger won the lock: the handover failed, once
            assert order.status == OrderStatus.DELIVERY_FAILED.value
            assert order.delivered_at is None and flight.delivered_at is None
            assert flight.handover_failed_at is not None
            assert _count(factory, "ORD-002", KIND) == 1


def test_a_trigger_racing_a_cancellation_leaves_a_cancelled_order(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-004", "DRN-007")

    with ThreadPoolExecutor(max_workers=8) as pool:
        cancels = [pool.submit(_cancel, factory, "ORD-004") for _ in range(3)]
        marks = [pool.submit(_mark, factory) for _ in range(3)]
        cancel_outcomes = [f.result(timeout=120) for f in cancels]
        mark_outcomes = [f.result(timeout=120) for f in marks]

    assert mark_outcomes.count("marked") <= 1
    assert "cancelled" in cancel_outcomes
    _settle(factory, mission_id)
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-004")
        flight = session.get(MissionFlight, mission_id)
        assert order is not None and flight is not None
        assert order.status == OrderStatus.CANCELLED.value  # a pending mark never beats a recall
        assert order.delivery_failed_at is None and flight.handover_failed_at is None
        assert flight.recalled_at is not None
    assert _count(factory, "ORD-004", KIND) == 0
    assert _count(factory, "ORD-004", EventType.ORDER_CANCELLED) == 1


def test_a_trigger_racing_a_drone_failure_leaves_an_interrupted_order(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-005", "DRN-008")

    with ThreadPoolExecutor(max_workers=8) as pool:
        failures = [pool.submit(_fail_drone, factory) for _ in range(3)]
        marks = [pool.submit(_mark, factory) for _ in range(3)]
        failure_outcomes = [f.result(timeout=120) for f in failures]
        mark_outcomes = [f.result(timeout=120) for f in marks]

    assert failure_outcomes.count("failed") == 1
    assert mark_outcomes.count("marked") <= 1
    _settle(factory, mission_id)
    with factory() as session:
        order = session.get(DeliveryOrder, "ORD-005")
        flight = session.get(MissionFlight, mission_id)
        assert order is not None and flight is not None
        assert flight.failed_at is not None and flight.handover_failed_at is None
        assert order.status == OrderStatus.OUT_FOR_DELIVERY.value  # interrupted, never failed
        assert order.delivery_failed_at is None
    assert _count(factory, "ORD-005", KIND) == 0
    assert _count(factory, "ORD-005", EventType.DRONE_FAILURE) == 1
