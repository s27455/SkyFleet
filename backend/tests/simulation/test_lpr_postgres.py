"""LPR helicopter scenario on PostgreSQL in a temporary database (Feature 018E).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations to a throwaway database, so the development database is never touched.
"""

import random
import threading
import time
from collections.abc import Iterator
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
from app.simulation import lpr
from app.simulation import service as simulation_service
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.flight import leg_from_dict
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import LprScenario, LprStatus, MissionFlight

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


def _start(factory: sessionmaker, now: datetime) -> str:  # type: ignore[type-arg]
    with factory() as session:
        try:
            lpr.start_scenario(session, now, SETTINGS)
        except lpr.LprAlreadyActiveError:
            return "active"
    return "started"


def _complete(factory: sessionmaker, now: datetime) -> bool:  # type: ignore[type-arg]
    with factory() as session:
        return lpr.complete_due(session, now)


@pytest.fixture(autouse=True)
def _no_leftover_scenario(temp_engine: Engine) -> Iterator[None]:
    """The temporary database is shared by this module: no scenario is active between tests."""
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    _complete(factory, tomorrow)
    yield
    _complete(factory, tomorrow)


def _events(factory: sessionmaker, phase: str) -> int:  # type: ignore[type-arg]
    with factory() as session:
        rows = session.scalars(
            select(OperationalEvent).where(
                OperationalEvent.event_type == EventType.LPR_TRANSIT.value,
                OperationalEvent.order_id.is_(None),
            )
        )
        return sum(1 for row in rows if row.details and row.details["phase"] == phase)


def test_concurrent_triggers_start_one_scenario_only(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    now = datetime.now(UTC)
    started_before = _events(factory, "STARTED")

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = [
            f.result(timeout=60) for f in [pool.submit(_start, factory, now) for _ in range(8)]
        ]

    assert outcomes.count("started") == 1 and outcomes.count("active") == 7
    with factory() as session:
        rows = session.scalars(select(LprScenario)).all()
        assert [row.status for row in rows] == [LprStatus.ACTIVE.value]
    assert _events(factory, "STARTED") - started_before == 1  # the losers wrote nothing


def test_completion_racing_a_new_trigger_leaves_one_active_and_one_completed_event(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with factory() as session:  # the previous scenario, which is over by the time of the race
        old = lpr.start_scenario(session, datetime.now(UTC) - timedelta(hours=1), SETTINGS)
        old_id = old.id
    later = datetime.now(UTC)
    completed_before = _events(factory, "COMPLETED")

    with ThreadPoolExecutor(max_workers=8) as pool:
        completions = [pool.submit(_complete, factory, later) for _ in range(4)]
        starts = [pool.submit(_start, factory, later) for _ in range(3)]
        [f.result(timeout=60) for f in completions]
        outcomes = [f.result(timeout=60) for f in starts]

    assert outcomes.count("started") == 1  # exactly one new scenario
    with factory() as session:
        statuses = {row.id: row.status for row in session.scalars(select(LprScenario))}
        assert statuses[old_id] == LprStatus.COMPLETED.value
        assert list(statuses.values()).count(LprStatus.ACTIVE.value) == 1
    assert _events(factory, "COMPLETED") - completed_before == 1  # however many workers saw it end


def _launch(factory: sessionmaker, order_id: str, drone_id: str) -> str:  # type: ignore[type-arg]
    now = datetime.now(UTC)
    with factory() as session:
        mission = missions_service.confirm_mission(session, order_id, drone_id, SETTINGS)
        record_heartbeat(session, now)
        simulation_service.start_mission(session, mission.id, now, SETTINGS)
        return mission.id


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


def test_yielding_racing_cancellation_failure_and_marking_stays_consistent(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    mission_id = _launch(factory, "ORD-003", "DRN-011")
    real_now = datetime.now(UTC)
    # The helicopter reaches the delivery corridor about 4 s after the flight starts.
    share = (18.606 - lpr.ROUTE_START[0]) / (lpr.ROUTE_END[0] - lpr.ROUTE_START[0])
    started = (
        real_now
        + timedelta(seconds=4)
        - timedelta(seconds=share * lpr.route_length_m() / SETTINGS.sim_lpr_speed_ms)
    )
    with factory() as session:
        lpr.start_scenario(session, started, SETTINGS)
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            sim_engine.advance_flight(factory, SETTINGS, mission_id, datetime.now(UTC))
            time.sleep(0.15)

    def cancel() -> str:
        with factory() as session:
            try:
                cancellation.cancel_order(session, "ORD-003", datetime.now(UTC), SETTINGS)
            except OrderManagementError as error:
                return type(error).__name__
        return "cancelled"

    def fail() -> str:
        with factory() as session:
            try:
                trigger_drone_failure(session, datetime.now(UTC), SETTINGS, rng=random.Random(1))
            except NoEligibleTargetError:
                return "none"
        return "failed"

    def mark() -> str:
        with factory() as session:
            try:
                trigger_recipient_unavailable(session, datetime.now(UTC), SETTINGS)
            except NoEligibleTargetError:
                return "none"
        return "marked"

    with ThreadPoolExecutor(max_workers=12) as pool:
        ticks = [pool.submit(worker) for _ in range(2)]
        time.sleep(5.5)  # the drone is yielding now
        results = [
            pool.submit(mark),
            pool.submit(cancel),
            pool.submit(cancel),
            pool.submit(fail),
            pool.submit(mark),
        ]
        time.sleep(3)
        outcomes = [r.result(timeout=120) for r in results]
        stop.set()
        for t in ticks:
            t.result(timeout=60)

    # Let the worker finish the flight as a late one would, with the scenario long over.
    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        assert flight is not None
        end = as_utc(flight.started_at) + timedelta(hours=1)
    for _ in range(4):
        sim_engine.advance_flight(factory, SETTINGS, mission_id, end)

    with factory() as session:
        flight = session.get(MissionFlight, mission_id)
        order = session.get(DeliveryOrder, "ORD-003")
        assert flight is not None and order is not None
        legs = [leg_from_dict(entry) for entry in flight.legs]
        # The schedule is intact: contiguous, in order, whatever was inserted or cut.
        for earlier, later in zip(legs, legs[1:], strict=False):
            assert later.start_s == pytest.approx(earlier.end_s, abs=1e-6)
        failed = flight.failed_at is not None
        assert failed == (outcomes.count("failed") == 1)
        if failed:
            assert flight.handover_failed_at is None or order.status == "DELIVERY_FAILED"
            assert order.status in {"OUT_FOR_DELIVERY", "DELIVERY_FAILED", "CANCELLED"}
        if order.status == OrderStatus.CANCELLED.value:
            assert order.delivered_at is None and order.delivery_failed_at is None
        if order.status == OrderStatus.DELIVERY_FAILED.value:
            assert order.delivered_at is None
    for kind in (
        EventType.DRONE_FAILURE,
        EventType.ORDER_CANCELLED,
        EventType.RECIPIENT_UNAVAILABLE,
    ):
        assert _count(factory, "ORD-003", kind) <= 1
    assert _count(factory, "ORD-003", EventType.LPR_TRANSIT) <= 1  # one yield event per mission
