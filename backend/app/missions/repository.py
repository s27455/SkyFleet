"""Queries for missions and the data the planner needs."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.drones.models import Drone
from app.hubs.models import Hub
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.orders.models import DeliveryOrder

_ACTIVE = [status.value for status in ACTIVE_MISSION_STATUSES]


def list_missions(session: Session) -> Sequence[Mission]:
    """Return all missions in a stable order (creation time, then id)."""
    return session.scalars(select(Mission).order_by(Mission.created_at, Mission.id)).all()


def get_mission(session: Session, mission_id: str) -> Mission | None:
    return session.get(Mission, mission_id)


def get_mission_for_update(session: Session, mission_id: str) -> Mission | None:
    """Fetch a mission and lock its row until the transaction ends (no-op on SQLite)."""
    statement = (
        select(Mission)
        .where(Mission.id == mission_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def get_order(session: Session, order_id: str, *, lock: bool = False) -> DeliveryOrder | None:
    statement = select(DeliveryOrder).where(DeliveryOrder.id == order_id)
    if lock:
        # populate_existing: rows already in the session are refreshed after the lock is taken.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return session.scalars(statement).one_or_none()


def get_drone(session: Session, drone_id: str, *, lock: bool = False) -> Drone | None:
    statement = select(Drone).options(selectinload(Drone.model)).where(Drone.id == drone_id)
    if lock:
        statement = statement.with_for_update(of=Drone).execution_options(populate_existing=True)
    return session.scalars(statement).one_or_none()


def list_hubs(session: Session) -> Sequence[Hub]:
    return session.scalars(select(Hub).order_by(Hub.id)).all()


def list_drones(session: Session) -> Sequence[Drone]:
    return session.scalars(select(Drone).order_by(Drone.id)).all()


def order_has_active_mission(session: Session, order_id: str) -> bool:
    statement = select(Mission.id).where(Mission.order_id == order_id, Mission.status.in_(_ACTIVE))
    return session.scalars(statement.limit(1)).first() is not None


def drone_has_active_mission(session: Session, drone_id: str) -> bool:
    statement = select(Mission.id).where(Mission.drone_id == drone_id, Mission.status.in_(_ACTIVE))
    return session.scalars(statement.limit(1)).first() is not None
