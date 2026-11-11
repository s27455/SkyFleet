"""Read-only Hub endpoints."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.hubs import repository
from app.hubs.models import Hub
from app.hubs.schemas import HubResponse

router = APIRouter(prefix="/hubs", tags=["hubs"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[HubResponse])
def list_hubs(session: SessionDep) -> Sequence[Hub]:
    return repository.list_hubs(session)


@router.get("/{hub_id}", response_model=HubResponse)
def get_hub(hub_id: str, session: SessionDep) -> Hub:
    hub = repository.get_hub(session, hub_id)
    if hub is None:
        raise HTTPException(status_code=404, detail=f"Hub '{hub_id}' not found")
    return hub
