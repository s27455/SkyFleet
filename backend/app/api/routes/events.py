"""Read-only operational event timeline (Feature 018A)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.events import repository
from app.events.models import OperationalEvent
from app.events.schemas import EventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def list_events(
    session: SessionDep,
    order_id: str | None = None,
    mission_id: str | None = None,
    drone_id: str | None = None,
    event_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=repository.MAX_LIMIT)] = repository.DEFAULT_LIMIT,
) -> Sequence[OperationalEvent]:
    """Events for one order, mission, drone or event type; one filter is required (oldest first)."""
    if order_id is None and mission_id is None and drone_id is None and event_type is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EVENT_FILTER_REQUIRED",
                "message": "Provide order_id, mission_id, drone_id or event_type.",
            },
        )
    return repository.list_events(
        session,
        order_id=order_id,
        mission_id=mission_id,
        drone_id=drone_id,
        event_type=event_type,
        limit=limit,
    )
