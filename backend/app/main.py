"""FastAPI application entrypoint: `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import drones, health, hubs
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="SkyFleet API", version="0.1.0")

    # Explicit allow-list; never "*" since the frontend is deployed on a known origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(hubs.router, prefix="/api")
    app.include_router(drones.router, prefix="/api")
    return app


app = create_app()
