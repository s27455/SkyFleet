"""The single entry point for asking the model something. Fail closed at every step.

`AiGateway.ask(question, context)` does, in this order, and stops at the first refusal:

1. refuse unless AI is enabled (then nothing else is looked at, no database, no network);
2. refuse unless the configuration passes `readiness.config_problems` (key, model allowlist,
   price freshness, limits at or below the MVP maxima);
3. validate and measure the request (question length, total input bytes);
4. reserve the worst-case cost durably and atomically, which also enforces the hourly quota, the
   minimum interval, one request at a time, the error back-off and the lifetime budget;
5. send exactly one request: no retry, ever;
6. settle the reservation by what happened (success: real cost; rejected: refund; unclear: keep);
7. verify the assumptions behind the reservation against the provider's own token counts, and halt
   the gateway if they were wrong.

The model gets no tools and the gateway reaches no domain data: it returns text. Nothing here stores
or logs a key, a question, a context or an answer.
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import BudgetLimits, BudgetStore, Reservation, SqlBudgetStore
from app.ai.errors import (
    AMBIGUOUS_KINDS,
    AccountingUnavailableError,
    AiDisabledError,
    AiMisconfiguredError,
    UpstreamError,
    UpstreamKind,
)
from app.ai.pricing import (
    NANO_USD_PER_USD,
    ModelPricing,
    actual_cost_nano_usd,
    get_pricing,
    reservation_nano_usd,
)
from app.ai.readiness import config_problems
from app.ai.request import prepare_request
from app.ai.types import AiAnswer, AiTransport, TransportRequest, TransportResult
from app.config import Settings

logger = logging.getLogger("skyfleet.ai")

# The lease of a reservation: the longest a request may plausibly stay alive. The SDK caps a
# non-streaming request at 10 minutes, and the transport timeout applies per phase (connect, write,
# read, pool), so four times the timeout plus a margin is the other bound; the larger one wins. An
# unsettled reservation older than the lease is charged in full, and the slot stays closed for one
# more lease (see `budget.py`).
MIN_LEASE_SECONDS = 600
LEASE_MARGIN_SECONDS = 60
PHASES_PER_REQUEST = 4
HALT_ESTIMATE_EXCEEDED = "ESTIMATE_EXCEEDED"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def lease_seconds(request_timeout_seconds: float) -> int:
    """How long a reservation may stay unsettled before it is treated as possibly still running."""
    per_phase_bound = PHASES_PER_REQUEST * int(request_timeout_seconds) + LEASE_MARGIN_SECONDS
    return max(MIN_LEASE_SECONDS, per_phase_bound)


class AiGateway:
    def __init__(
        self,
        settings: Settings,
        transport: AiTransport | None,
        store: BudgetStore | None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._store = store
        self._clock = clock

    def ask(self, question: str, context: str = "") -> AiAnswer:
        settings = self._settings
        if not settings.ai_enabled:
            raise AiDisabledError

        now = self._clock()
        problems = config_problems(settings, now.date())
        pricing = get_pricing(settings.ai_model)
        if problems or pricing is None or self._transport is None or self._store is None:
            raise AiMisconfiguredError(problems or ("the gateway has no transport or budget",))

        prepared = prepare_request(
            question,
            context,
            max_question_chars=settings.ai_max_question_chars,
            max_input_bytes=settings.ai_max_input_bytes,
        )
        reserved = reservation_nano_usd(
            pricing, prepared.reserved_input_tokens, settings.ai_max_output_tokens
        )
        reservation = self._store.reserve(
            model=settings.ai_model,
            reserved_nano_usd=reserved,
            request_bytes=prepared.input_bytes,
            limits=self._limits(settings),
            now=now,
        )

        request = TransportRequest(
            model=settings.ai_model,
            system=prepared.system,
            user_content=prepared.user_content,
            max_output_tokens=settings.ai_max_output_tokens,
            timeout_seconds=settings.ai_request_timeout_seconds,
        )
        try:
            result = self._transport.send(request)
        except UpstreamError as error:
            self._settle_failure(reservation, error)
            raise
        except Exception:
            # Something the transport did not classify: whether anything was billed is unknown.
            unclassified = UpstreamError(UpstreamKind.UNKNOWN)
            self._settle_failure(reservation, unclassified)
            raise unclassified from None

        return self._settle_success(
            reservation, result, pricing, prepared.reserved_input_tokens, settings
        )

    # --- settlement ---------------------------------------------------------------------------

    def _settle_failure(self, reservation: Reservation, error: UpstreamError) -> None:
        assert self._store is not None
        now = self._clock()
        try:
            if error.kind in AMBIGUOUS_KINDS:
                self._store.settle_ambiguous(
                    reservation,
                    error_code=error.kind.value,
                    provider_request_id=error.provider_request_id,
                    now=now,
                )
            else:
                self._store.settle_rejected(
                    reservation,
                    error_code=error.kind.value,
                    provider_request_id=error.provider_request_id,
                    now=now,
                )
        except AccountingUnavailableError:
            # The reservation stays held and is charged in full by the next stale sweep.
            logger.error("AI request %s: could not settle the failure", reservation.request_id)
        logger.warning(
            "ai_request id=%s outcome=failed kind=%s status=%s provider_request_id=%s",
            reservation.request_id,
            error.kind.value,
            error.status_code,
            error.provider_request_id,
        )

    def _settle_success(
        self,
        reservation: Reservation,
        result: TransportResult,
        pricing: ModelPricing,
        reserved_input_tokens: int,
        settings: Settings,
    ) -> AiAnswer:
        assert self._store is not None
        usage = result.usage
        charged = actual_cost_nano_usd(pricing, usage)
        # The reservation assumed the prompt fits `reserved_input_tokens` and the output fits the
        # cap. The provider's own counts are the check: if either assumption was wrong, the real
        # cost is charged and the gateway stops itself instead of carrying on.
        exceeded = (
            usage.prompt_tokens > reserved_input_tokens
            or usage.output_tokens > settings.ai_max_output_tokens
        )
        now = self._clock()
        try:
            self._store.settle_success(
                reservation,
                charged_nano_usd=charged,
                usage=usage,
                provider_request_id=result.provider_request_id,
                now=now,
            )
            if exceeded:
                self._store.halt(HALT_ESTIMATE_EXCEEDED, now)
        except AccountingUnavailableError:
            # The answer was generated and is returned; the reservation stays held and is charged
            # in full by the next stale sweep, so the books can only be more conservative.
            logger.error("AI request %s: could not settle the success", reservation.request_id)
        logger.info(
            "ai_request id=%s outcome=succeeded model=%s prompt_tokens=%s output_tokens=%s "
            "charged_nano_usd=%s%s",
            reservation.request_id,
            reservation.model,
            usage.prompt_tokens,
            usage.output_tokens,
            charged,
            " HALTED:estimate_exceeded" if exceeded else "",
        )
        return AiAnswer(
            text=result.text,
            stop_reason=result.stop_reason,
            prompt_tokens=usage.prompt_tokens,
            output_tokens=usage.output_tokens,
            charged_nano_usd=charged,
            request_id=reservation.request_id,
            provider_request_id=result.provider_request_id,
        )

    @staticmethod
    def _limits(settings: Settings) -> BudgetLimits:
        return BudgetLimits(
            ceiling_nano_usd=int(settings.ai_budget_ceiling_usd * NANO_USD_PER_USD),
            max_requests_per_hour=settings.ai_max_requests_per_hour,
            min_interval_seconds=settings.ai_min_interval_seconds,
            stale_after_seconds=lease_seconds(settings.ai_request_timeout_seconds),
            error_backoff_seconds=settings.ai_error_backoff_seconds,
        )


def build_gateway(
    settings: Settings,
    session_factory: sessionmaker[Session],
    *,
    today: date | None = None,
) -> AiGateway:
    """The real gateway. With AI disabled or misconfigured it is built without a transport, so
    nothing is created that could reach the network, and `ask` refuses with a typed error."""
    problems = config_problems(settings, today or _utc_now().date())
    key = settings.anthropic_api_key
    if not settings.ai_enabled or problems or key is None:
        return AiGateway(settings, None, None)
    from app.ai.anthropic_transport import AnthropicTransport  # the only import of the SDK

    transport = AnthropicTransport(key, timeout_seconds=settings.ai_request_timeout_seconds)
    return AiGateway(settings, transport, SqlBudgetStore(session_factory))
