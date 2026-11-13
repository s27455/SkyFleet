"""Order Simulation endpoints (Feature 015B): status and an explicit ON/OFF switch.

Independent of Automatic Dispatch. The simulation worker owns the generation loop; these routes
only read and change the stored mode.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import worker_unavailable
from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.orders import simulation
from app.orders.schemas import OrderSimulationStatus
from app.simulation import clock
from app.simulation import service as simulation_service

router = APIRouter(prefix="/orders/simulation", tags=["order-simulation"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/status", response_model=OrderSimulationStatus)
def get_status(session: SessionDep, settings: SettingsDep) -> OrderSimulationStatus:
    """The server's actual Order Simulation state (OFF by default)."""
    return simulation.get_status(session, clock.utcnow(), settings)


@router.post("/enable", response_model=OrderSimulationStatus)
def enable(session: SessionDep, settings: SettingsDep) -> OrderSimulationStatus:
    """Turn Order Simulation ON (idempotent); refused while no simulation worker is alive."""
    try:
        return simulation.enable(session, clock.utcnow(), settings)
    except simulation_service.WorkerUnavailableError as error:
        raise worker_unavailable(error) from error


@router.post("/disable", response_model=OrderSimulationStatus)
def disable(session: SessionDep, settings: SettingsDep) -> OrderSimulationStatus:
    """Turn Order Simulation OFF (idempotent). Existing orders are untouched."""
    return simulation.disable(session, clock.utcnow(), settings)
