"""Read queries for drones."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.drones.models import Drone


def list_drones(session: Session) -> Sequence[Drone]:
    """Return all drones in a stable order (by id), with their model loaded."""
    statement = select(Drone).options(selectinload(Drone.model)).order_by(Drone.id)
    return session.scalars(statement).all()


def get_drone(session: Session, drone_id: str) -> Drone | None:
    statement = select(Drone).options(selectinload(Drone.model)).where(Drone.id == drone_id)
    return session.scalars(statement).one_or_none()
