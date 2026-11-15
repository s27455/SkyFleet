"""Durable budget reservation on an in-memory SQLite database.

These tests prove the accounting rules. The row-lock race between real concurrent connections is a
PostgreSQL property and is tested against a temporary PostgreSQL database in Gate B2, after the
migration is approved.
"""

from datetime import timedelta

import pytest
from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import BudgetLimits, Reservation, SqlBudgetStore
from app.ai.errors import (
    AccountingUnavailableError,
    AiHaltedError,
    BudgetExhaustedError,
    ConcurrencyLimitError,
    ErrorBackoffError,
    RateLimitedError,
    TooSoonError,
)
from app.ai.models import AiBudgetState, AiRequestLog, RequestStatus
from app.ai.types import TransportUsage

from .ai_fakes import START, Clock

RESERVED = 1_940_800  # nano-USD, the reservation of a maximal request
USAGE = TransportUsage(input_tokens=1_000, output_tokens=100)
ACTUAL = 1_000 * 100 + 100 * 500  # 150,000 nano-USD


def reserve(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock, amount: int = RESERVED
) -> Reservation:
    return store.reserve(
        model="claude-haiku-5-5",
        reserved_nano_usd=amount,
        request_bytes=2_000,
        limits=limits,
        now=clock(),
    )


def settle_ok(store: SqlBudgetStore, reservation: Reservation, clock: Clock) -> None:
    store.settle_success(
        reservation, charged_nano_usd=ACTUAL, usage=USAGE, provider_request_id="req_1", now=clock()
    )


def rows(factory: sessionmaker[Session]) -> list[AiRequestLog]:
    with factory() as session:
        return list(session.scalars(select(AiRequestLog).order_by(AiRequestLog.id)))


# --- reservation and the three kinds of settlement ----


