"""Read-only drone endpoints."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.drones import repository
from app.drones.models import Drone
from app.drones.schemas import DroneResponse

router = APIRouter(prefix="/drones", tags=["drones"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[DroneResponse])
def list_drones(session: SessionDep) -> Sequence[Drone]:
    return repository.list_drones(session)


@router.get("/{drone_id}", response_model=DroneResponse)
def get_drone(drone_id: str, session: SessionDep) -> Drone:
    drone = repository.get_drone(session, drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail=f"Drone '{drone_id}' not found")
    return drone
