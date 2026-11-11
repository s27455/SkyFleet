"""SQLAlchemy engine, session factory and declarative base shared by the API and the worker."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all persisted models."""


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide engine (created lazily; no connection is opened here)."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is closed after the request."""
    with sessionmaker(bind=get_engine(), expire_on_commit=False)() as session:
        yield session
