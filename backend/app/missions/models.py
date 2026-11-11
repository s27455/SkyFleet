"""Persisted delivery missions: one drone serving one order, planned at confirmation time.

Feature 009 only plans, confirms and cancels missions. Nothing flies: `IN_FLIGHT` is reserved for
the flight simulation feature and no code here sets it. A mission never changes the order, the
drone or any Hub; "assigned" is derived from the existence of an active mission.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MissionStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    # Reserved for the flight simulation feature; Feature 009 never sets it.
    IN_FLIGHT = "IN_FLIGHT"
    CANCELLED = "CANCELLED"


# A mission is active (it claims its order and its drone) while assigned or in flight.
ACTIVE_MISSION_STATUSES: tuple[MissionStatus, ...] = (
    MissionStatus.ASSIGNED,
    MissionStatus.IN_FLIGHT,
)

_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in MissionStatus)
_ACTIVE_VALUES = ", ".join(f"'{status.value}'" for status in ACTIVE_MISSION_STATUSES)
ACTIVE_PREDICATE = f"status IN ({_ACTIVE_VALUES})"

MISSION_ID_PREFIX = "MIS-"


def new_mission_id() -> str:
    """`MIS-` plus 8 hexadecimal characters; the primary key guarantees uniqueness."""
    return f"{MISSION_ID_PREFIX}{uuid.uuid4().hex[:8].upper()}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Mission(Base):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_missions_status_valid"),
        CheckConstraint("origin_to_destination_km >= 0", name="ck_missions_leg_out_nonnegative"),
        CheckConstraint("destination_to_return_km >= 0", name="ck_missions_leg_back_nonnegative"),
        CheckConstraint("total_km >= 0", name="ck_missions_total_nonnegative"),
        CheckConstraint("expected_energy_pct >= 0", name="ck_missions_expected_nonnegative"),
        CheckConstraint("worst_case_energy_pct >= 0", name="ck_missions_worst_nonnegative"),
        # The database, not a pre-check, prevents two active missions for one order or one drone.
        Index(
            "uq_missions_active_order",
            "order_id",
            unique=True,
            postgresql_where=text(ACTIVE_PREDICATE),
            sqlite_where=text(ACTIVE_PREDICATE),
        ),
        Index(
            "uq_missions_active_drone",
            "drone_id",
            unique=True,
            postgresql_where=text(ACTIVE_PREDICATE),
            sqlite_where=text(ACTIVE_PREDICATE),
        ),
    )

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"))
    drone_id: Mapped[str] = mapped_column(ForeignKey("drones.id", ondelete="RESTRICT"))
    origin_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    # Planned return Hub: chosen at planning time, neither guaranteed nor reserved.
    return_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    # Snapshot of the estimate at confirmation (simulation assumptions, not certified values).
    origin_to_destination_km: Mapped[float] = mapped_column(Float)
    destination_to_return_km: Mapped[float] = mapped_column(Float)
    total_km: Mapped[float] = mapped_column(Float)
    expected_energy_pct: Mapped[float] = mapped_column(Float)
    worst_case_energy_pct: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), onupdate=_utc_now
    )
