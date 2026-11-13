"""Dispatch endpoints: read-only recommendations (014A) and explicit execution (014B)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import worker_unavailable
from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.dispatch import auto, service
from app.dispatch.schemas import (
    AutoDispatchStatus,
    DispatchExecuteRequest,
    RecommendationsResponse,
)
from app.missions import service as missions_service
from app.missions.models import Mission
from app.missions.schemas import MissionResponse
from app.simulation import clock
from app.simulation import service as simulation_service

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(session: SessionDep, settings: SettingsDep) -> RecommendationsResponse:
    """Which drone should serve which waiting order. Never creates or starts a mission."""
    return service.recommend_for_session(session, settings)


@router.post("/execute", response_model=MissionResponse, status_code=201)
def execute_dispatch(
    body: DispatchExecuteRequest, session: SessionDep, settings: SettingsDep
) -> Mission:
    """Create and start a mission for one order and drone, revalidated now.

    A recommendation is only a snapshot; every rule is checked again under locks. If the mission
    is created but does not start, the error names it and it stays ASSIGNED (nothing flies).
    """
    try:
        return service.execute_dispatch(
            session, body.order_id, body.drone_id, clock.utcnow(), settings
        )
    except missions_service.OrderNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "ORDER_NOT_FOUND", "message": str(error)}
        ) from error
    except missions_service.DroneNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "DRONE_NOT_FOUND", "message": str(error)}
        ) from error
    except service.MissionAlreadyAssignedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DISPATCH_ALREADY_ASSIGNED",
                "message": str(error),
                "mission_id": error.mission.id,
                "status": error.mission.status,
                "drone_id": error.mission.drone_id,
            },
        ) from error
    except missions_service.DroneNotFullyChargedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DRONE_NOT_FULLY_CHARGED",
                "message": str(error),
                "battery_pct": error.battery_pct,
                "required_pct": error.required_pct,
            },
        ) from error
    except missions_service.PlanRejectedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MISSION_NOT_ELIGIBLE",
                "message": str(error),
                "plan": error.plan.model_dump(mode="json"),
            },
        ) from error
    except simulation_service.WorkerUnavailableError as error:
        raise worker_unavailable(error) from error
    except service.DispatchStartFailedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DISPATCH_START_FAILED",
                "message": str(error),
                "mission_id": error.mission_id,
                "status": error.status,
                "cause": error.cause,
            },
        ) from error


@router.get("/auto/status", response_model=AutoDispatchStatus)
def get_auto_status(session: SessionDep, settings: SettingsDep) -> AutoDispatchStatus:
    """The server's actual automatic-dispatch state (OFF by default)."""
    return auto.get_status(session, clock.utcnow(), settings)


@router.post("/auto/enable", response_model=AutoDispatchStatus)
def enable_auto(session: SessionDep, settings: SettingsDep) -> AutoDispatchStatus:
    """Turn automatic dispatch ON (idempotent); refused while no simulation worker is alive."""
    try:
        return auto.enable(session, clock.utcnow(), settings)
    except simulation_service.WorkerUnavailableError as error:
        raise worker_unavailable(error) from error


@router.post("/auto/disable", response_model=AutoDispatchStatus)
def disable_auto(session: SessionDep, settings: SettingsDep) -> AutoDispatchStatus:
    """Turn automatic dispatch OFF (idempotent). Flights already started continue."""
    return auto.disable(session, clock.utcnow(), settings)
