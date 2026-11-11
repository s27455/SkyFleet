"""Read queries for Hubs."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hubs.models import Hub


def list_hubs(session: Session) -> Sequence[Hub]:
    """Return all Hubs in a stable order (by id)."""
    return session.scalars(select(Hub).order_by(Hub.id)).all()


def get_hub(session: Session, hub_id: str) -> Hub | None:
    return session.get(Hub, hub_id)
