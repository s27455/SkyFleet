"""Manual incident triggers (Feature 018C). MVP/demo-only controls.

Each trigger calls the same backend service an automatic trigger will call later: one request, the
backend chooses an eligible target, performs the real transition and records the event, or answers
409 `NO_ELIGIBLE_TARGET` and creates nothing.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.simulation import clock
from app.simulation.failure import NoEligibleTargetError, trigger_drone_failure
from app.simulation.schemas import DroneFailureResponse

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
