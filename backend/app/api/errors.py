"""HTTP error mapping shared by several route modules."""

from fastapi import HTTPException

from app.simulation import service as simulation_service
from app.weather.service import RainWarningActiveError


def worker_unavailable(error: simulation_service.WorkerUnavailableError) -> HTTPException:
    last = error.last_heartbeat_at
    return HTTPException(
        status_code=503,
        detail={
            "code": "SIMULATION_WORKER_UNAVAILABLE",
            "message": str(error),
            "last_heartbeat_at": last.isoformat() if last else None,
            "max_age_seconds": error.max_age_seconds,
        },
    )


def rain_warning_active(error: RainWarningActiveError) -> HTTPException:
    return HTTPException(
        status_code=409, detail={"code": "RAIN_WARNING_ACTIVE", "message": str(error)}
    )
