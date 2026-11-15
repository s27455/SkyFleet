"""Read queries for drones."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.drones.models import Drone, DroneModel
from app.hubs.models import Hub
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission

_ACTIVE = [status.value for status in ACTIVE_MISSION_STATUSES]


def list_drones(session: Session) -> Sequence[Drone]:
    """Return all drones in a stable order (by id), with their model loaded."""
    statement = select(Drone).options(selectinload(Drone.model)).order_by(Drone.id)
    return session.scalars(statement).all()


def get_drone(session: Session, drone_id: str) -> Drone | None:
    statement = select(Drone).options(selectinload(Drone.model)).where(Drone.id == drone_id)
    return session.scalars(statement).one_or_none()


def get_drone_for_update(session: Session, drone_id: str) -> Drone | None:
    """Fetch a drone and lock its row until the transaction ends (no-op on SQLite)."""
    statement = (
        select(Drone)
        .options(selectinload(Drone.model))
        .where(Drone.id == drone_id)
        .with_for_update(of=Drone)
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def get_hub_for_update(session: Session, hub_id: str) -> Hub | None:
    """Fetch a Hub and lock its row, serialising capacity checks for that Hub."""
    statement = (
        select(Hub)
        .where(Hub.id == hub_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def get_model_for_update(session: Session, model_id: str) -> DroneModel | None:
    """Fetch a drone model and lock its row (a no-op on SQLite): serialises drone creation."""
    statement = (
        select(DroneModel)
        .where(DroneModel.id == model_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def list_all_hubs(session: Session) -> Sequence[Hub]:
    return session.scalars(select(Hub).order_by(Hub.id)).all()


def has_missions(session: Session, drone_id: str, *, active_only: bool) -> bool:
    """Whether any mission (or any active mission) references the drone."""
    statement = select(Mission.id).where(Mission.drone_id == drone_id)
    if active_only:
        statement = statement.where(Mission.status.in_(_ACTIVE))
    return session.scalars(statement.limit(1)).first() is not None
