"""Read-only flight endpoint for REST polling."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.missions.models import Mission
from app.simulation import clock, heartbeat, lpr
from app.simulation.engine import rounded_pct
from app.simulation.models import FlightPhase, MissionFlight
from app.simulation.schemas import (
    FlightEmergency,
    FlightResponse,
    FlightsResponse,
    FlightTarget,
)

router = APIRouter(prefix="/flights", tags=["flights"])

SessionDep = Annotated[Session, Depends(get_session)]


def _as_flight_response(flight: MissionFlight, mission: Mission, now: datetime) -> FlightResponse:
    target = None
    if flight.target_longitude is not None and flight.target_latitude is not None:
        target = FlightTarget(
            position=(flight.target_longitude, flight.target_latitude),
            eta_s=flight.target_eta_s or 0.0,
        )
    emergency = None
    if flight.emergency_reason is not None and flight.emergency_at is not None:
        emergency = FlightEmergency.model_validate(
            {
                "reason": flight.emergency_reason,
                "at": clock.as_utc(flight.emergency_at),
                "position": (flight.longitude, flight.latitude),
            }
        )
    return FlightResponse.model_validate(
        {
            "mission_id": mission.id,
            "order_id": mission.order_id,
            "drone_id": mission.drone_id,
            "mission_status": mission.status,
            "phase": flight.phase,
            "progress": flight.progress,
            "position": (flight.longitude, flight.latitude),
            "battery_pct": rounded_pct(flight.battery_pct),
            "battery_exact_pct": flight.battery_pct,
            "target": target,
            "origin_hub_id": mission.origin_hub_id,
            "planned_return_hub_id": flight.planned_return_hub_id,
            "landing_target_hub_id": flight.landing_target_hub_id,
            "started_at": clock.as_utc(flight.started_at),
            "delivered_at": clock.as_utc(flight.delivered_at) if flight.delivered_at else None,
            "recalled_at": clock.as_utc(flight.recalled_at) if flight.recalled_at else None,
            "failed_at": clock.as_utc(flight.failed_at) if flight.failed_at else None,
            "recipient_unavailable_at": (
                clock.as_utc(flight.recipient_unavailable_at)
                if flight.recipient_unavailable_at
                else None
            ),
            "handover_failed_at": (
                clock.as_utc(flight.handover_failed_at) if flight.handover_failed_at else None
            ),
            "yielding_to_lpr": lpr.is_yielding(flight.legs, flight.started_at, now),
            "updated_at": clock.as_utc(flight.updated_at),
            "emergency": emergency,
        }
    )


@router.get("", response_model=FlightsResponse)
def list_flights(session: SessionDep, settings: SettingsDep) -> FlightsResponse:
    """Active flights plus flights that ended in an emergency, with the worker's heartbeat."""
    now = clock.utcnow()
    beat = heartbeat.last_heartbeat(session)
    rows = session.execute(
        select(MissionFlight, Mission)
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .where(MissionFlight.phase != FlightPhase.LANDED.value)
        .order_by(MissionFlight.started_at, MissionFlight.mission_id)
    ).all()
    return FlightsResponse(
        server_time=now,
        worker_heartbeat_at=beat,
        worker_stale=not heartbeat.is_fresh(beat, now, settings.sim_heartbeat_stale_seconds),
        flights=[_as_flight_response(flight, mission, now) for flight, mission in rows],
    )
