"""The application's notion of "now", in one place so tests can control it.

Shared by every domain module (events, weather, orders, dispatch, the API and the simulation), so it
lives here and not inside `app.simulation`.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp (SQLite drops the zone on read) as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
