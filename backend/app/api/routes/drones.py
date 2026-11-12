"""Drone endpoints: reads plus administrative create, update and delete."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.session import get_session
from app.drones import repository, service
from app.drones.models import Drone
from app.drones.schemas import DroneCreateRequest, DroneResponse, DroneUpdateRequest

router = APIRouter(prefix="/drones", tags=["drones"])

SessionDep = Annotated[Session, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def _http_error(error: service.DroneManagementError) -> HTTPException:
    """Map a domain error to a response with a stable machine-readable code."""
    if isinstance(error, service.DroneNotFoundError | service.HubNotFoundError):
        code = (
            "DRONE_NOT_FOUND" if isinstance(error, service.DroneNotFoundError) else "HUB_NOT_FOUND"
        )
        return HTTPException(status_code=404, detail={"code": code, "message": str(error)})
    codes: dict[type[service.DroneManagementError], str] = {
        service.DuplicateDroneError: "DRONE_ALREADY_EXISTS",
        service.HubFullError: "HUB_FULL",
        service.DroneBusyError: "DRONE_BUSY",
        service.InvalidChangeError: "INVALID_CHANGE",
        service.DroneHasHistoryError: "DRONE_HAS_HISTORY",
    }
    code = codes.get(type(error), "CONFLICT")
    return HTTPException(status_code=409, detail={"code": code, "message": str(error)})


@router.get("", response_model=list[DroneResponse])
def list_drones(session: SessionDep) -> Sequence[Drone]:
    return repository.list_drones(session)


@router.get("/{drone_id}", response_model=DroneResponse)
def get_drone(drone_id: str, session: SessionDep) -> Drone:
    drone = repository.get_drone(session, drone_id)
    if drone is None:
        raise HTTPException(status_code=404, detail=f"Drone '{drone_id}' not found")
    return drone


@router.post("", response_model=DroneResponse, status_code=201)
def create_drone(body: DroneCreateRequest, session: SessionDep, settings: SettingsDep) -> Drone:
    try:
        return service.create_drone(session, body, settings)
    except service.DroneManagementError as error:
        raise _http_error(error) from error


@router.patch("/{drone_id}", response_model=DroneResponse)
def update_drone(
    drone_id: str, body: DroneUpdateRequest, session: SessionDep, settings: SettingsDep
) -> Drone:
    try:
        return service.update_drone(session, drone_id, body, settings)
    except service.DroneManagementError as error:
        raise _http_error(error) from error


@router.delete("/{drone_id}", status_code=204)
def delete_drone(drone_id: str, session: SessionDep) -> Response:
    try:
        service.delete_drone(session, drone_id)
    except service.DroneManagementError as error:
        raise _http_error(error) from error
    return Response(status_code=204)
