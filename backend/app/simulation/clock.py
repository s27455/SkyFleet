"""The simulation's notion of "now", in one place so tests can control it."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp (SQLite drops the zone on read) as UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
