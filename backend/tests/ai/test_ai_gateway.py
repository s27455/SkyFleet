"""The gateway end to end with a fake transport and the real budget store (in-memory SQLite)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import BudgetLimits, BudgetSnapshot, Reservation, SqlBudgetStore
from app.ai.errors import (
    AMBIGUOUS_KINDS,
    REJECTED_KINDS,
    AccountingUnavailableError,
    AiDisabledError,
    AiError,
    AiHaltedError,
    AiMisconfiguredError,
    BudgetExhaustedError,
    ConcurrencyLimitError,
    ErrorBackoffError,
    InvalidQuestionError,
    PromptTooLargeError,
    RateLimitedError,
    TooSoonError,
    UpstreamError,
    UpstreamKind,
)
from app.ai.gateway import AiGateway, build_gateway, lease_seconds
from app.ai.models import AiRequestLog
from app.ai.pricing import ALLOWED_MODELS, actual_cost_nano_usd, reservation_nano_usd
from app.ai.request import SYSTEM_PROMPT, prepare_request
from app.ai.types import TransportRequest, TransportResult, TransportUsage
from app.config import Settings

from .ai_fakes import FAKE_KEY, Clock, FakeTransport, ok_result, upstream

Make = Callable[..., tuple[AiGateway, FakeTransport]]
QUESTION = "How many drones are charging right now?"
CONTEXT = "Drone DRN-001 is CHARGING at Forum Gdańsk."
HAIKU = ALLOWED_MODELS["claude-haiku-5-5"]


class ExplodingStore:
    """A budget that must never be touched (used where the gateway has to refuse first)."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"the budget was touched ({name})")


def log_rows(factory: sessionmaker[Session]) -> list[AiRequestLog]:
    with factory() as session:
        return list(session.scalars(select(AiRequestLog).order_by(AiRequestLog.id)))


def snapshot(factory: sessionmaker[Session]) -> BudgetSnapshot:
    return SqlBudgetStore(factory).snapshot()


# --- disabled and misconfigured ----


def test_a_disabled_gateway_refuses_before_touching_anything(
    make_settings: Callable[..., Settings], clock: Clock
) -> None:
    transport = FakeTransport()
    gateway = AiGateway(make_settings(ai_enabled=False), transport, ExplodingStore(), clock=clock)  # type: ignore[arg-type]

    with pytest.raises(AiDisabledError):
        gateway.ask(QUESTION, CONTEXT)

    assert transport.requests == []


def test_the_default_settings_build_a_gateway_that_cannot_reach_anything(
    session_factory: sessionmaker[Session],
) -> None:
    gateway = build_gateway(Settings(_env_file=None), session_factory)

    with pytest.raises(AiDisabledError):
        gateway.ask(QUESTION)


def test_an_enabled_but_misconfigured_gateway_refuses_with_safe_problems(
    make_settings: Callable[..., Settings],
    session_factory: sessionmaker[Session],
    clock: Clock,
) -> None:
    settings = make_settings(anthropic_api_key=None)
    transport = FakeTransport()
    gateway = AiGateway(settings, transport, SqlBudgetStore(session_factory), clock=clock)

    with pytest.raises(AiMisconfiguredError) as refused:
        gateway.ask(QUESTION)

    assert refused.value.problems == ("ANTHROPIC_API_KEY is not set",)
    assert transport.requests == [] and log_rows(session_factory) == []
    # build_gateway creates no transport at all in this state
    built = build_gateway(settings, session_factory, today=clock().date())
    with pytest.raises(AiMisconfiguredError):
        built.ask(QUESTION)


def test_stale_prices_stop_the_gateway(
    make_gateway: Make, clock: Clock, session_factory: sessionmaker[Session]
) -> None:
    gateway, transport = make_gateway()
    clock.advance(200 * 24 * 3600)  # far past the 90 days the prices are trusted for

    with pytest.raises(AiMisconfiguredError, match="official pricing page"):
        gateway.ask(QUESTION)

    assert transport.requests == [] and log_rows(session_factory) == []


# --- the success path ----


