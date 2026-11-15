from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai import models as ai_models  # noqa: F401  (registers the AI tables)
from app.copilot import service as copilot_service

from .helpers import Rig


@pytest.fixture(autouse=True)
def _prices_are_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """The readiness check dates the prices by the calendar; pin it so the tests never age out."""
    monkeypatch.setattr(copilot_service, "_today", lambda: date(2026, 11, 20))


@pytest.fixture
def make_rig(
    engine: Engine, seeded: Session, session_factory: sessionmaker[Session]
) -> Iterator[Callable[..., Rig]]:
    made: list[Rig] = []

    def factory(**overrides: Any) -> Rig:
        rig = Rig(engine, session_factory, **overrides)
        made.append(rig)
        return rig

    yield factory
    for rig in made:
        rig.close()
