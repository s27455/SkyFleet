"""Read queries for delivery orders."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.missions.models import Mission
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.visibility import visibility_cutoff


def list_orders(session: Session) -> Sequence[DeliveryOrder]:
    """Return all orders in a stable order (creation time, then id)."""
    statement = select(DeliveryOrder).order_by(DeliveryOrder.created_at, DeliveryOrder.id)
    return session.scalars(statement).all()


def list_active_orders(
    session: Session, now: datetime, window_seconds: float
) -> Sequence[DeliveryOrder]:
    """Orders for the active operational views (Feature 017A), in the same order as `list_orders`.

    Every order that is not `DELIVERED`, plus `DELIVERED` orders still inside the visibility window.
    A `DELIVERED` order without a delivery time never matches (`NULL > cutoff` is not true). The
    SQL mirrors `visibility.is_order_active`; both are tested against the same boundaries.
    """
    cutoff = visibility_cutoff(now, window_seconds)
    statement = (
        select(DeliveryOrder)
        .where(
            DeliveryOrder.status.not_in([OrderStatus.DELIVERED.value, OrderStatus.CANCELLED.value])
            | (
                (DeliveryOrder.status == OrderStatus.DELIVERED.value)
                & (DeliveryOrder.delivered_at > cutoff)
            )
            | (
                (DeliveryOrder.status == OrderStatus.CANCELLED.value)
                & (DeliveryOrder.cancelled_at > cutoff)
            )
        )
        .order_by(DeliveryOrder.created_at, DeliveryOrder.id)
    )
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


def count_ready_orders(session: Session) -> int:
    """Outstanding orders: every `READY_FOR_PICKUP` order, however it was created.

    An order stays `READY_FOR_PICKUP` while its mission is only ASSIGNED, until takeoff.
    """
    statement = (
        select(func.count())
        .select_from(DeliveryOrder)
        .where(DeliveryOrder.status == OrderStatus.READY_FOR_PICKUP.value)
    )
    return session.scalar(statement) or 0
