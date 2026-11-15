"""Fixtures for the AI tests: isolated settings, an in-memory budget database, fake transports."""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from app.ai import models  # noqa: F401  (registers the AI tables on Base.metadata)
from app.ai.budget import BudgetLimits, SqlBudgetStore
from app.ai.gateway import AiGateway
from app.config import Settings

from .ai_fakes import FAKE_KEY, START, Clock, FakeTransport

__all__ = ["FAKE_KEY", "START"]


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    """Settings that never read `.env` or the real environment (`_env_file=None`).

    AI is enabled with a FAKE key by default so the gateway logic can be tested; pass overrides to
    change anything, `ai_enabled=False` included.
    """

    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "ai_enabled": True,
            "anthropic_api_key": SecretStr(FAKE_KEY),
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return factory


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(session_factory: sessionmaker[Session]) -> SqlBudgetStore:
    return SqlBudgetStore(session_factory)


@pytest.fixture
def limits() -> BudgetLimits:
    return BudgetLimits(
        ceiling_nano_usd=4_000_000_000,
        max_requests_per_hour=10,
        min_interval_seconds=30,
        stale_after_seconds=90,
        error_backoff_seconds=900,
    )


@pytest.fixture
def make_gateway(
    make_settings: Callable[..., Settings], store: SqlBudgetStore, clock: Clock
) -> Callable[..., tuple[AiGateway, FakeTransport]]:
    def factory(
        transport: FakeTransport | None = None, **settings_overrides: Any
    ) -> tuple[AiGateway, FakeTransport]:
        fake = transport or FakeTransport()
        gateway = AiGateway(make_settings(**settings_overrides), fake, store, clock=clock)
        return gateway, fake

    return factory