def test_a_reservation_is_recorded_before_anything_is_sent(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    reservation = reserve(store, limits, clock)

    snapshot = store.snapshot()
    assert (snapshot.spent_nano_usd, snapshot.reserved_nano_usd) == (0, RESERVED)
    (row,) = rows(session_factory)
    assert row.id == reservation.request_id
    assert (row.status, row.reserved_nano_usd, row.charged_nano_usd) == ("RESERVED", RESERVED, 0)
    assert row.request_bytes == 2_000 and row.model == "claude-haiku-5-5"


def test_success_charges_the_real_cost_and_releases_the_rest(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    reservation = reserve(store, limits, clock)

    settle_ok(store, reservation, clock)

    snapshot = store.snapshot()
    assert (snapshot.spent_nano_usd, snapshot.reserved_nano_usd) == (ACTUAL, 0)
    (row,) = rows(session_factory)
    assert (row.status, row.charged_nano_usd) == ("SUCCEEDED", ACTUAL)
    assert (row.prompt_tokens, row.output_tokens) == (1_000, 100)
    assert row.provider_request_id == "req_1" and row.finished_at is not None


def test_a_request_the_provider_rejected_is_refunded(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    reservation = reserve(store, limits, clock)

    store.settle_rejected(
        reservation, error_code="rate_limit", provider_request_id=None, now=clock()
    )

    snapshot = store.snapshot()
    assert (snapshot.spent_nano_usd, snapshot.reserved_nano_usd) == (0, 0)
    (row,) = rows(session_factory)
    assert (row.status, row.charged_nano_usd, row.error_code) == ("REJECTED", 0, "rate_limit")


def test_an_unclear_outcome_is_charged_in_full_never_refunded(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    reservation = reserve(store, limits, clock)

    store.settle_ambiguous(reservation, error_code="timeout", provider_request_id=None, now=clock())

    snapshot = store.snapshot()
    assert (snapshot.spent_nano_usd, snapshot.reserved_nano_usd) == (RESERVED, 0)
    (row,) = rows(session_factory)
    assert (row.status, row.charged_nano_usd) == ("AMBIGUOUS", RESERVED)


def test_the_budget_row_is_created_once(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    for _ in range(3):
        settle_ok(store, reserve(store, limits, clock), clock)
        clock.advance(31)

    with session_factory() as session:
        assert len(session.scalars(select(AiBudgetState)).all()) == 1
    assert store.snapshot().spent_nano_usd == 3 * ACTUAL


# --- the lifetime ceiling ----


def test_the_ceiling_counts_unknown_outcomes_and_a_refund_frees_room(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    tight = BudgetLimits(2 * RESERVED, 10, 30, 90, 900)
    first = reserve(store, tight, clock)
    store.settle_ambiguous(first, error_code="timeout", provider_request_id=None, now=clock())
    clock.advance(31)
    second = reserve(store, tight, clock)  # spent R + reserved R: exactly at the ceiling, allowed
    store.settle_ambiguous(second, error_code="timeout", provider_request_id=None, now=clock())
    clock.advance(31)

    with pytest.raises(BudgetExhaustedError):  # two unknown outcomes used the whole ceiling
        reserve(store, tight, clock)

    assert store.snapshot().spent_nano_usd == 2 * RESERVED

    roomy = BudgetLimits(3 * RESERVED, 10, 30, 90, 900)
    third = reserve(store, roomy, clock)  # the same books under a higher ceiling
    store.settle_rejected(third, error_code="rate_limit", provider_request_id=None, now=clock())
    clock.advance(31)
    assert reserve(store, roomy, clock).request_id  # the refund released its reservation


def test_a_held_reservation_counts_toward_the_ceiling(store: SqlBudgetStore, clock: Clock) -> None:
    store.settle_ambiguous(
        reserve(store, BudgetLimits(2 * RESERVED, 10, 30, 90, 900), clock),
        error_code="timeout",
        provider_request_id=None,
        now=clock(),
    )
    clock.advance(31)
    held = reserve(store, BudgetLimits(2 * RESERVED, 10, 30, 90, 900), clock)

    snapshot = store.snapshot()
    assert snapshot.spent_nano_usd + snapshot.reserved_nano_usd == 2 * RESERVED
    assert held.reserved_nano_usd == RESERVED


def test_a_request_that_would_cross_the_ceiling_by_one_nano_dollar_is_refused(
    store: SqlBudgetStore, clock: Clock
) -> None:
    tight = BudgetLimits(RESERVED - 1, 10, 30, 90, 900)

    with pytest.raises(BudgetExhaustedError):
        reserve(store, tight, clock)

    assert store.snapshot().reserved_nano_usd == 0


def test_the_ceiling_and_the_spend_survive_a_restart(
    session_factory: sessionmaker[Session], limits: BudgetLimits, clock: Clock
) -> None:
    tight = BudgetLimits(RESERVED, 10, 30, 90, 900)
    before = SqlBudgetStore(session_factory)
    before.settle_ambiguous(
        reserve(before, tight, clock), error_code="timeout", provider_request_id=None, now=clock()
    )
    clock.advance(31)

    after = SqlBudgetStore(session_factory)  # a new process: nothing in memory

    assert after.snapshot().spent_nano_usd == RESERVED
    with pytest.raises(BudgetExhaustedError):
        reserve(after, tight, clock)


# --- the rate limits ----


def test_two_requests_must_be_at_least_30_seconds_apart(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    settle_ok(store, reserve(store, limits, clock), clock)
    clock.advance(10)

    with pytest.raises(TooSoonError) as refused:
        reserve(store, limits, clock)

    assert refused.value.retry_after_seconds == 20
    clock.advance(20)
    assert reserve(store, limits, clock).request_id


def test_ten_requests_per_hour_and_the_eleventh_waits_for_the_oldest_to_expire(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    first_time = clock()
    for _ in range(10):
        settle_ok(store, reserve(store, limits, clock), clock)
        clock.advance(31)

    with pytest.raises(RateLimitedError) as refused:
        reserve(store, limits, clock)

    waited = (first_time + timedelta(hours=1) - clock()).total_seconds()
    assert refused.value.retry_after_seconds == pytest.approx(waited, abs=1)
    clock.advance(waited + 1)  # the first request has left the one-hour window
    assert reserve(store, limits, clock).request_id


def test_only_one_request_may_be_in_flight(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    held = reserve(store, limits, clock)
    clock.advance(31)  # well past the minimum interval, but the first is still unsettled

    with pytest.raises(ConcurrencyLimitError):
        reserve(store, limits, clock)

    settle_ok(store, held, clock)
    assert reserve(store, limits, clock).request_id


# --- crashes: unsettled reservations ----


def test_an_unsettled_reservation_is_charged_in_full_once_it_is_stale(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    lost = reserve(store, limits, clock)  # a crash: nobody settles it
    clock.advance(limits.stale_after_seconds + 1)

    with pytest.raises(ConcurrencyLimitError):  # the sweep happens, but the slot stays closed
        reserve(store, limits, clock)
    swept = store.snapshot()
    assert (swept.spent_nano_usd, swept.reserved_nano_usd) == (RESERVED, 0)  # charged in full
    clock.advance(limits.stale_after_seconds + 1)  # one more lease: the lost request is long over
    fresh = reserve(store, limits, clock)

    snapshot = store.snapshot()
    assert snapshot.spent_nano_usd == RESERVED  # the lost one, charged in full
    assert snapshot.reserved_nano_usd == RESERVED  # the new one
    first, second = rows(session_factory)
    assert (first.id, first.status, first.charged_nano_usd) == (
        lost.request_id,
        "UNKNOWN",
        RESERVED,
    )
    assert first.error_code == "stale_reservation" and second.id == fresh.request_id


def test_a_reservation_is_not_swept_before_it_is_stale(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    reserve(store, limits, clock)
    clock.advance(limits.stale_after_seconds - 1)

    with pytest.raises(ConcurrencyLimitError):  # still in flight, not lost
        reserve(store, limits, clock)


def test_a_late_settlement_of_a_swept_request_never_lowers_the_charge(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    lost = reserve(store, limits, clock)
    clock.advance(limits.stale_after_seconds + 1)
    with pytest.raises(ConcurrencyLimitError):  # sweeps `lost`; the slot stays closed
        reserve(store, limits, clock)

    settle_ok(store, lost, clock)  # the original request finally reports a (smaller) cost

    assert store.snapshot().spent_nano_usd == RESERVED  # still the conservative charge
    assert rows(session_factory)[0].status == "UNKNOWN"


def test_a_late_settlement_that_costs_more_than_the_charge_adds_the_difference(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    lost = reserve(store, limits, clock)
    clock.advance(limits.stale_after_seconds + 1)
    with pytest.raises(ConcurrencyLimitError):  # sweeps `lost`
        reserve(store, limits, clock)

    store.settle_success(
        lost,
        charged_nano_usd=RESERVED + 777,
        usage=USAGE,
        provider_request_id=None,
        now=clock(),
    )

    assert store.snapshot().spent_nano_usd == RESERVED + 777


def test_after_a_sweep_the_slot_stays_closed_for_one_more_lease(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    lease = limits.stale_after_seconds
    reserve(store, limits, clock)  # outlives its lease: it may still be running
    clock.advance(lease + 1)
    with pytest.raises(ConcurrencyLimitError):  # swept here, at time T
        reserve(store, limits, clock)

    clock.advance(lease - 10)  # T + lease - 10: still inside the quarantine
    with pytest.raises(ConcurrencyLimitError) as waiting:
        reserve(store, limits, clock)
    assert waiting.value.retry_after_seconds == 10

    clock.advance(11)  # T + lease + 1: two leases after the first request began
    assert reserve(store, limits, clock).request_id


def test_a_request_is_never_granted_within_two_leases_of_an_unsettled_one(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    started = clock()
    reserve(store, limits, clock)  # never settled
    lease = limits.stale_after_seconds

    granted_at: list[float] = []
    for second in range(0, 3 * lease, 7):  # probe every 7 s across three leases
        clock.now = started + timedelta(seconds=second)
        try:
            reserve(store, limits, clock)
        except ConcurrencyLimitError:
            continue
        granted_at.append(second)
        break

    assert granted_at and granted_at[0] > 2 * lease  # the first grant is after both leases


def test_a_swept_request_that_finishes_late_does_not_reopen_the_slot_early(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    lost = reserve(store, limits, clock)
    clock.advance(limits.stale_after_seconds + 1)
    with pytest.raises(ConcurrencyLimitError):  # swept
        reserve(store, limits, clock)

    settle_ok(store, lost, clock)  # it reports in, late

    with pytest.raises(ConcurrencyLimitError):  # no early reopening on the strength of a report
        reserve(store, limits, clock)


# --- back-off after a key, balance or request failure ----


def test_after_a_key_or_balance_failure_no_request_is_sent_for_the_back_off_period(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    store.settle_rejected(
        reserve(store, limits, clock),
        error_code="authentication",
        provider_request_id=None,
        now=clock(),
    )
    clock.advance(60)

    with pytest.raises(ErrorBackoffError) as refused:
        reserve(store, limits, clock)

    assert refused.value.retry_after_seconds == 900 - 60
    clock.advance(841)
    assert reserve(store, limits, clock).request_id


@pytest.mark.parametrize("code", ["rate_limit", "timeout", "server"])
def test_other_failures_do_not_start_a_back_off(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock, code: str
) -> None:
    store.settle_rejected(
        reserve(store, limits, clock), error_code=code, provider_request_id=None, now=clock()
    )
    clock.advance(31)

    assert reserve(store, limits, clock).request_id


# --- the breaker and the books ----


def test_a_halted_store_refuses_everything_until_a_person_clears_it(
    store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    store.halt("ESTIMATE_EXCEEDED", clock())

    with pytest.raises(AiHaltedError, match="ESTIMATE_EXCEEDED"):
        reserve(store, limits, clock)

    snapshot = store.snapshot()
    assert snapshot.halted and snapshot.halt_reason == "ESTIMATE_EXCEEDED"


def test_the_store_halts_itself_when_the_budget_row_and_the_log_disagree(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    settle_ok(store, reserve(store, limits, clock), clock)
    clock.advance(31)
    with session_factory() as session:  # someone edits the budget row by hand
        session.execute(update(AiBudgetState).values(spent_nano_usd=5))
        session.commit()

    with pytest.raises(AiHaltedError):
        reserve(store, limits, clock)

    snapshot = store.snapshot()
    assert snapshot.halted and snapshot.halt_reason == "ACCOUNTING_INCONSISTENT"
    clock.advance(31)
    with pytest.raises(AiHaltedError):  # and it stays closed
        reserve(store, limits, clock)


def test_deleted_log_rows_are_detected_as_an_inconsistency(
    store: SqlBudgetStore,
    limits: BudgetLimits,
    clock: Clock,
    session_factory: sessionmaker[Session],
) -> None:
    settle_ok(store, reserve(store, limits, clock), clock)
    clock.advance(31)
    with session_factory() as session:
        session.execute(text("DELETE FROM ai_request_log"))
        session.commit()

    with pytest.raises(AiHaltedError):
        reserve(store, limits, clock)


# --- fail closed when the accounting cannot be used ----


def test_without_the_accounting_tables_no_reservation_is_made(
    engine: Engine, store: SqlBudgetStore, limits: BudgetLimits, clock: Clock
) -> None:
    with engine.begin() as connection:  # the state of a database where the migration is not applied
        connection.execute(text("DROP TABLE ai_request_log"))
        connection.execute(text("DROP TABLE ai_budget_state"))

    with pytest.raises(AccountingUnavailableError) as failed:
        reserve(store, limits, clock)

    assert "no request was sent" in str(failed.value)
    assert failed.value.__cause__ is None  # nothing from the database error travels further
    with pytest.raises(AccountingUnavailableError):
        store.snapshot()
    with pytest.raises(AccountingUnavailableError):
        store.halt("X", clock())


def test_the_records_hold_numbers_and_codes_only() -> None:
    columns = {column.name for column in AiRequestLog.__table__.columns}

    assert columns == {
        "id",
        "created_at",
        "finished_at",
        "model",
        "status",
        "request_bytes",
        "reserved_nano_usd",
        "charged_nano_usd",
        "prompt_tokens",
        "output_tokens",
        "error_code",
        "provider_request_id",
    }  # no column could hold a prompt, an answer, a key or a provider message
    assert {column.name for column in AiBudgetState.__table__.columns} == {
        "name",
        "spent_nano_usd",
        "reserved_nano_usd",
        "halted",
        "halt_reason",
        "updated_at",
    }
    assert {status.value for status in RequestStatus} == {
        "RESERVED",
        "SUCCEEDED",
        "REJECTED",
        "AMBIGUOUS",
        "UNKNOWN",
    }
    assert START.year == 2026
