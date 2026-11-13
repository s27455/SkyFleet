"""Active-view visibility rule for orders (Feature 017A).

A `DELIVERED` order stays in the active operational views for a fixed window after its persisted
delivery time, then drops out of them; the row is never deleted. Feature 017B reuses this rule for
the delivery-address markers: the map draws exactly the orders the active list returns.
"""

from datetime import datetime, timedelta

from app.orders.models import OrderStatus


def visibility_cutoff(now: datetime, window_seconds: float) -> datetime:
    """A delivery at or before this moment is outside the window (now >= delivered_at + window)."""
    return now - timedelta(seconds=window_seconds)


def is_order_active(
    status: str, delivered_at: datetime | None, now: datetime, window_seconds: float
) -> bool:
    """Whether an order belongs in the active views at `now`.

    Not `DELIVERED`: always. `DELIVERED`: only while `now < delivered_at + window`. A delivered
    order without a delivery time (legacy data) is hidden; no time is ever invented for it.
    """
    if status != OrderStatus.DELIVERED.value:
        return True
    if delivered_at is None:
        return False
    return delivered_at > visibility_cutoff(now, window_seconds)
