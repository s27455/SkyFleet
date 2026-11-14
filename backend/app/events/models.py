"""Persisted operational events.

An event records that something really happened, at the real UTC time the transition was
committed (never a simulated flight instant). Events are append-only and are written in the same
transaction as the domain change they describe. History alone never says whether an incident is
still active; a later feature exposes explicit active state.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EventType(StrEnum):
    """Stable event codes. The four incident categories are enabled by Features 018B to 018E."""

    ORDER_CREATED = "ORDER_CREATED"
    ORDER_CANCELLED = "ORDER_CANCELLED"  # 018B
    DRONE_FAILURE = "DRONE_FAILURE"  # 018C
    RECIPIENT_UNAVAILABLE = "RECIPIENT_UNAVAILABLE"  # 018D
    LPR_TRANSIT = "LPR_TRANSIT"  # 018E
    DRONE_RELOCATION = "DRONE_RELOCATION"  # 019A (`details.phase` STARTED or COMPLETED)


class EventOrigin(StrEnum):
    SYSTEM = "SYSTEM"
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


def _in_list(values: type[StrEnum]) -> str:
    return ", ".join(f"'{value.value}'" for value in values)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OperationalEvent(Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({_in_list(EventType)})", name="ck_operational_events_type_valid"
        ),
        CheckConstraint(
            f"origin IN ({_in_list(EventOrigin)})", name="ck_operational_events_origin_valid"
        ),
        Index("ix_operational_events_order", "order_id", "occurred_at", "id"),
        Index("ix_operational_events_mission", "mission_id", "occurred_at", "id"),
        Index("ix_operational_events_drone", "drone_id", "occurred_at", "id"),
    )

    # Monotonic id: the tie-breaker after `occurred_at` for a deterministic order.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32))
    # Real UTC time of the transition (not a simulated or scheduled instant).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    origin: Mapped[str] = mapped_column(String(16))
    # All references are optional and RESTRICT: history is never silently detached. Only the
    # technical order deletion removes its events, explicitly, in its own transaction.
    order_id: Mapped[str | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), default=None
    )
    mission_id: Mapped[str | None] = mapped_column(
        ForeignKey("missions.id", ondelete="RESTRICT"), default=None
    )
    # A flight shares its mission's id (`mission_flights.mission_id` is its key).
    flight_id: Mapped[str | None] = mapped_column(
        ForeignKey("mission_flights.mission_id", ondelete="RESTRICT"), default=None
    )
    drone_id: Mapped[str | None] = mapped_column(
        ForeignKey("drones.id", ondelete="RESTRICT"), default=None
    )
    reason: Mapped[str | None] = mapped_column(String(255), default=None)
    # Small incident-specific details; the size is bounded by the append helper.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    # Optional idempotency key: a second append with the same key is ignored (NULLs never clash).
    dedupe_key: Mapped[str | None] = mapped_column(String(128), unique=True, default=None)
