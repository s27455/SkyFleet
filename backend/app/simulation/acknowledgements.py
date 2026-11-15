"""Acknowledging an emergency alert (Feature 022): hide it in the map overlay, nothing else.

An acknowledgement is one row in `incident_acknowledgements`, keyed by the mission id (the failed
flight's id). It never touches the incident: the events, the flight, the mission, the order and the
drone stay as they are, and it is not a resolution or a cancellation. Acknowledging is idempotent:
the first request stores the time, later ones (also concurrent ones) return that same time. Only an
alert that exists can be acknowledged, that is a flight that already ended in an emergency, which
is exactly what the flights endpoint exposes as `emergency`.
"""

from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.common.clock import as_utc
from app.simulation.models import IncidentAcknowledgement, MissionFlight


class EmergencyNotFoundError(Exception):
    def __init__(self, mission_id: str) -> None:
        super().__init__(f"Mission '{mission_id}' has no emergency alert to acknowledge")
        self.mission_id = mission_id


def acknowledge_emergency(session: Session, mission_id: str, now: datetime) -> datetime:
    """Store the acknowledgement (once) and return when it was first made.

    `INSERT ... ON CONFLICT DO NOTHING` makes concurrent first requests safe on both databases: one
    inserts, the others do nothing, and all read the same stored row afterwards.
    """
    try:
        has_alert = session.scalar(
            select(MissionFlight.mission_id).where(
                MissionFlight.mission_id == mission_id,
                MissionFlight.emergency_reason.is_not(None),
                MissionFlight.emergency_at.is_not(None),
            )
        )
        if has_alert is None:
            raise EmergencyNotFoundError(mission_id)
        values = {"mission_id": mission_id, "acknowledged_at": now}
        dialect = session.get_bind().dialect.name
        statement: Any
        if dialect == "postgresql":
            statement = postgresql_insert(IncidentAcknowledgement).values(**values)
        else:
            statement = sqlite_insert(IncidentAcknowledgement).values(**values)
        session.execute(statement.on_conflict_do_nothing(index_elements=["mission_id"]))
        session.commit()
    except BaseException:
        session.rollback()
        raise
    stored = session.scalar(
        select(IncidentAcknowledgement.acknowledged_at).where(
            IncidentAcknowledgement.mission_id == mission_id
        )
    )
    assert stored is not None
    return as_utc(stored)


def acknowledged_at_by_mission(
    session: Session, mission_ids: Collection[str]
) -> dict[str, datetime]:
    """When each of the given missions' alerts was acknowledged (missing: not acknowledged)."""
    if not mission_ids:
        return {}
    rows = session.execute(
        select(IncidentAcknowledgement.mission_id, IncidentAcknowledgement.acknowledged_at).where(
            IncidentAcknowledgement.mission_id.in_(mission_ids)
        )
    )
    return {mission_id: as_utc(at) for mission_id, at in rows}
