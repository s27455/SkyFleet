"""The Copilot service (Feature 026): one question, one gateway call, fixed error codes.

SAME SETTINGS BY CONSTRUCTION. `CopilotService` takes ONE `Settings` and builds the gateway from
it, then hands the same object to `ask_fleet_question` for the fleet context, so the two can never
work from different limits. (Tests inject a fake-transport gateway through `gateway_factory`, which
also receives that same `Settings`.)

ONE REQUEST. `ask` makes exactly one `ask_fleet_question` call, which makes at most one gateway
call. There is no retry, no fallback and no loop here; every Feature 024 control (quota, interval,
one in flight, durable reservation, USD 4 ceiling, no SDK retry) applies inside the gateway.

FIXED ERRORS. Every refusal becomes a `CopilotError` with a fixed code, HTTP status and message.
Exception text, row data, prompts and credentials never reach the response or the log: only the
code (and, for a configuration problem, the NAMES of the settings) is logged.
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session, sessionmaker

from app.ai.errors import (
    AMBIGUOUS_KINDS,
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
)
from app.ai.gateway import AiGateway, build_gateway
from app.ai.readiness import config_problems
from app.config import Settings
from app.copilot.access import token_problem
from app.copilot.schemas import (
    AskResponse,
    ErrorCode,
    NamedDroneInfo,
    OmittedInfo,
    SnapshotInfo,
)
from app.fleet_context.errors import FleetContextTooLargeError, FleetContextUnavailableError
from app.fleet_context.service import ask_fleet_question

logger = logging.getLogger("skyfleet.copilot")

GatewayFactory = Callable[[Settings, sessionmaker[Session]], AiGateway]


def _today() -> date:
    return datetime.now(UTC).date()


class CopilotError(Exception):
    """A refusal with a fixed code, status and message (never exception text)."""

    def __init__(
        self,
        code: ErrorCode,
        status: int,
        message: str,
        *,
        retry_after_seconds: int | None = None,
        charge_possible: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.charge_possible = charge_possible


def copilot_problems(settings: Settings) -> tuple[str, ...]:
    """Every reason the Copilot cannot run, by setting NAME only. Empty when AI is disabled."""
    if not settings.ai_enabled:
        return ()
    problems = list(config_problems(settings, _today()))
    problem = token_problem(settings)
    if problem is not None:
        problems.append(problem)
    return tuple(problems)


def copilot_available(settings: Settings) -> bool:
    return settings.ai_enabled and not copilot_problems(settings)


# --- fixed refusals -----------------------------------------------------------------------------

MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.ORIGIN_NOT_ALLOWED: "This origin is not allowed to use the AI Copilot.",
    ErrorCode.AI_DISABLED: "The AI Copilot is disabled on this server.",
    ErrorCode.AI_MISCONFIGURED: "The AI Copilot is not correctly configured on this server.",
    ErrorCode.UNAUTHORIZED: "A valid access token is required.",
    ErrorCode.AUTH_THROTTLED: "Too many failed attempts. Try again later.",
    ErrorCode.INVALID_QUESTION: (
        "The question must be 1 to 500 characters and must not contain the words 'fleet context'."
    ),
    ErrorCode.CONTEXT_TOO_LARGE: (
        "The question and the fleet snapshot do not fit the AI request size limit."
    ),
    ErrorCode.RATE_LIMITED: "AI requests are limited. Try again later.",
    ErrorCode.BUDGET_EXHAUSTED: "The AI budget is exhausted.",
    ErrorCode.AI_HALTED: "The AI Copilot stopped itself and must be reviewed by an operator.",
    ErrorCode.PROVIDER_UNAVAILABLE: "The AI provider is unavailable. Try again later.",
    ErrorCode.ACCOUNTING_UNAVAILABLE: "The AI budget could not be read; no request was sent.",
    ErrorCode.CONTEXT_UNAVAILABLE: "The fleet snapshot could not be built; no AI request was made.",
    ErrorCode.INTERNAL_ERROR: "The AI Copilot failed unexpectedly.",
}
PROVIDER_REJECTED = "The AI provider rejected the request. No charge is expected."
PROVIDER_UNKNOWN = (
    "The AI provider's answer is unknown and the request may have been charged. "
    "It will not be retried automatically: check the AI ledger and the provider Console first."
)


def refusal(
    code: ErrorCode,
    status: int,
    *,
    message: str | None = None,
    retry_after_seconds: int | None = None,
    charge_possible: bool | None = None,
) -> CopilotError:
    return CopilotError(
        code,
        status,
        message or MESSAGES[code],
        retry_after_seconds=retry_after_seconds,
        charge_possible=charge_possible,
    )


def map_ai_error(error: AiError) -> CopilotError:
    """The fixed refusal for a gateway or fleet-context error; the error's text is dropped."""
    if isinstance(error, AiDisabledError):
        return refusal(ErrorCode.AI_DISABLED, 503)
    if isinstance(error, AiMisconfiguredError):
        logger.warning("copilot misconfigured: %s", "; ".join(error.problems))  # names only
        return refusal(ErrorCode.AI_MISCONFIGURED, 503)
    if isinstance(error, InvalidQuestionError):
        return refusal(ErrorCode.INVALID_QUESTION, 422)
    if isinstance(error, PromptTooLargeError | FleetContextTooLargeError):
        return refusal(ErrorCode.CONTEXT_TOO_LARGE, 413)
    if isinstance(error, TooSoonError | RateLimitedError | ConcurrencyLimitError):
        return refusal(ErrorCode.RATE_LIMITED, 429, retry_after_seconds=error.retry_after_seconds)
    if isinstance(error, BudgetExhaustedError):
        return refusal(ErrorCode.BUDGET_EXHAUSTED, 409)
    if isinstance(error, AiHaltedError):
        return refusal(ErrorCode.AI_HALTED, 409)
    if isinstance(error, ErrorBackoffError):
        return refusal(
            ErrorCode.PROVIDER_UNAVAILABLE, 503, retry_after_seconds=error.retry_after_seconds
        )
    if isinstance(error, AccountingUnavailableError):
        return refusal(ErrorCode.ACCOUNTING_UNAVAILABLE, 503)
    if isinstance(error, FleetContextUnavailableError):
        return refusal(ErrorCode.CONTEXT_UNAVAILABLE, 503)
    if isinstance(error, UpstreamError):
        unknown = error.kind in AMBIGUOUS_KINDS
        return refusal(
            ErrorCode.PROVIDER_UNAVAILABLE,
            502,
            message=PROVIDER_UNKNOWN if unknown else PROVIDER_REJECTED,
            charge_possible=unknown,
        )
    return refusal(ErrorCode.INTERNAL_ERROR, 500)