def test_a_successful_request_reserves_sends_once_and_charges_the_real_cost(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, transport = make_gateway(FakeTransport(ok_result(prompt_tokens=600, output_tokens=80)))

    answer = gateway.ask(QUESTION, CONTEXT)

    expected = actual_cost_nano_usd(HAIKU, TransportUsage(input_tokens=600, output_tokens=80))
    assert (answer.text, answer.prompt_tokens, answer.output_tokens) == ("An answer.", 600, 80)
    assert answer.charged_nano_usd == expected == 600 * 100 + 80 * 500
    assert answer.provider_request_id == "req_fake_001"
    (request,) = transport.requests  # exactly one request, no retry
    prepared = prepare_request(QUESTION, CONTEXT, max_question_chars=500, max_input_bytes=16384)
    assert request.model == "claude-haiku-5-5"
    assert request.system == SYSTEM_PROMPT == prepared.system
    assert request.user_content == prepared.user_content
    assert (request.max_output_tokens, request.timeout_seconds) == (400, 30.0)
    state = snapshot(session_factory)
    assert (state.spent_nano_usd, state.reserved_nano_usd, state.halted) == (expected, 0, False)
    (row,) = log_rows(session_factory)
    assert (row.status, row.charged_nano_usd, row.id) == ("SUCCEEDED", expected, answer.request_id)


def test_the_reservation_is_the_pessimistic_worst_case_of_that_request(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, _ = make_gateway()
    gateway.ask(QUESTION, CONTEXT)

    prepared = prepare_request(QUESTION, CONTEXT, max_question_chars=500, max_input_bytes=16384)
    (row,) = log_rows(session_factory)

    assert row.reserved_nano_usd == reservation_nano_usd(HAIKU, prepared.input_bytes + 1024, 400)
    assert row.request_bytes == prepared.input_bytes
    assert row.reserved_nano_usd > row.charged_nano_usd  # the unused part was released


def test_nothing_is_reserved_for_an_invalid_or_oversized_request(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, transport = make_gateway()

    with pytest.raises(InvalidQuestionError):
        gateway.ask("  ")
    with pytest.raises(InvalidQuestionError):
        gateway.ask("q" * 501)
    with pytest.raises(PromptTooLargeError):
        gateway.ask("q", "c" * 16_400)

    assert transport.requests == [] and log_rows(session_factory) == []
    assert snapshot(session_factory).spent_nano_usd == 0


# --- limits through the gateway ----


def test_the_interval_and_the_hourly_quota_apply_to_every_request(
    make_gateway: Make, clock: Clock
) -> None:
    gateway, transport = make_gateway()
    gateway.ask(QUESTION)
    clock.advance(10)
    with pytest.raises(TooSoonError):
        gateway.ask(QUESTION)
    assert len(transport.requests) == 1

    for _ in range(9):
        clock.advance(31)
        gateway.ask(QUESTION)
    clock.advance(31)
    with pytest.raises(RateLimitedError):
        gateway.ask(QUESTION)
    assert len(transport.requests) == 10


def test_an_exhausted_budget_refuses_without_sending(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, transport = make_gateway(
        ai_budget_ceiling_usd=Decimal("0.0001")
    )  # below the smallest possible reservation

    with pytest.raises(BudgetExhaustedError):
        gateway.ask(QUESTION)

    assert transport.requests == []
    assert snapshot(session_factory).reserved_nano_usd == 0


def test_the_internal_ceiling_is_enforced_over_many_requests(
    make_gateway: Make, clock: Clock
) -> None:
    # A ceiling that fits exactly two worst-case reservations, with every outcome ambiguous
    # (the most expensive kind): the third request is refused.
    prepared = prepare_request(QUESTION, "", max_question_chars=500, max_input_bytes=16384)
    one = reservation_nano_usd(HAIKU, prepared.reserved_input_tokens, 400)
    gateway, transport = make_gateway(
        FakeTransport(error=upstream("timeout")),
        ai_budget_ceiling_usd=Decimal(2 * one) / Decimal(1_000_000_000),
    )

    for _ in range(2):
        with pytest.raises(UpstreamError):
            gateway.ask(QUESTION)
        clock.advance(31)
    with pytest.raises(BudgetExhaustedError):
        gateway.ask(QUESTION)

    assert len(transport.requests) == 2


# --- failures at the provider: refund or keep, never retry ----


@pytest.mark.parametrize("kind", sorted(REJECTED_KINDS))
def test_a_rejected_request_is_refunded_and_not_retried(
    make_gateway: Make, session_factory: sessionmaker[Session], kind: UpstreamKind
) -> None:
    gateway, transport = make_gateway(FakeTransport(error=upstream(kind.value, 400)))

    with pytest.raises(UpstreamError) as failed:
        gateway.ask(QUESTION)

    assert failed.value.kind is kind
    assert len(transport.requests) == 1
    state = snapshot(session_factory)
    assert (state.spent_nano_usd, state.reserved_nano_usd) == (0, 0)
    (row,) = log_rows(session_factory)
    assert (row.status, row.charged_nano_usd, row.error_code) == ("REJECTED", 0, kind.value)


@pytest.mark.parametrize("kind", sorted(AMBIGUOUS_KINDS))
def test_an_unclear_failure_keeps_the_whole_reservation_as_spent(
    make_gateway: Make, session_factory: sessionmaker[Session], kind: UpstreamKind
) -> None:
    gateway, transport = make_gateway(FakeTransport(error=upstream(kind.value, 500)))

    with pytest.raises(UpstreamError) as failed:
        gateway.ask(QUESTION)

    assert failed.value.kind is kind
    assert len(transport.requests) == 1  # no retry, ever
    (row,) = log_rows(session_factory)
    assert (row.status, row.error_code) == ("AMBIGUOUS", kind.value)
    state = snapshot(session_factory)
    assert (state.spent_nano_usd, state.reserved_nano_usd) == (row.reserved_nano_usd, 0)


def test_an_unclassified_transport_error_is_charged_and_its_text_is_not_passed_on(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, _ = make_gateway(FakeTransport(error=RuntimeError(f"boom with {FAKE_KEY}")))

    with pytest.raises(UpstreamError) as failed:
        gateway.ask(QUESTION)

    assert failed.value.kind is UpstreamKind.UNKNOWN
    assert "boom" not in str(failed.value) and FAKE_KEY not in str(failed.value)
    assert failed.value.__cause__ is None
    (row,) = log_rows(session_factory)
    assert row.status == "AMBIGUOUS"  # whether anything was billed is unknown: charged in full


def test_a_key_or_balance_failure_starts_a_back_off_but_a_rate_limit_does_not(
    make_gateway: Make, clock: Clock
) -> None:
    gateway, transport = make_gateway(FakeTransport(error=upstream("authentication", 401)))
    with pytest.raises(UpstreamError):
        gateway.ask(QUESTION)
    clock.advance(31)
    transport.error = None

    with pytest.raises(ErrorBackoffError):
        gateway.ask(QUESTION)
    assert len(transport.requests) == 1  # the second ask never reached the provider
    clock.advance(900)
    assert gateway.ask(QUESTION).text  # the back-off is over

    other, other_transport = make_gateway(FakeTransport(error=upstream("rate_limit", 429)))
    clock.advance(31)
    with pytest.raises(UpstreamError):
        other.ask(QUESTION)
    clock.advance(31)
    other_transport.error = None
    assert other.ask(QUESTION).text  # an ordinary rate limit is not a configuration problem


# --- the safeguards around the reservation assumptions ----


def test_a_prompt_larger_than_reserved_halts_the_gateway_after_charging_the_real_cost(
    make_gateway: Make, session_factory: sessionmaker[Session], clock: Clock
) -> None:
    gateway, transport = make_gateway(FakeTransport(ok_result(prompt_tokens=40_000)))

    answer = gateway.ask(QUESTION)  # the answer exists and is returned

    assert answer.charged_nano_usd == 40_000 * 100 + 100 * 500  # the real cost, not the estimate
    state = snapshot(session_factory)
    assert state.spent_nano_usd == answer.charged_nano_usd
    assert state.halted and state.halt_reason == "ESTIMATE_EXCEEDED"
    clock.advance(31)
    with pytest.raises(AiHaltedError):
        gateway.ask(QUESTION)
    assert len(transport.requests) == 1


def test_more_output_than_the_cap_also_halts_the_gateway(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    gateway, _ = make_gateway(FakeTransport(ok_result(output_tokens=401)))

    gateway.ask(QUESTION)

    assert snapshot(session_factory).halted


def test_usage_within_the_reservation_never_halts(
    make_gateway: Make, session_factory: sessionmaker[Session]
) -> None:
    prepared = prepare_request(QUESTION, "", max_question_chars=500, max_input_bytes=16384)
    gateway, _ = make_gateway(
        FakeTransport(ok_result(prompt_tokens=prepared.reserved_input_tokens, output_tokens=400))
    )

    answer = gateway.ask(QUESTION)  # exactly at the bound: allowed

    assert not snapshot(session_factory).halted
    (row,) = log_rows(session_factory)
    assert answer.charged_nano_usd <= row.reserved_nano_usd


# --- the accounting store failing ----


def test_without_the_accounting_tables_nothing_is_sent(make_gateway: Make, engine: Engine) -> None:
    gateway, transport = make_gateway()
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE ai_request_log"))
        connection.execute(text("DROP TABLE ai_budget_state"))

    with pytest.raises(AccountingUnavailableError):
        gateway.ask(QUESTION)

    assert transport.requests == []


class FailingSettleStore(SqlBudgetStore):
    """A store whose settlements fail (the database went away after the send)."""

    def _settle(self, *args: object, **kwargs: object) -> None:
        raise AccountingUnavailableError("no settlement")


def test_a_failed_settlement_never_hides_the_answer_and_the_next_sweep_charges_in_full(
    make_settings: Callable[..., Settings],
    session_factory: sessionmaker[Session],
    clock: Clock,
) -> None:
    gateway = AiGateway(
        make_settings(), FakeTransport(), FailingSettleStore(session_factory), clock=clock
    )

    answer = gateway.ask(QUESTION)  # the provider answered; the books could not be updated

    assert answer.text == "An answer."
    (row,) = log_rows(session_factory)
    assert row.status == "RESERVED"  # held, not forgotten
    healthy = AiGateway(
        make_settings(), FakeTransport(), SqlBudgetStore(session_factory), clock=clock
    )
    clock.advance(31)
    with pytest.raises(ConcurrencyLimitError, match="still in progress"):
        healthy.ask(QUESTION)  # still held: conservative
    clock.advance(lease_seconds(30.0))
    with pytest.raises(ConcurrencyLimitError, match="may still be active"):
        healthy.ask(QUESTION)  # past its lease: swept and charged in full, slot still closed
    clock.advance(lease_seconds(30.0) + 1)
    healthy.ask(QUESTION)  # a further lease later: allowed
    first = log_rows(session_factory)[0]
    assert (first.status, first.charged_nano_usd) == ("UNKNOWN", first.reserved_nano_usd)


def test_the_lease_covers_the_sdk_cap_and_every_phase_timeout() -> None:
    assert lease_seconds(30.0) == 600  # the SDK caps a non-streaming request at 10 minutes
    assert lease_seconds(60.0) == 600  # the largest timeout the readiness check accepts
    assert lease_seconds(200.0) == 4 * 200 + 60  # four phases at a larger timeout would exceed it


def test_the_gateway_hands_the_lease_to_the_budget(
    make_settings: Callable[..., Settings],
) -> None:
    assert AiGateway._limits(make_settings()).stale_after_seconds == 600


def test_a_slow_request_never_overlaps_the_next_one(
    make_settings: Callable[..., Settings],
    session_factory: sessionmaker[Session],
    clock: Clock,
) -> None:
    """The first provider call stays in the air; others ask while time passes (the old 90 s
    cutoff would have let the second one start at the first probe)."""
    settings = make_settings()
    store = SqlBudgetStore(session_factory)
    second_transport = FakeTransport()
    second = AiGateway(settings, second_transport, store, clock=clock)
    started = clock()
    outcomes: dict[int, str] = {}

    class SlowTransport(FakeTransport):
        def send(self, request: TransportRequest) -> TransportResult:
            for seconds in (100, 590, 700, 1250, 1301):
                clock.now = started + timedelta(seconds=seconds)
                try:
                    second.ask(QUESTION)
                    outcomes[seconds] = "answered"
                except AiError as error:
                    outcomes[seconds] = type(error).__name__
            return super().send(request)

    first = AiGateway(settings, SlowTransport(), store, clock=clock)

    answer = first.ask(QUESTION)  # the slow request finally answers, after everything above

    assert answer.text == "An answer."
    assert outcomes == {
        100: "ConcurrencyLimitError",  # beyond the old 90 s cutoff: refused, first still held
        590: "ConcurrencyLimitError",  # just inside the lease
        700: "ConcurrencyLimitError",  # lease over: swept and charged, slot still closed
        1250: "ConcurrencyLimitError",  # inside the quarantine that follows the sweep
        1301: "answered",  # two leases after the first began
    }
    assert len(second_transport.requests) == 1  # one provider call, and only at the end
    unknown, succeeded = log_rows(session_factory)
    assert (unknown.status, unknown.error_code) == ("UNKNOWN", "stale_reservation")
    assert unknown.charged_nano_usd == unknown.reserved_nano_usd  # charged in full, not the answer
    assert succeeded.status == "SUCCEEDED"
    state = snapshot(session_factory)
    assert state.spent_nano_usd == unknown.reserved_nano_usd + succeeded.charged_nano_usd
    assert state.reserved_nano_usd == 0 and not state.halted


def test_a_failed_settlement_after_a_provider_error_still_raises_the_provider_error(
    make_settings: Callable[..., Settings],
    session_factory: sessionmaker[Session],
    clock: Clock,
) -> None:
    gateway = AiGateway(
        make_settings(),
        FakeTransport(error=upstream("timeout")),
        FailingSettleStore(session_factory),
        clock=clock,
    )

    with pytest.raises(UpstreamError) as failed:
        gateway.ask(QUESTION)

    assert failed.value.kind is UpstreamKind.TIMEOUT


# --- nothing sensitive is stored or logged ----


def test_no_prompt_answer_or_key_is_stored_or_logged(
    make_gateway: Make,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
    clock: Clock,
) -> None:
    secret_question = "Where is the SECRET-PROMPT-MARKER drone?"
    secret_context = "SECRET-CONTEXT-MARKER: DRN-777 at the depot."
    secret_answer = "SECRET-ANSWER-MARKER: it is at the depot."
    gateway, transport = make_gateway(FakeTransport(ok_result(text=secret_answer)))

    with caplog.at_level(logging.DEBUG):
        gateway.ask(secret_question, secret_context)
        clock.advance(31)
        transport.error = upstream("server", 500)
        with pytest.raises(UpstreamError):
            gateway.ask(secret_question, secret_context)

    dump = "\n".join(
        str(row)
        for table in ("ai_request_log", "ai_budget_state")
        for row in _all_rows(session_factory, table)
    )
    everything = dump + caplog.text
    for marker in (
        "SECRET-PROMPT-MARKER",
        "SECRET-CONTEXT-MARKER",
        "SECRET-ANSWER-MARKER",
        FAKE_KEY,
    ):
        assert marker not in everything
    assert "ai_request id=" in caplog.text  # the safe metrics are logged


def _all_rows(factory: sessionmaker[Session], table: str) -> list[tuple[object, ...]]:
    with factory() as session:
        return [tuple(row) for row in session.execute(text(f"SELECT * FROM {table}"))]


def test_the_clock_used_for_limits_is_the_injected_one(
    make_gateway: Make, session_factory: sessionmaker[Session], clock: Clock
) -> None:
    gateway, _ = make_gateway()
    gateway.ask(QUESTION)

    (row,) = log_rows(session_factory)

    assert isinstance(clock(), datetime)
    assert row.created_at.replace(tzinfo=clock().tzinfo) == clock()


def test_reservation_objects_are_plain_values() -> None:
    reservation = Reservation(1, 2, "m")
    limits = BudgetLimits(1, 1, 1, 1, 1)

    assert (reservation.request_id, limits.ceiling_nano_usd) == (1, 1)
