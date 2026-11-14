"""Manual incident triggers (Feature 018C). MVP/demo-only controls.

Each trigger calls the same backend service an automatic trigger will call later: one request, the
backend chooses an eligible target, performs the real transition and records the event, or answers
409 `NO_ELIGIBLE_TARGET` and creates nothing.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.events.models import EventOrigin
from app.simulation import clock, lpr
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.models import LprScenario
from app.simulation.schemas import (
    DroneFailureResponse,
    LprScenarioResponse,
    LprStatusResponse,
    RecipientUnavailableResponse,
)
from app.weather import service as weather
from app.weather.schemas import RainWarningResponse

router = APIRouter(prefix="/incidents", tags=["incidents"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/drone-failure", response_model=DroneFailureResponse)
def drone_failure(session: SessionDep, settings: SettingsDep) -> DroneFailureResponse:
    """Fail one eligible flying drone: it makes a short emergency landing and is then grounded."""
    try:
        result = trigger_drone_failure(session, clock.utcnow(), settings)
    except NoEligibleTargetError as error:
        raise HTTPException(
            status_code=409, detail={"code": "NO_ELIGIBLE_TARGET", "message": str(error)}
        ) from error
    return DroneFailureResponse(
        drone_id=result.drone_id,
        mission_id=result.mission_id,
        order_id=result.order_id,
        stage=result.stage.value,
        landing_position=result.landing_position,
    )


@router.post("/recipient-unavailable", response_model=RecipientUnavailableResponse)
def recipient_unavailable(
    session: SessionDep, settings: SettingsDep
) -> RecipientUnavailableResponse:
    """Mark one delivery on its way as "recipient unavailable".

    The outcome is pending: the order only fails when the drone reaches the destination.
    """
    try:
        result = trigger_recipient_unavailable(session, clock.utcnow(), settings)
    except NoEligibleTargetError as error:
        raise HTTPException(
            status_code=409, detail={"code": "NO_ELIGIBLE_TARGET", "message": str(error)}
        ) from error
    return RecipientUnavailableResponse(
        drone_id=result.drone_id,
        mission_id=result.mission_id,
        order_id=result.order_id,
        attempt_at=result.attempt_at,
    )


def _lpr_response(row: LprScenario, now: datetime) -> LprScenarioResponse:
    zone = lpr.zone_of(row)
    return LprScenarioResponse(
        id=row.id,
        status=row.status,
        origin=row.origin,
        started_at=zone.started_at,
        ends_at=zone.ends_at,
        position=lpr.helicopter_position(zone, now),
        route_start=zone.start,
        route_end=zone.end,
        speed_ms=zone.speed_ms,
        radius_m=zone.radius_m,
        hold_margin_m=zone.margin_m,
    )


@router.post("/lpr-helicopter", response_model=LprScenarioResponse)
def lpr_helicopter(session: SessionDep, settings: SettingsDep) -> LprScenarioResponse:
    """Start the LPR helicopter pass: a moving safety zone that delivery drones yield to.

    Only one scenario runs at a time: a second trigger answers 409 `LPR_ALREADY_ACTIVE`.
    """
    now = clock.utcnow()
    try:
        row = lpr.start_scenario(session, now, settings)
    except lpr.LprAlreadyActiveError as error:
        raise HTTPException(
            status_code=409, detail={"code": "LPR_ALREADY_ACTIVE", "message": str(error)}
        ) from error
    return _lpr_response(row, now)


@router.get("/lpr", response_model=LprStatusResponse)
def lpr_status(session: SessionDep) -> LprStatusResponse:
    """The running LPR scenario with the helicopter's position now, or `null` when none runs."""
    now = clock.utcnow()
    row = lpr.active_scenario(session, now)
    return LprStatusResponse(
        server_time=now, scenario=_lpr_response(row, now) if row is not None else None
    )


def _rain_response(status: weather.RainWarningStatus, changed: bool = False) -> RainWarningResponse:
    return RainWarningResponse(
        active=status.active,
        activated_at=status.activated_at,
        cleared_at=status.cleared_at,
        origin=status.origin,
        changed=changed,
    )


@router.get("/rain-warning", response_model=RainWarningResponse)
def rain_warning_status(session: SessionDep) -> RainWarningResponse:
    """The global rain warning (Feature 020): `active` means new takeoffs are suspended."""
    return _rain_response(weather.get_status(session))


@router.post("/rain-warning/activate", response_model=RainWarningResponse)
def activate_rain_warning(session: SessionDep) -> RainWarningResponse:
    """Suspend NEW takeoffs (idempotent). Flights already in the air are not affected."""
    status, changed = weather.activate(session, clock.utcnow(), EventOrigin.MANUAL)
    return _rain_response(status, changed)


@router.post("/rain-warning/clear", response_model=RainWarningResponse)
def clear_rain_warning(session: SessionDep) -> RainWarningResponse:
    """Allow takeoffs again (idempotent)."""
    status, changed = weather.clear(session, clock.utcnow(), EventOrigin.MANUAL)
    return _rain_response(status, changed)
