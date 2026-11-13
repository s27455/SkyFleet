"""Active-view visibility rule for orders (Feature 017A).

A `DELIVERED` order stays in the active operational views for a fixed window after its persisted
delivery time, and a `CANCELLED` order (Feature 018B) for the same window after its persisted
cancellation time; then it drops out of them. The row is never deleted. Feature 017B reuses this
rule for the delivery-address markers: the map draws exactly the orders the active list returns.
"""

from datetime import datetime, timedelta

from app.orders.models import OrderStatus


def visibility_cutoff(now: datetime, window_seconds: float) -> datetime:
    """A delivery at or before this moment is outside the window (now >= delivered_at + window)."""
    return now - timedelta(seconds=window_seconds)


def is_order_active(
    status: str,
    delivered_at: datetime | None,
    now: datetime,
    window_seconds: float,
    cancelled_at: datetime | None = None,
) -> bool:
    """Whether an order belongs in the active views at `now`.

    Neither `DELIVERED` nor `CANCELLED`: always. `DELIVERED`: only while
    `now < delivered_at + window`. `CANCELLED`: the same with `cancelled_at`. An order without the
    matching time (legacy data) is hidden; no time is ever invented for it.
    """
    if status == OrderStatus.DELIVERED.value:
        moment = delivered_at
    elif status == OrderStatus.CANCELLED.value:
        moment = cancelled_at
    else:
        return True
    if moment is None:
        return False
    return moment > visibility_cutoff(now, window_seconds)
