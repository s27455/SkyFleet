"""Typed refusals and failures of the AI gateway.

Every message is safe to show or log: it never contains the key, a prompt, an answer or the text of
a provider error. `code` is a stable machine-readable name.
"""

from enum import StrEnum


class UpstreamKind(StrEnum):
    """What went wrong at the provider, classified only from status, type and error code."""

    AUTHENTICATION = "authentication"  # 401: the key was refused
    PERMISSION = "permission"  # 403
    BILLING = "billing"  # 402: payment or credit problem
    SPEND_LIMIT = "spend_limit"  # 429 with the spend-cap error code
    INVALID_REQUEST = "invalid_request"  # 400/404/413/422: rejected before anything was generated
    RATE_LIMIT = "rate_limit"  # any other 429
    OVERLOADED = "overloaded"  # 529
    SERVER = "server"  # other 5xx
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNKNOWN = "unknown"


# The provider refused the request, so nothing was generated or billed: the reservation is refunded.
REJECTED_KINDS: frozenset[UpstreamKind] = frozenset(
    {
        UpstreamKind.AUTHENTICATION,
        UpstreamKind.PERMISSION,
        UpstreamKind.BILLING,
        UpstreamKind.SPEND_LIMIT,
        UpstreamKind.INVALID_REQUEST,
        UpstreamKind.RATE_LIMIT,
    }
)

# The provider may or may not have generated (and billed) something: the whole reservation is kept
# as spent, never refunded on a guess.
AMBIGUOUS_KINDS: frozenset[UpstreamKind] = frozenset(
    {
        UpstreamKind.OVERLOADED,
        UpstreamKind.SERVER,
        UpstreamKind.TIMEOUT,
        UpstreamKind.CONNECTION,
        UpstreamKind.UNKNOWN,
    }
)

# Failures that say "something is wrong with the key, the balance or the request": no new request
# is sent for a while afterwards, so a bad configuration is not hammered.
BACKOFF_KINDS: frozenset[UpstreamKind] = frozenset(
    {
        UpstreamKind.AUTHENTICATION,
        UpstreamKind.PERMISSION,
        UpstreamKind.BILLING,
        UpstreamKind.SPEND_LIMIT,
        UpstreamKind.INVALID_REQUEST,
    }
)


class AiError(Exception):
    """Base class. `retry_after_seconds` is set when waiting is the remedy."""

    code = "ai_error"

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class AiDisabledError(AiError):
    code = "ai_disabled"

    def __init__(self) -> None:
        super().__init__("The AI assistant is disabled.")


class AiMisconfiguredError(AiError):
    """AI is enabled but its configuration cannot be trusted.

    `problems` name settings, never their values.
    """

    code = "ai_misconfigured"

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("The AI assistant is misconfigured: " + "; ".join(problems))
        self.problems = problems


class InvalidQuestionError(AiError):
    code = "invalid_question"


class PromptTooLargeError(AiError):
    code = "prompt_too_large"


class RateLimitedError(AiError):
    code = "rate_limited"


class TooSoonError(AiError):
    code = "too_soon"


class ConcurrencyLimitError(AiError):
    code = "concurrency_limit"


class BudgetExhaustedError(AiError):
    code = "budget_exhausted"


class ErrorBackoffError(AiError):
    code = "error_backoff"


class AiHaltedError(AiError):
    """The gateway stopped itself (an estimate was exceeded or the accounting disagrees)."""

    code = "ai_halted"


class AccountingUnavailableError(AiError):
    """The budget could not be read or written: no request is sent without a reservation."""

    code = "accounting_unavailable"


class UpstreamError(AiError):
    code = "upstream_error"

    def __init__(
        self,
        kind: UpstreamKind,
        *,
        status_code: int | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(f"The AI provider call failed ({kind.value}).")
        self.kind = kind
        self.status_code = status_code
        self.provider_request_id = provider_request_id
