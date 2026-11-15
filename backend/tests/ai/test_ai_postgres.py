"""The budget on a real PostgreSQL database, with real threads (opt-in: `pytest -m postgres`).

These run on the temporary database of the `temp_engine` fixture (migrations applied, so migration
0019 itself is exercised). The development database is never touched. Every transport here is a
fake and the suite guard forbids a real client and any non-loopback connection.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import BudgetLimits, Reservation, SqlBudgetStore
from app.ai.errors import (
    AiError,
    BudgetExhaustedError,
    ConcurrencyLimitError,
    TooSoonError,
    UpstreamError,
)
from app.ai.gateway import AiGateway
from app.ai.models import AiBudgetState, AiRequestLog
from app.ai.types import TransportUsage
from app.config import Settings
from app.db.session import Base

from .ai_fakes import Clock, FakeTransport, upstream

pytestmark = pytest.mark.postgres

R = 1_000_000  # a reservation, in nano-USD
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
THREADS = 8


def limits(
    *, ceiling: int = 100 * R, per_hour: int = 10_000, interval: int = 0, stale: int = 90
) -> BudgetLimits:
    return BudgetLimits(ceiling, per_hour, interval, stale, 900)


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    """Sessions on the temporary database, with the two AI tables emptied for each test."""
    with temp_engine.begin() as connection:
        connection.execute(text("DELETE FROM ai_request_log"))
        connection.execute(text("DELETE FROM ai_budget_state"))
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def reserve(store: SqlBudgetStore, lim: BudgetLimits, now: datetime = T0, amount: int = R) -> int:
    return store.reserve(
        model="claude-haiku-5-5",
        reserved_nano_usd=amount,
        request_bytes=100,
        limits=lim,
        now=now,
    ).request_id


def race(jobs: int, work: Callable[[int], object]) -> list[object]:
    """Run `work(i)` in `jobs` threads released together; return results or the raised error."""
    barrier = threading.Barrier(jobs)

    def run(index: int) -> object:
        barrier.wait(timeout=30)
        try:
            return work(index)
        except AiError as error:
            return error

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(run, range(jobs)))


def books(factory: sessionmaker[Session]) -> tuple[int, int, list[tuple[str, int]]]:
    with factory() as session:
        state = session.get(AiBudgetState, "anthropic")
        assert state is not None
        log = session.execute(
            select(AiRequestLog.status, AiRequestLog.charged_nano_usd).order_by(AiRequestLog.id)
        ).all()
        return state.spent_nano_usd, state.reserved_nano_usd, [(s, c) for s, c in log]


# --- the migration on PostgreSQL ----


def test_the_migrated_postgres_schema_matches_the_models(temp_engine: Engine) -> None:
    with temp_engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []


def test_postgres_enforces_the_constraints(factory: sessionmaker[Session]) -> None:
    store = SqlBudgetStore(factory)
    reserve(store, limits())

    bad_statements = [
        "UPDATE ai_request_log SET status = 'BOGUS'",
        "UPDATE ai_request_log SET reserved_nano_usd = -1",
        "UPDATE ai_request_log SET charged_nano_usd = -1",
        "UPDATE ai_budget_state SET spent_nano_usd = -1",
        "UPDATE ai_budget_state SET reserved_nano_usd = -1",
    ]
    for statement in bad_statements:
        with factory() as session, pytest.raises(IntegrityError):
            session.execute(text(statement))
            session.commit()


# --- simultaneous reservations ----


def test_simultaneous_requests_let_exactly_one_through(factory: sessionmaker[Session]) -> None:
    store = SqlBudgetStore(factory)

    results = race(THREADS, lambda _: reserve(store, limits(interval=30)))

    winners = [r for r in results if isinstance(r, int)]
    refused = [r for r in results if isinstance(r, AiError)]
    assert len(winners) == 1  # the one-at-a-time rule holds under a true race
    assert len(refused) == THREADS - 1
    assert all(isinstance(r, ConcurrencyLimitError | TooSoonError) for r in refused)
    spent, reserved, log = books(factory)
    assert (spent, reserved, log) == (0, R, [("RESERVED", 0)])  # one row, one reservation


def test_the_ceiling_is_never_exceeded_by_racing_requests(factory: sessionmaker[Session]) -> None:
    store = SqlBudgetStore(factory)
    lim = limits(ceiling=5 * R)  # room for exactly five reservations
    granted: list[int] = []
    lock = threading.Lock()

    def worker(_: int) -> str:
        for _attempt in range(5_000):
            try:
                request_id = reserve(store, lim)
            except (ConcurrencyLimitError, TooSoonError):
                continue  # another request is in flight: try again
            except BudgetExhaustedError:
                return "exhausted"
            with lock:
                granted.append(request_id)
            # every outcome is the expensive, unclear one: the whole reservation stays spent
            store.settle_ambiguous(
                _reservation(request_id), error_code="timeout", provider_request_id=None, now=T0
            )
        return "gave up"

    results = race(THREADS, worker)

    assert results == ["exhausted"] * THREADS  # every thread ended on the ceiling, none gave up
    assert len(granted) == 5  # exactly the number the ceiling pays for
    spent, reserved, log = books(factory)
    assert (spent, reserved) == (5 * R, 0)
    assert spent <= 5 * R
    assert log == [("AMBIGUOUS", R)] * 5


def _reservation(request_id: int) -> Reservation:
    return Reservation(request_id, R, "claude-haiku-5-5")


def test_the_hourly_quota_holds_under_a_race(factory: sessionmaker[Session]) -> None:
    store = SqlBudgetStore(factory)
    lim = limits(per_hour=3)
    done: list[int] = []
    lock = threading.Lock()

    def worker(_: int) -> str:
        for _attempt in range(5_000):
            try:
                request_id = reserve(store, lim)
            except ConcurrencyLimitError:
                continue
            except AiError:
                return "limited"
            with lock:
                done.append(request_id)
            store.settle_success(
                _reservation(request_id),
                charged_nano_usd=10,
                usage=_usage(),
                provider_request_id=None,
                now=T0,
            )
        return "gave up"

    results = race(THREADS, worker)

    assert results == ["limited"] * THREADS
    assert len(done) == 3  # never a fourth within the hour
    assert books(factory)[0] == 30


def _usage() -> TransportUsage:
    return TransportUsage(input_tokens=1, output_tokens=1)


# --- stale reservations ----


def test_a_stale_reservation_is_charged_exactly_once_and_the_slot_stays_closed_while_racing(
    factory: sessionmaker[Session],
) -> None:
    store = SqlBudgetStore(factory)
    reserve(store, limits(), T0)  # a crash: it is never settled
    after_lease = T0 + timedelta(seconds=1_000)

    results = race(THREADS, lambda _: reserve(store, limits(), after_lease))

    assert not [r for r in results if isinstance(r, int)]  # nobody starts: it may still be running
    assert all(isinstance(r, ConcurrencyLimitError) for r in results)
    spent, reserved, log = books(factory)
    assert (spent, reserved) == (R, 0)  # charged once, not once per racing thread
    assert log == [("UNKNOWN", R)]

    after_quarantine = after_lease + timedelta(seconds=91)  # one more lease (90 s in these tests)
    results = race(THREADS, lambda _: reserve(store, limits(), after_quarantine))

    assert len([r for r in results if isinstance(r, int)]) == 1  # now exactly one new request
    spent, reserved, log = books(factory)
    assert (spent, reserved) == (R, R)
    assert log == [("UNKNOWN", R), ("RESERVED", 0)]


def test_a_late_settlement_cannot_lower_what_a_sweep_already_charged(
    factory: sessionmaker[Session],
) -> None:
    store = SqlBudgetStore(factory)
    lost = reserve(store, limits(), T0)
    with pytest.raises(ConcurrencyLimitError):  # sweeps `lost`; the slot stays closed
        reserve(store, limits(), T0 + timedelta(seconds=1_000))

    store.settle_success(
        _reservation(lost), charged_nano_usd=5, usage=_usage(), provider_request_id=None, now=T0
    )

    spent, reserved, log = books(factory)
    assert (spent, reserved) == (R, 0)
    assert log == [("UNKNOWN", R)]


# --- restart persistence ----


def test_the_budget_survives_a_restart_with_fresh_connections(
    temp_engine: Engine, factory: sessionmaker[Session]
) -> None:
    lim = limits(ceiling=R)
    before = SqlBudgetStore(factory)
    before.settle_ambiguous(
        _reservation(reserve(before, lim)), error_code="timeout", provider_request_id=None, now=T0
    )

    temp_engine.dispose()  # every pooled connection is closed, as when a process exits
    after = SqlBudgetStore(sessionmaker(bind=temp_engine, expire_on_commit=False))

    assert after.snapshot().spent_nano_usd == R
    with pytest.raises(BudgetExhaustedError):
        reserve(after, lim)


def test_two_processes_share_one_budget(
    temp_engine: Engine, factory: sessionmaker[Session]
) -> None:
    """The API and the worker are separate processes: two stores over separate engines."""
    from sqlalchemy import create_engine

    second_engine = create_engine(temp_engine.url, pool_size=5)
    try:
        api = SqlBudgetStore(factory)
        worker = SqlBudgetStore(sessionmaker(bind=second_engine, expire_on_commit=False))
        api.settle_ambiguous(
            _reservation(reserve(api, limits(interval=30))),
            error_code="timeout",
            provider_request_id=None,
            now=T0,
        )

        with pytest.raises(TooSoonError):  # the worker sees the API's request
            reserve(worker, limits(interval=30), T0 + timedelta(seconds=5))
        assert worker.snapshot().spent_nano_usd == R
    finally:
        second_engine.dispose()


# --- through the gateway: conservative accounting after failures ----


@pytest.fixture
def settings() -> Settings:
    from pydantic import SecretStr

    from .ai_fakes import FAKE_KEY

    return Settings(_env_file=None, ai_enabled=True, anthropic_api_key=SecretStr(FAKE_KEY))


@pytest.mark.parametrize("kind", ["timeout", "connection", "server", "overloaded", "unknown"])
def test_an_unclear_failure_is_charged_in_full_on_postgres(
    factory: sessionmaker[Session], settings: Settings, kind: str
) -> None:
    clock = Clock(T0 + timedelta(days=5))
    gateway = AiGateway(
        settings, FakeTransport(error=upstream(kind)), SqlBudgetStore(factory), clock=clock
    )

    with pytest.raises(UpstreamError):
        gateway.ask("How many drones are charging?")

    spent, reserved, log = books(factory)
    assert reserved == 0 and spent > 0
    assert log == [("AMBIGUOUS", spent)]  # the full reservation, never refunded on a guess


def test_a_rejected_request_is_refunded_and_a_success_is_charged_exactly(
    factory: sessionmaker[Session], settings: Settings
) -> None:
    clock = Clock(T0 + timedelta(days=5))
    transport = FakeTransport(error=upstream("rate_limit", 429))
    gateway = AiGateway(settings, transport, SqlBudgetStore(factory), clock=clock)
    with pytest.raises(UpstreamError):
        gateway.ask("question")
    assert books(factory)[:2] == (0, 0)  # refunded

    clock.advance(31)
    transport.error = None
    answer = gateway.ask("question")

    spent, reserved, _ = books(factory)
    assert (spent, reserved) == (answer.charged_nano_usd, 0)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AiRequestLog)) == 2


def test_the_gateway_never_calls_the_provider_twice_for_racing_asks(
    factory: sessionmaker[Session], settings: Settings
) -> None:
    clock = Clock(T0 + timedelta(days=5))
    transport = FakeTransport()
    gateway = AiGateway(settings, transport, SqlBudgetStore(factory), clock=clock)

    results = race(THREADS, lambda _: gateway.ask("How many drones are charging?"))

    answers = [r for r in results if not isinstance(r, AiError)]
    assert len(answers) == 1 and len(transport.requests) == 1  # one provider call in total
    assert books(factory)[1] == 0  # nothing left reserved
