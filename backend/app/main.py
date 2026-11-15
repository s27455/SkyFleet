"""FastAPI application entrypoint: `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    copilot,
    dispatch,
    drones,
    events,
    flights,
    health,
    hubs,
    incidents,
    missions,
    order_simulation,
    orders,
)
from app.config import Settings, get_settings
from app.copilot.access import FailedAuthThrottle
from app.copilot.schemas import ErrorCode
from app.copilot.service import MESSAGES


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="SkyFleet API", version="0.1.0")
    app.state.settings = settings
    # Feature 026: failed Copilot sign-ins, in memory, per app (resets when the API restarts).
    app.state.copilot_throttle = FailedAuthThrottle()

    # Explicit allow-list; never "*" since the frontend is deployed on a known origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(hubs.router, prefix="/api")
    app.include_router(drones.router, prefix="/api")
    app.include_router(order_simulation.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    app.include_router(missions.router, prefix="/api")
    app.include_router(flights.router, prefix="/api")
    app.include_router(dispatch.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(incidents.router, prefix="/api")
    app.include_router(copilot.router, prefix="/api")

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, error: RequestValidationError):  # type: ignore[no-untyped-def]
        # The Copilot never echoes a rejected question back (FastAPI's default 422 does);
        # every other route keeps its default 422.
        if request.url.path.startswith("/api/ai/"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "code": ErrorCode.INVALID_QUESTION.value,
                        "message": MESSAGES[ErrorCode.INVALID_QUESTION],
                    }
                },
            )
        return await request_validation_exception_handler(request, error)

    return app


app = create_app()
