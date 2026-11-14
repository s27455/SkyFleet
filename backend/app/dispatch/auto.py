"""Automatic dispatch: the operator-controlled mode and the pass the simulation worker runs.

The mode is one database row (`DispatchAutoState`), because the API toggles it and the worker, the
loop's only owner, reads it; a missing row means OFF, and the worker resets it to OFF whenever it
starts. A pass takes the 014A recommendations and executes each pair with the 014B
`execute_dispatch`, so selection, planner rules, locks and duplicate prevention are reused, not
repeated. The mode is read again before every execution: disabling stops further attempts at once,
while an execution already running may finish. Flights already started are never touched.

After dispatching, the same pass may move one spare drone to a Hub that has orders waiting and no
drone (Feature 019B, `app.dispatch.rebalancing`); the mode, its OFF default and the reset at worker
start are the same, so OFF means no new dispatch and no new relocation.

Every failure is a controlled outcome summarised in one short line; one bad pair never stops the
others, and nothing is cancelled or compensated automatically (a mission whose start failed stays
ASSIGNED and is reported).
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch.models import AUTO_DISPATCH, DispatchAutoState
from app.dispatch.rebalancing import run_rebalancing
from app.dispatch.schemas import AutoDispatchStatus
from app.dispatch.service import DispatchStartFailedError, execute_dispatch, recommend_for_session
from app.missions.service import MissionError
from app.simulation import heartbeat
from app.simulation.clock import as_utc
from app.simulation.service import WorkerUnavailableError

logger = logging.getLogger("skyfleet.dispatch")

MAX_OUTCOME_LENGTH = 255


def _row(session: Session) -> DispatchAutoState | None:
    return session.get(DispatchAutoState, AUTO_DISPATCH)


def _set_enabled(session: Session, enabled: bool, now: datetime, outcome: str | None) -> None:
    row = _row(session)
    if row is None:
        row = DispatchAutoState(name=AUTO_DISPATCH, enabled=enabled, updated_at=now)
        session.add(row)
    row.enabled = enabled
    row.updated_at = now
    if outcome is not None:
        row.last_outcome = outcome[:MAX_OUTCOME_LENGTH]
    session.commit()


def worker_is_running(session: Session, now: datetime, settings: Settings) -> bool:
    return heartbeat.is_fresh(
        heartbeat.last_heartbeat(session), now, settings.sim_heartbeat_stale_seconds
    )


def get_status(session: Session, now: datetime, settings: Settings) -> AutoDispatchStatus:
    row = _row(session)
    running = worker_is_running(session, now, settings)
    return AutoDispatchStatus(
        enabled=bool(row and row.enabled) and running,
        worker_running=running,
        last_check_at=as_utc(row.last_check_at) if row and row.last_check_at else None,
        last_outcome=row.last_outcome if row else None,
    )


def enable(session: Session, now: datetime, settings: Settings) -> AutoDispatchStatus:
    """Turn the mode ON (idempotent). Refused while no simulation worker is alive."""
    beat = heartbeat.last_heartbeat(session)
    if not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds):
        session.rollback()
        raise WorkerUnavailableError(beat, settings.sim_heartbeat_stale_seconds)
    _set_enabled(session, True, now, None)
    return get_status(session, now, settings)


def disable(session: Session, now: datetime, settings: Settings) -> AutoDispatchStatus:
    """Turn the mode OFF (idempotent). Started flights and missions are untouched."""
    _set_enabled(session, False, now, None)
    return get_status(session, now, settings)


def reset_to_off(session: Session, now: datetime) -> None:
    """Called when the worker starts: nothing is dispatched just because the system started."""
    _set_enabled(session, False, now, "Reset to OFF when the simulation worker started")


def is_enabled(factory: sessionmaker[Session]) -> bool:
    """The current stored mode, read in its own short transaction."""
    with factory() as session:
        return bool(session.scalar(select(DispatchAutoState.enabled)))


def _record(factory: sessionmaker[Session], now: datetime, outcome: str) -> bool:
    """Store the pass summary; returns True when it differs from the previous one."""
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


def run_dispatch_pass(
    factory: sessionmaker[Session], settings: Settings, now: datetime
) -> str | None:
    """One pass; returns its summary, or None when the mode is OFF (nothing is done or written)."""
    if not is_enabled(factory):
        return None

    with factory() as session:
        result = recommend_for_session(session, settings)

    started = 0
    skipped = 0
    problems: list[str] = []
    for recommendation in result.recommendations:
        if not is_enabled(factory):  # disabled meanwhile: no further attempts
            problems.append("stopped because the mode was turned OFF")
            break
        with factory() as session:
            try:
                execute_dispatch(
                    session, recommendation.order_id, recommendation.drone_id, now, settings
                )
                started += 1
            except WorkerUnavailableError:
                problems.append("simulation worker unavailable; will retry")
                break
            except DispatchStartFailedError as error:
                problems.append(f"mission {error.mission_id} created but not started")
            except MissionError:
                skipped += 1  # no longer eligible (state changed since the recommendation)
            except Exception:
                logger.exception(
                    "Dispatch of %s with %s failed",
                    recommendation.order_id,
                    recommendation.drone_id,
                )
                problems.append(f"unexpected error dispatching {recommendation.order_id}")

    # Feature 019B: after dispatching, the same pass may move one spare drone to a Hub that has
    # orders waiting and no drone. Skipped when the worker was found unavailable.
    rebalanced: str | None = None
    if not any("worker unavailable" in problem for problem in problems):
        rebalanced = run_rebalancing(factory, settings, now, lambda: is_enabled(factory))

    parts: list[str] = []
    if started:
        parts.append(f"Started {started} mission(s)")
    if skipped:
        parts.append(f"{skipped} no longer eligible")
    if rebalanced:
        parts.append(rebalanced)
    parts.extend(problems)
    if not parts:
        waiting = len(result.pending)
        parts.append(
            f"Nothing to dispatch; {waiting} order(s) waiting" if waiting else "Nothing to dispatch"
        )
    outcome = "; ".join(parts)

    # Log only when something changed, so a blocked order does not repeat itself every pass.
    if _record(factory, now, outcome):
        logger.info("Automatic dispatch: %s", outcome)
    return outcome
