"""Queries for missions and the data the planner needs."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.drones.models import Drone
from app.hubs.models import Hub
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission
from app.orders.models import DeliveryOrder

_ACTIVE = [status.value for status in ACTIVE_MISSION_STATUSES]

# The largest `limit` the missions list accepts (the history grows with every simulated order).
MAX_LIST_LIMIT = 1000


def list_missions(
    session: Session,
    *,
    statuses: Sequence[str] | None = None,
    limit: int | None = None,
) -> Sequence[Mission]:
    """Return missions in a stable order (creation time, then id), oldest first.

    `statuses` keeps only missions in those states. `limit` keeps only the most recent N (after the
    status filter); they are still returned oldest first. Both are applied in SQL. Without either
    the whole history is returned.
    """
    statement = select(Mission)
    if statuses is not None:
        statement = statement.where(Mission.status.in_(statuses))
    if limit is None:
        return session.scalars(statement.order_by(Mission.created_at, Mission.id)).all()
    newest = statement.order_by(Mission.created_at.desc(), Mission.id.desc()).limit(limit)
    return list(reversed(session.scalars(newest).all()))


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


def order_has_active_mission(
    session: Session, order_id: str, *, exclude_mission_id: str | None = None
) -> bool:
    statement = select(Mission.id).where(Mission.order_id == order_id, Mission.status.in_(_ACTIVE))
    if exclude_mission_id is not None:
        statement = statement.where(Mission.id != exclude_mission_id)
    return session.scalars(statement.limit(1)).first() is not None


def drone_has_active_mission(
    session: Session, drone_id: str, *, exclude_mission_id: str | None = None
) -> bool:
    statement = select(Mission.id).where(Mission.drone_id == drone_id, Mission.status.in_(_ACTIVE))
    if exclude_mission_id is not None:
        statement = statement.where(Mission.id != exclude_mission_id)
    return session.scalars(statement.limit(1)).first() is not None
