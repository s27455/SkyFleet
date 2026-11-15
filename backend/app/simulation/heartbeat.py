"""The worker's heartbeat: the simplest reliable "is the simulation running?" signal.

The worker writes the time of every tick to one database row (the database is the bridge between
the API and the worker, see ADR 0002). Starting a mission requires a fresh heartbeat. Both sides
use the application clock on the same machine; the staleness limit is generous compared with the
tick interval, so small clock differences do not matter.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.common.clock import as_utc
from app.simulation.models import WORKER_HEARTBEAT, SimulationHeartbeat


def record_heartbeat(session: Session, now: datetime) -> None:
    row = session.get(SimulationHeartbeat, WORKER_HEARTBEAT)
    if row is None:
        session.add(SimulationHeartbeat(name=WORKER_HEARTBEAT, beat_at=now))
    else:
        row.beat_at = now
    session.commit()


def last_heartbeat(session: Session) -> datetime | None:
    row = session.get(SimulationHeartbeat, WORKER_HEARTBEAT)
    return as_utc(row.beat_at) if row is not None else None


def is_fresh(beat: datetime | None, now: datetime, max_age_seconds: float) -> bool:
    return beat is not None and (now - beat).total_seconds() <= max_age_seconds
