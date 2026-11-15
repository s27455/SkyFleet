"""Random Incidents mode: the operator-controlled switch shared by the API and the worker.

The mode is one database row (`IncidentSchedulerState`), because the API toggles it and the worker,
the scheduler's only owner, reads it. A missing row means OFF, and the worker resets it to OFF
whenever it starts, so no incident happens just because the system started. It is independent of
Automatic Dispatch and Order Simulation (each has its own state): every read and write here is by
this feature's own row name. The scheduling itself lives in `incident_scheduler.py`.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.common.clock import as_utc
from app.config import Settings
from app.simulation import heartbeat
from app.simulation.models import RANDOM_INCIDENTS, IncidentSchedulerState
from app.simulation.schemas import RandomIncidentsStatus
from app.simulation.service import WorkerUnavailableError

MAX_OUTCOME_LENGTH = 255


def _row(session: Session) -> IncidentSchedulerState | None:
    return session.get(IncidentSchedulerState, RANDOM_INCIDENTS)


def _set_enabled(session: Session, enabled: bool, now: datetime, outcome: str | None) -> None:
    for attempt in range(2):
        row = _row(session)
        if row is None:
            row = IncidentSchedulerState(name=RANDOM_INCIDENTS, enabled=enabled, updated_at=now)
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


def get_status(session: Session, now: datetime, settings: Settings) -> RandomIncidentsStatus:
    row = _row(session)
    running = worker_is_running(session, now, settings)
    return RandomIncidentsStatus(
        enabled=bool(row and row.enabled) and running,
        worker_running=running,
        last_check_at=as_utc(row.last_check_at) if row and row.last_check_at else None,
        last_outcome=row.last_outcome if row else None,
    )


def enable(session: Session, now: datetime, settings: Settings) -> RandomIncidentsStatus:
    """Turn the mode ON (idempotent). Refused while no simulation worker is alive.

    Enabling schedules nothing by itself: the worker's first look at the ON mode only starts the
    first random pause, so no incident follows immediately.
    """
    beat = heartbeat.last_heartbeat(session)
    if not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds):
        session.rollback()
        raise WorkerUnavailableError(beat, settings.sim_heartbeat_stale_seconds)
    _set_enabled(session, True, now, None)
    return get_status(session, now, settings)


def disable(session: Session, now: datetime, settings: Settings) -> RandomIncidentsStatus:
    """Turn the mode OFF (idempotent). An incident already in progress is not undone."""
    _set_enabled(session, False, now, None)
    return get_status(session, now, settings)


def reset_to_off(session: Session, now: datetime) -> None:
    """Called when the worker starts: no incident happens just because the system started."""
    _set_enabled(session, False, now, "Reset to OFF when the simulation worker started")


def is_enabled(factory: sessionmaker[Session]) -> bool:
    """The current stored mode, read in its own short transaction."""
    with factory() as session:
        return bool(
            session.scalar(
                select(IncidentSchedulerState.enabled).where(
                    IncidentSchedulerState.name == RANDOM_INCIDENTS
                )
            )
        )


def record_attempt(factory: sessionmaker[Session], now: datetime, outcome: str) -> bool:
    """Store the attempt summary; returns True when it differs from the previous one.

    Only the state row is written: a skipped attempt is not a mission event.
    """
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
