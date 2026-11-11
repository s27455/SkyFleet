"""Read queries for delivery orders."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.orders.models import DeliveryOrder


def list_orders(session: Session) -> Sequence[DeliveryOrder]:
    """Return all orders in a stable order (creation time, then id)."""
    statement = select(DeliveryOrder).order_by(DeliveryOrder.created_at, DeliveryOrder.id)
    return session.scalars(statement).all()


def get_order(session: Session, order_id: str) -> DeliveryOrder | None:
    return session.get(DeliveryOrder, order_id)