class CopilotService:
    def __init__(
        self,
        settings: Settings,
        factory: sessionmaker[Session],
        gateway_factory: GatewayFactory = build_gateway,
    ) -> None:
        self.settings = settings
        self._factory = factory
        self._gateway = gateway_factory(settings, factory)

    def ask(self, question: str) -> AskResponse:
        """One question, one gateway call at most; every failure is a `CopilotError`."""
        try:
            result = ask_fleet_question(
                question,
                gateway=self._gateway,
                factory=self._factory,
                settings=self.settings,
            )
        except AiError as error:
            mapped = map_ai_error(error)
            logger.info("copilot refused: %s", mapped.code.value)
            raise mapped from None
        except Exception as error:
            logger.error("copilot failed unexpectedly (%s)", type(error).__name__)
            raise refusal(ErrorCode.INTERNAL_ERROR, 500) from None
        logger.info("copilot answered (snapshot %s)", result.data_status)
        return AskResponse(
            answer=result.answer.text,
            answer_cut_off=result.answer.stop_reason == "max_tokens",
            snapshot=SnapshotInfo(
                captured_at=result.captured_at,
                data_status="degraded" if result.data_status == "degraded" else "complete",
                truncated=result.truncated,
                limitations=list(result.limitations),
                omitted=OmittedInfo(**result.omitted.model_dump()),
                named_drones=[
                    NamedDroneInfo(id=item.id, exists=item.exists, listed=item.listed)
                    for item in result.named_drones
                ],
            ),
        )
