"""Mission endpoints: read-only plan preview, confirmation, cancellation and reads."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep, SettingsDep
from app.api.errors import rain_warning_active
from app.common import clock
from app.missions import repository, service
from app.missions.models import Mission
from app.missions.schemas import MissionCreateRequest, MissionResponse, PlanResponse
from app.simulation import service as simulation_service
from app.weather.service import RainWarningActiveError

router = APIRouter(prefix="/missions", tags=["missions"])


def _not_found(error: service.MissionError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


# Declared before "/{mission_id}" so "plan" is never read as a mission id.
@router.get("/plan", response_model=PlanResponse)
def preview_plan(
    session: SessionDep,
    settings: SettingsDep,
    order_id: Annotated[str, Query(min_length=1)],
    drone_id: Annotated[str, Query(min_length=1)],
) -> PlanResponse:
    """Read-only feasibility check; never changes data. The return Hub is planned, not reserved."""
    try:
        return service.preview_plan(session, order_id, drone_id, settings)
    except (service.OrderNotFoundError, service.DroneNotFoundError) as error:
        raise _not_found(error) from error


@router.post("", response_model=MissionResponse, status_code=201)
def create_mission(
    body: MissionCreateRequest, session: SessionDep, settings: SettingsDep
) -> Mission:
    try:
        return service.confirm_mission(session, body.order_id, body.drone_id, settings)
    except (service.OrderNotFoundError, service.DroneNotFoundError) as error:
        raise _not_found(error) from error
    except service.PlanRejectedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MISSION_NOT_ELIGIBLE",
                "message": str(error),
                "plan": error.plan.model_dump(mode="json"),
            },
        ) from error


@router.get("", response_model=list[MissionResponse])
def list_missions(session: SessionDep) -> Sequence[Mission]:
    return repository.list_missions(session)


@router.get("/{mission_id}", response_model=MissionResponse)
def get_mission(mission_id: str, session: SessionDep) -> Mission:
    mission = repository.get_mission(session, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    return mission


@router.post("/{mission_id}/start", response_model=MissionResponse)
def start_mission(mission_id: str, session: SessionDep, settings: SettingsDep) -> Mission:
    """Takeoff: starts an ASSIGNED mission exactly once. Needs a running simulation worker."""
    try:
        return simulation_service.start_mission(session, mission_id, clock.utcnow(), settings)
    except service.MissionNotFoundError as error:
        raise _not_found(error) from error
    except RainWarningActiveError as error:
        raise rain_warning_active(error) from error
    except simulation_service.WorkerUnavailableError as error:
        last = error.last_heartbeat_at
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SIMULATION_WORKER_UNAVAILABLE",
                "message": str(error),
                "last_heartbeat_at": last.isoformat() if last else None,
                "max_age_seconds": error.max_age_seconds,
            },
        ) from error
    except simulation_service.MissionNotStartableError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MISSION_NOT_STARTABLE",
                "message": str(error),
                "status": error.status,
            },
        ) from error
    except service.PlanRejectedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MISSION_NOT_ELIGIBLE",
                "message": str(error),
                "plan": error.plan.model_dump(mode="json"),
            },
        ) from error


@router.post("/{mission_id}/cancel", response_model=MissionResponse)
def cancel_mission(mission_id: str, session: SessionDep) -> Mission:
    try:
        return service.cancel_mission(session, mission_id)
    except service.MissionNotFoundError as error:
        raise _not_found(error) from error
    except service.MissionNotCancellableError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MISSION_NOT_CANCELLABLE",
                "message": str(error),
                "status": error.status,
            },
        ) from error
