"""Read-only flight endpoint for REST polling."""

from fastapi import APIRouter

from app.api.deps import SessionDep, SettingsDep
from app.common import clock
from app.simulation import flight_view
from app.simulation.schemas import FlightsResponse

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("", response_model=FlightsResponse)
def list_flights(session: SessionDep, settings: SettingsDep) -> FlightsResponse:
    """Active flights plus flights that ended in an emergency, with the worker's heartbeat."""
    return flight_view.flights_response(
        session, clock.utcnow(), settings.sim_heartbeat_stale_seconds
    )
