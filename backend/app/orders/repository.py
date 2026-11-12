"""Read queries for delivery orders."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.missions.models import Mission
from app.orders.models import DeliveryOrder


def list_orders(session: Session) -> Sequence[DeliveryOrder]:
    """Return all orders in a stable order (creation time, then id)."""
    statement = select(DeliveryOrder).order_by(DeliveryOrder.created_at, DeliveryOrder.id)
    return session.scalars(statement).all()


def get_order(session: Session, order_id: str) -> DeliveryOrder | None:
    return session.get(DeliveryOrder, order_id)


def get_order_for_update(session: Session, order_id: str) -> DeliveryOrder | None:
    """Fetch an order and lock its row until the transaction ends (no-op on SQLite)."""
    statement = (
        select(DeliveryOrder)
        .where(DeliveryOrder.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalars(statement).one_or_none()


def has_missions(session: Session, order_id: str) -> bool:
    """Whether any mission, in any status, references the order."""
    statement = select(Mission.id).where(Mission.order_id == order_id).limit(1)
    return session.scalars(statement).first() is not None
