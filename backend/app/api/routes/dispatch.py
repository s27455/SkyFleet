"""Read-only dispatch recommendations (Feature 014A): proposes assignments, creates nothing."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes.missions import SettingsDep
from app.db.session import get_session
from app.dispatch import service
from app.dispatch.schemas import RecommendationsResponse

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(session: SessionDep, settings: SettingsDep) -> RecommendationsResponse:
    """Which drone should serve which waiting order. Never creates or starts a mission."""
    return service.recommend_for_session(session, settings)
