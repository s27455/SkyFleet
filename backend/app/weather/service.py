"""The rain warning (Feature 020): a persisted global restriction on NEW takeoffs only.

Takeoff gate and race safety: every code path that starts a flight (`start_mission`,
`start_relocation`) calls `lock_for_takeoff` as the first lock of its transaction. It reads the
state row FOR SHARE and refuses while the warning is active. Activation takes the same row FOR
UPDATE, so it waits for takeoffs that already hold the share lock and commits before any later
takeoff can look; no takeoff is committed after the warning became active. Activation touches no
domain row, so these locks cannot form a cycle.

Flights already airborne are never affected: the worker and the flight engine do not call this
module. Activation and clearing are idempotent: a repeated request changes nothing and records no
second event.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.missions.service import MissionError
from app.simulation.clock import as_utc
from app.weather.models import RAIN_WARNING, WeatherState

REASON_ACTIVATED = "Rain warning activated: new takeoffs are suspended"
REASON_CLEARED = "Rain warning cleared: new takeoffs are allowed again"


class RainWarningActiveError(MissionError):
    def __init__(self) -> None:
        super().__init__(
            "Takeoff is prohibited: a rain warning is active. Flights already in the air continue; "
            "new takeoffs resume when the warning is cleared"
        )


@dataclass(frozen=True)
class RainWarningStatus:
    active: bool
    activated_at: datetime | None
    cleared_at: datetime | None
    origin: str | None


def _status(row: WeatherState | None) -> RainWarningStatus:
    if row is None:
        return RainWarningStatus(False, None, None, None)
    return RainWarningStatus(
        row.active,
        as_utc(row.activated_at) if row.activated_at else None,
        as_utc(row.cleared_at) if row.cleared_at else None,
        row.origin,
    )


def _select(lock: str | None = None) -> Select[Any]:
    statement = select(WeatherState).where(WeatherState.name == RAIN_WARNING)
    if lock == "share":
        statement = statement.with_for_update(read=True)
    elif lock == "update":
        statement = statement.with_for_update()
    return statement.execution_options(populate_existing=True)


def get_status(session: Session) -> RainWarningStatus:
    """The committed state, without a lock (read-only views)."""
    return _status(session.scalars(_select()).one_or_none())


def is_active(session: Session) -> bool:
    return get_status(session).active


def lock_for_takeoff(session: Session) -> None:
    """Call first in a takeoff transaction (before any domain row lock); raises while active."""
    row = session.scalars(_select("share")).one_or_none()
    if row is not None and row.active:
        raise RainWarningActiveError


def _ensure_row(session: Session) -> None:
    """Create the INACTIVE row if absent (the migration seeds it); safe against a concurrent one."""
    insert = postgresql_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    session.execute(
        insert(WeatherState)
        .values(name=RAIN_WARNING, active=False)
        .on_conflict_do_nothing(index_elements=["name"])
    )


def _change(
    session: Session, *, activate: bool, now: datetime, origin: EventOrigin
) -> tuple[RainWarningStatus, bool]:
    try:
        _ensure_row(session)
        row = session.scalars(_select("update")).one()
        if row.active == activate:
            status = _status(row)
            session.rollback()  # nothing to change: no write, no event
            return status, False
        row.active = activate
        row.origin = origin.value
        row.updated_at = now
        if activate:
            row.activated_at = now
        else:
            row.cleared_at = now
        append_event(
            session,
            event_type=(
                EventType.RAIN_WARNING_ACTIVATED if activate else EventType.RAIN_WARNING_CLEARED
            ),
            origin=origin,
            reason=REASON_ACTIVATED if activate else REASON_CLEARED,
            details={"active": activate},
            occurred_at=now,
        )
        session.commit()
        return _status(row), True
    except BaseException:
        session.rollback()
        raise


def activate(
    session: Session, now: datetime, origin: EventOrigin = EventOrigin.MANUAL
) -> tuple[RainWarningStatus, bool]:
    """Activate the warning. Returns the state and whether it changed (False: already active)."""
    return _change(session, activate=True, now=now, origin=origin)


def clear(
    session: Session, now: datetime, origin: EventOrigin = EventOrigin.MANUAL
) -> tuple[RainWarningStatus, bool]:
    """Clear the warning. Returns the state and whether it changed (False: already inactive)."""
    return _change(session, activate=False, now=now, origin=origin)
