"""Persisted delivery orders.

An order is one package handed over at an origin Hub by a business partner, destined for one
customer location. Feature 007 only stores and exposes orders: nothing dispatches, assigns or moves
them yet. There is no Partner entity and no drone assignment column; assignment will belong to a
future Mission entity. Destination coordinates are simulation inputs, not verified addresses.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# MVP order-acceptance rule: matches the SF-1 Courier's 3.0 kg maximum payload. A CHECK constraint
# cannot read the drone model table, so the limit is stated here (and in migration 0003).
MAX_PACKAGE_WEIGHT_KG = 3.0


class OrderStatus(StrEnum):
    """Initial states (business-rules.md section 3) plus the two delivery states of Feature 010.

    Failed delivery and parcel-return states are not decided yet (section 8); further states are
    added by a migration when a feature needs them.
    """

    CREATED = "CREATED"
    AWAITING_HANDOVER = "AWAITING_HANDOVER"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    # Set by the flight simulation: at takeoff, and when the parcel reaches the destination. The
    # order is DELIVERED before the drone returns and the mission completes.
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    # Feature 018B: terminal, set by the cancellation service. History is kept; a recalled parcel
    # stays on the drone until it lands (the flight records the recall, not the order).
    CANCELLED = "CANCELLED"


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
    # When the parcel was handed over (Feature 017A): the real UTC time at which the flight
    # simulation committed the DELIVERED status (not the flight's scheduled instant). Null for any
    # order not delivered and for legacy delivered orders whose time cannot be recovered. It is the
    # only reference for the active-view visibility window.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # When the order was cancelled (Feature 018B): the real UTC time of the transition. Like
    # `delivered_at`, it is the only reference for the active-view visibility window.
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Set on insert; a later lifecycle feature updates it when the status changes.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), onupdate=_utc_now
    )


ORDER_SIMULATION = "order-simulation"


class OrderSimulationState(Base):
    """Persisted Order Simulation mode (Feature 015B), shared by the API (toggle) and the worker.

    The single row `order-simulation`; a missing row means OFF. It is independent of the Automatic
    Dispatch mode and is reset to OFF whenever the simulation worker starts.
    """

    __tablename__ = "order_simulation_state"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # The time and short summary of the last generation attempt, not a log.
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_outcome: Mapped[str | None] = mapped_column(String(255), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
