"""The Copilot endpoint with real concurrency on PostgreSQL (opt-in: `pytest -m postgres`).

These run on the temporary database of the `temp_engine` fixture; the development database and the
real provider are never involved.
"""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.ai import models as ai_models  # noqa: F401  (registers the AI tables)
from app.ai.models import AiBudgetState, AiRequestLog

from .helpers import ASK, ORIGIN, TOKEN, Rig, good_headers

pytestmark = pytest.mark.postgres


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with temp_engine.begin() as connection:  # the AI ledger starts empty in every test
        connection.execute(text("DELETE FROM ai_request_log"))
        connection.execute(text("DELETE FROM ai_budget_state"))
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def counts(factory: sessionmaker[Session]) -> tuple[int, int, int]:
    with factory() as session:
        return (
            int(session.scalar(select(func.count()).select_from(AiRequestLog)) or 0),
            int(session.scalar(select(func.count()).select_from(AiBudgetState)) or 0),
            int(
                session.execute(
                    text("select coalesce(sum(reserved_nano_usd), 0) from ai_budget_state")
                ).scalar_one()
            ),
        )


def test_racing_posts_make_exactly_one_provider_request(
    temp_engine: Engine, factory: sessionmaker[Session]
) -> None:
    rig = Rig(temp_engine, factory)
    barrier = threading.Barrier(8)

    def post(_: int) -> Any:
        client = TestClient(rig.app)  # one client per thread, all against the one app
        barrier.wait(timeout=30)
        return client.post(
            ASK, json={"question": "How many drones are charging?"}, headers=good_headers()
        )

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(post, range(8)))
    finally:
        rig.close()

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200] + [429] * 7  # one answer, seven refusals by the gateway
    assert {r.json()["detail"]["code"] for r in responses if r.status_code == 429} == {
        "RATE_LIMITED"
    }
    assert len(rig.transport.requests) == 1  # ONE paid request, never a retry or a second attempt
    assert counts(factory) == (1, 1, 0)  # one ledger row, one budget row, nothing left reserved


def test_a_flood_of_wrong_tokens_never_reaches_the_database_or_the_provider(
    temp_engine: Engine, factory: sessionmaker[Session]
) -> None:
    rig = Rig(temp_engine, factory)
    before = counts(factory)
    barrier = threading.Barrier(8)
    statements_before = rig.statements

    def post(_: int) -> int:
        client = TestClient(rig.app)
        barrier.wait(timeout=30)
        codes = []
        for _ in range(5):
            codes.append(
                client.post(
                    ASK,
                    json={"question": "q"},
                    headers={"Origin": ORIGIN, "Authorization": "Bearer " + "w" * 50},
                ).status_code
            )
        return sum(1 for code in codes if code == 401), sum(1 for code in codes if code == 429)  # type: ignore[return-value]

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(post, range(8)))
        locked = TestClient(rig.app).post(ASK, json={"question": "q"}, headers=good_headers())
    finally:
        rig.close()

    refused_401 = sum(r[0] for r in results)  # type: ignore[index]
    refused_429 = sum(r[1] for r in results)  # type: ignore[index]
    assert refused_401 + refused_429 == 40 and refused_429 > 0  # the throttle engaged
    assert refused_401 >= 10  # at least the failures that fill the window were answered with 401
    assert locked.status_code == 429  # even the right token is refused while locked
    assert rig.transport.requests == [] and rig.service_requests == 0
    assert rig.statements == statements_before  # not one SQL statement for 41 refused requests
    assert counts(factory) == before == (0, 0, 0)
    assert TOKEN not in locked.text
