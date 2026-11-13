"""Bounded read queries for operational events."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.models import OperationalEvent

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def list_events(
    session: Session,
    *,
    order_id: str | None = None,
    mission_id: str | None = None,
    drone_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Sequence[OperationalEvent]:
    """The newest `limit` matching events, returned oldest first (occurred_at, then id).

    At least one filter is required so that the full history is never read in one call.
    """
    if order_id is None and mission_id is None and drone_id is None:
        raise ValueError("At least one of order_id, mission_id or drone_id is required")
    limit = max(1, min(limit, MAX_LIMIT))
    statement = select(OperationalEvent)
    if order_id is not None:
        statement = statement.where(OperationalEvent.order_id == order_id)
    if mission_id is not None:
        statement = statement.where(OperationalEvent.mission_id == mission_id)
    if drone_id is not None:
        statement = statement.where(OperationalEvent.drone_id == drone_id)
    newest = session.scalars(
        statement.order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc()).limit(
            limit
        )
    ).all()
    return list(reversed(newest))
