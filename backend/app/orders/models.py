"""Persisted delivery orders.

An order is one package handed over at an origin Hub by a business partner, destined for one
customer location. Feature 007 only stores and exposes orders: nothing dispatches, assigns or moves
them yet. There is no Partner entity and no drone assignment column; assignment will belong to a
future Mission entity. Destination coordinates are simulation inputs, not verified addresses.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# MVP order-acceptance rule: matches the SF-1 Courier's 3.0 kg maximum payload. A CHECK constraint
# cannot read the drone model table, so the limit is stated here (and in migration 0003).
MAX_PACKAGE_WEIGHT_KG = 3.0


class OrderStatus(StrEnum):
    """Only the initial states confirmed in business-rules.md section 3.

    The lifecycle after `READY_FOR_PICKUP` is not decided yet (section 8, Q1); later states are
    added by a migration when a feature needs them.
    """

    CREATED = "CREATED"
    AWAITING_HANDOVER = "AWAITING_HANDOVER"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"


_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in OrderStatus)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DeliveryOrder(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_orders_status_valid"),
        CheckConstraint(
            "length(trim(destination_address)) > 0", name="ck_orders_destination_address_nonempty"
        ),
        CheckConstraint(
            "destination_longitude BETWEEN -180 AND 180", name="ck_orders_longitude_range"
        ),
        CheckConstraint("destination_latitude BETWEEN -90 AND 90", name="ck_orders_latitude_range"),
        CheckConstraint(
            f"package_weight_kg > 0 AND package_weight_kg <= {MAX_PACKAGE_WEIGHT_KG}",
            name="ck_orders_package_weight_range",
        ),
    )

    # Stable human-readable id, e.g. "ORD-001".
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Hub where the package was handed over; chosen explicitly, never inferred.
    origin_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    destination_address: Mapped[str] = mapped_column(String(255))
    destination_longitude: Mapped[float] = mapped_column(Float)
    destination_latitude: Mapped[float] = mapped_column(Float)
    package_weight_kg: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now()
    )
    # Set on insert; a later lifecycle feature updates it when the status changes.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), onupdate=_utc_now
    )
