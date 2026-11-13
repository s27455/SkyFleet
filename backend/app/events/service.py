"""Append and delete operational events. Callers own the transaction; nothing here commits."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.events.models import EventOrigin, EventType, OperationalEvent

MAX_DETAILS_JSON_CHARS = 2000
MAX_REASON_CHARS = 255


def append_event(
    session: Session,
    *,
    event_type: EventType,
    origin: EventOrigin,
    order_id: str | None = None,
    mission_id: str | None = None,
    flight_id: str | None = None,
    drone_id: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    occurred_at: datetime | None = None,
) -> bool:
    """Add one event to the caller's open transaction; return False if `dedupe_key` was seen.

    With a key it uses `INSERT ... ON CONFLICT DO NOTHING`, so a duplicate neither raises nor
    aborts the transaction (a unique violation would on PostgreSQL). Uniqueness is per key: this
    is at-most-once recording for a key, not an exactly-once guarantee. Pending domain rows are
    flushed first so the foreign keys resolve; the caller still commits or rolls back.
    """
    if details is not None and len(json.dumps(details)) > MAX_DETAILS_JSON_CHARS:
        raise ValueError(f"Event details exceed {MAX_DETAILS_JSON_CHARS} characters")
    values: dict[str, Any] = {
        "event_type": event_type.value,
        "origin": origin.value,
        "occurred_at": occurred_at or datetime.now(UTC),
        "order_id": order_id,
        "mission_id": mission_id,
        "flight_id": flight_id,
        "drone_id": drone_id,
        "reason": reason[:MAX_REASON_CHARS] if reason else None,
        "details": details,
        "dedupe_key": dedupe_key,
    }
    session.flush()
    dialect = session.get_bind().dialect.name
    if dedupe_key is not None and dialect == "postgresql":
        statement: Any = (
            postgresql_insert(OperationalEvent)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
    elif dedupe_key is not None and dialect == "sqlite":
        statement = (
            sqlite_insert(OperationalEvent)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
    else:
        statement = insert(OperationalEvent).values(**values)
    # RETURNING, not rowcount: a conflict returns no row, whatever the driver reports as rowcount.
    return session.execute(statement.returning(OperationalEvent.id)).first() is not None


def delete_events_for_order(session: Session, order_id: str) -> None:
    """Technical deletion only: remove an order's events inside the caller's transaction."""
    session.execute(delete(OperationalEvent).where(OperationalEvent.order_id == order_id))
