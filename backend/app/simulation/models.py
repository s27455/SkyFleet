"""Persisted flight state and the simulation worker's heartbeat.

A `MissionFlight` is the authoritative record of one started mission's flight: the timed legs, the
current phase and snapshot (position, battery, progress, next target) and the milestones reached.
Flight position and battery are a pure function of the stored schedule and the clock
(`flight.py`), so a restart never resets or invents progress.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FlightPhase(StrEnum):
    OUTBOUND = "OUTBOUND"  # flying to the destination with the parcel
    DELIVERING = "DELIVERING"  # the short delivery stop at the destination
    RETURNING = "RETURNING"  # flying back, empty, to the planned Hub
    DIVERTING = "DIVERTING"  # flying to another Hub because the planned one was full
    LANDED = "LANDED"  # terminal: docked at a Hub
    EMERGENCY = "EMERGENCY"  # terminal: simulated emergency, no safe Hub landing was possible


TERMINAL_PHASES: tuple[FlightPhase, ...] = (FlightPhase.LANDED, FlightPhase.EMERGENCY)


class EmergencyReason(StrEnum):
    NO_HUB_WITH_CAPACITY = "NO_HUB_WITH_CAPACITY"  # every reachable Hub was full
    BATTERY_INSUFFICIENT = "BATTERY_INSUFFICIENT"  # no other Hub was reachable with the battery
    BATTERY_CRITICAL = "BATTERY_CRITICAL"  # the battery fell below the critical floor in flight


_PHASES = ", ".join(f"'{phase.value}'" for phase in FlightPhase)
_REASONS = ", ".join(f"'{reason.value}'" for reason in EmergencyReason)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MissionFlight(Base):
    __tablename__ = "mission_flights"
    __table_args__ = (
        CheckConstraint(f"phase IN ({_PHASES})", name="ck_mission_flights_phase_valid"),
        CheckConstraint(
            f"emergency_reason IS NULL OR emergency_reason IN ({_REASONS})",
            name="ck_mission_flights_emergency_reason_valid",
        ),
        CheckConstraint("progress BETWEEN 0 AND 1", name="ck_mission_flights_progress_range"),
        CheckConstraint("pace_s_per_km > 0", name="ck_mission_flights_pace_positive"),
    )

    mission_id: Mapped[str] = mapped_column(
        ForeignKey("missions.id", ondelete="RESTRICT"), primary_key=True
    )
    phase: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Battery in percent of capacity, unrounded; the drone row holds the rounded value.
    start_battery_pct: Mapped[float] = mapped_column(Float)
    battery_pct: Mapped[float] = mapped_column(Float)
    # Ordered timed legs (see app/simulation/flight.py); replaced as a whole on a diversion.
    legs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # Seconds per km of the original plan; a diversion leg flies at the same pace.
    pace_s_per_km: Mapped[float] = mapped_column(Float)
    planned_return_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    # The Hub currently being flown to; changes on a diversion.
    landing_target_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id", ondelete="RESTRICT"))
    landed_hub_id: Mapped[str | None] = mapped_column(
        ForeignKey("hubs.id", ondelete="RESTRICT"), default=None
    )
    # Hubs already found full during this flight; each Hub is tried at most once.
    tried_hub_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    longitude: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    target_longitude: Mapped[float | None] = mapped_column(Float, default=None)
    target_latitude: Mapped[float | None] = mapped_column(Float, default=None)
    target_eta_s: Mapped[float | None] = mapped_column(Float, default=None)
    emergency_reason: Mapped[str | None] = mapped_column(String(24), default=None)
    emergency_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), onupdate=_utc_now
    )


class SimulationHeartbeat(Base):
    """The worker records the time of its latest tick here; starting a mission requires it fresh."""

    __tablename__ = "simulation_heartbeats"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


WORKER_HEARTBEAT = "simulation-worker"
