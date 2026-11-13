"""Automatic order generation: the operator-controlled mode and the step the worker runs.

The mode is one database row (`OrderSimulationState`), because the API toggles it and the worker,
the loop's only owner, reads it; a missing row means OFF, and the worker resets it to OFF whenever
it starts. It is independent of Automatic Dispatch. While ON, the worker creates one ordinary
`READY_FOR_PICKUP` order per opportunity with the 015A `generate_one_order`; nothing here duplicates
order creation.

Timing lives in the worker's memory (`GenerationSchedule`): one random pause after the mode is
seen ON, then a new random pause after every opportunity. Because only the next due time is kept
and it is always recomputed from "now", a restart or a long stall can never cause a burst of
catch-up orders. Generation pauses while the number of outstanding (`READY_FOR_PICKUP`) orders is at
the configured limit; no order is ever deleted or changed.
"""

import logging
import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.orders import repository
from app.orders.generator import generate_one_order
from app.orders.models import ORDER_SIMULATION, OrderSimulationState
from app.orders.schemas import OrderSimulationStatus
from app.simulation import heartbeat
from app.simulation.clock import as_utc
from app.simulation.service import WorkerUnavailableError

logger = logging.getLogger("skyfleet.orders")

MAX_OUTCOME_LENGTH = 255


def _row(session: Session) -> OrderSimulationState | None:
    return session.get(OrderSimulationState, ORDER_SIMULATION)


def _set_enabled(session: Session, enabled: bool, now: datetime, outcome: str | None) -> None:
    for attempt in range(2):
        row = _row(session)
        if row is None:
            row = OrderSimulationState(name=ORDER_SIMULATION, enabled=enabled, updated_at=now)
            session.add(row)
        row.enabled = enabled
        row.updated_at = now
        if outcome is not None:
            row.last_outcome = outcome[:MAX_OUTCOME_LENGTH]
        try:
            session.commit()
            return
        except IntegrityError:  # two first-ever writes raced to create the row; update it instead
            session.rollback()
            if attempt == 1:
                raise


def worker_is_running(session: Session, now: datetime, settings: Settings) -> bool:
    return heartbeat.is_fresh(
        heartbeat.last_heartbeat(session), now, settings.sim_heartbeat_stale_seconds
    )


def get_status(session: Session, now: datetime, settings: Settings) -> OrderSimulationStatus:
    row = _row(session)
    running = worker_is_running(session, now, settings)
    return OrderSimulationStatus(
        enabled=bool(row and row.enabled) and running,
        worker_running=running,
        last_check_at=as_utc(row.last_check_at) if row and row.last_check_at else None,
        last_outcome=row.last_outcome if row else None,
        outstanding_orders=repository.count_ready_orders(session),
        max_outstanding_orders=settings.order_sim_max_outstanding_orders,
    )


def enable(session: Session, now: datetime, settings: Settings) -> OrderSimulationStatus:
    """Turn the mode ON (idempotent). Refused while no simulation worker is alive."""
    beat = heartbeat.last_heartbeat(session)
    if not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds):
        session.rollback()
        raise WorkerUnavailableError(beat, settings.sim_heartbeat_stale_seconds)
    _set_enabled(session, True, now, None)
    return get_status(session, now, settings)


def disable(session: Session, now: datetime, settings: Settings) -> OrderSimulationStatus:
    """Turn the mode OFF (idempotent). Existing orders are untouched."""
    _set_enabled(session, False, now, None)
    return get_status(session, now, settings)


def reset_to_off(session: Session, now: datetime) -> None:
    """Called when the worker starts: no order is generated just because the system started."""
    _set_enabled(session, False, now, "Reset to OFF when the simulation worker started")


def is_enabled(factory: sessionmaker[Session]) -> bool:
    """The current stored mode, read in its own short transaction."""
    with factory() as session:
        return bool(session.scalar(select(OrderSimulationState.enabled)))


class GenerationSchedule:
    """When the next order is due, kept in the worker's memory (monotonic seconds)."""

    def __init__(self, settings: Settings, rng: random.Random | None = None) -> None:
        self._min = settings.order_sim_min_interval_seconds
        self._max = settings.order_sim_max_interval_seconds
        self._rng = rng or random.Random()
        self._next_at: float | None = None

    def _pause(self) -> float:
        return self._rng.uniform(self._min, self._max)

    def poll(self, enabled: bool, now: float) -> bool:
        """True when an order is due now. Turning OFF forgets the schedule, and the first poll
        after turning ON only schedules, so enabling never produces an immediate order."""
        if not enabled:
            self._next_at = None
            return False
        if self._next_at is None:
            self._next_at = now + self._pause()
            return False
        if now < self._next_at:
            return False
        self._next_at = now + self._pause()  # from now, never from the missed due time
        return True


def _record(factory: sessionmaker[Session], now: datetime, outcome: str) -> bool:
    """Store the attempt summary; returns True when it differs from the previous one."""
    outcome = outcome[:MAX_OUTCOME_LENGTH]
    with factory() as session:
        row = _row(session)
        if row is None:
            return False
        changed = row.last_outcome != outcome
        row.last_check_at = now
        row.last_outcome = outcome
        session.commit()
        return changed


def run_generation_step(
    factory: sessionmaker[Session],
    settings: Settings,
    now: datetime,
    rng: random.Random | None = None,
) -> str | None:
    """One generation opportunity; returns its summary, or None when the mode is OFF.

    Never raises for a generation problem: it is recorded as the outcome and the next scheduled
    opportunity simply tries again. `create_order` rolls back on error, so no partial order stays.
    """
    if not is_enabled(factory):
        return None

    error: Exception | None = None
    with factory() as session:
        outstanding = repository.count_ready_orders(session)
    limit = settings.order_sim_max_outstanding_orders
    if outstanding >= limit:
        outcome = f"Paused: {outstanding} outstanding orders (limit {limit})"
    elif not is_enabled(factory):  # disabled meanwhile: create nothing
        return None
    else:
        try:
            with factory() as session:
                order = generate_one_order(session, rng=rng)
            outcome = (
                f"Created {order.id}: {order.destination_address}, {order.package_weight_kg} kg"
            )
        except Exception as caught:
            error = caught
            outcome = f"Generation failed ({type(caught).__name__}); will retry"

    # Log only when something changed, so a capped or failing generator does not repeat itself.
    if _record(factory, now, outcome):
        if error is not None:
            logger.error("Order generation: %s", outcome, exc_info=error)
        else:
            logger.info("Order generation: %s", outcome)
    return outcome
