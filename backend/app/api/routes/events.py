"""Read-only operational event timeline (Feature 018A)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.events import repository
from app.events.models import OperationalEvent
from app.events.schemas import EventResponse

router = APIRouter(prefix="/events", tags=["events"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[EventResponse])
def list_events(
    session: SessionDep,
    order_id: str | None = None,
    mission_id: str | None = None,
    drone_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=repository.MAX_LIMIT)] = repository.DEFAULT_LIMIT,
) -> Sequence[OperationalEvent]:
    """Events for one order, mission or drone; at least one filter is required (oldest first)."""
    if order_id is None and mission_id is None and drone_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVENT_FILTER_REQUIRED",
                "message": "Provide order_id, mission_id or drone_id.",
            },
        )
    return repository.list_events(
        session, order_id=order_id, mission_id=mission_id, drone_id=drone_id, limit=limit
    )
