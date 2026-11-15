"""Is the AI configuration trustworthy? The answer names settings, never their values.

The gateway calls this before every request while AI is enabled and refuses to run with any
problem (fail closed). While AI is disabled nothing is checked, so a missing key can never stop the
API or the worker. The limits can only be tightened: a value beyond the MVP maximum below is a
problem, not something the gateway accepts.
"""

from datetime import date
from decimal import Decimal

from app.ai.pricing import ALLOWED_MODELS, get_pricing, pricing_age_problem
from app.config import Settings

# The MVP maxima (Feature 024). Raising one needs a code change, not just an environment variable.
MAX_INPUT_BYTES = 16 * 1024
MAX_QUESTION_CHARS = 500
MAX_OUTPUT_TOKENS = 400
MAX_REQUESTS_PER_HOUR = 10
MIN_INTERVAL_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60.0
MAX_BUDGET_CEILING_USD = Decimal("4.00")
MIN_ERROR_BACKOFF_SECONDS = 60


def config_problems(settings: Settings, today: date) -> tuple[str, ...]:
    """Every reason the gateway must not run, or an empty tuple. Empty also when AI is disabled."""
    if not settings.ai_enabled:
        return ()
    problems: list[str] = []

    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value().strip():
        problems.append("ANTHROPIC_API_KEY is not set")

    pricing = get_pricing(settings.ai_model)
    if pricing is None:
        allowed = ", ".join(sorted(ALLOWED_MODELS))
        problems.append(
            f"SKYFLEET_AI_MODEL '{settings.ai_model}' is not on the allowlist (allowed: {allowed})"
        )
    else:
        stale = pricing_age_problem(pricing, today)
        if stale:
            problems.append(stale)

    if not 0 < settings.ai_max_input_bytes <= MAX_INPUT_BYTES:
        problems.append(f"SKYFLEET_AI_MAX_INPUT_BYTES must be between 1 and {MAX_INPUT_BYTES}")
    if not 0 < settings.ai_max_question_chars <= MAX_QUESTION_CHARS:
        problems.append(
            f"SKYFLEET_AI_MAX_QUESTION_CHARS must be between 1 and {MAX_QUESTION_CHARS}"
        )
    if not 0 < settings.ai_max_output_tokens <= MAX_OUTPUT_TOKENS:
        problems.append(f"SKYFLEET_AI_MAX_OUTPUT_TOKENS must be between 1 and {MAX_OUTPUT_TOKENS}")
    if not 0 < settings.ai_request_timeout_seconds <= MAX_TIMEOUT_SECONDS:
        problems.append(
            "SKYFLEET_AI_REQUEST_TIMEOUT_SECONDS must be above 0 and at most "
            f"{MAX_TIMEOUT_SECONDS:g}"
        )
    if not 0 < settings.ai_max_requests_per_hour <= MAX_REQUESTS_PER_HOUR:
        problems.append(
            f"SKYFLEET_AI_MAX_REQUESTS_PER_HOUR must be between 1 and {MAX_REQUESTS_PER_HOUR}"
        )
    if settings.ai_min_interval_seconds < MIN_INTERVAL_SECONDS:
        problems.append(f"SKYFLEET_AI_MIN_INTERVAL_SECONDS must be at least {MIN_INTERVAL_SECONDS}")
    if not Decimal(0) < settings.ai_budget_ceiling_usd <= MAX_BUDGET_CEILING_USD:
        problems.append(
            f"SKYFLEET_AI_BUDGET_CEILING_USD must be above 0 and at most {MAX_BUDGET_CEILING_USD}"
        )
    if settings.ai_error_backoff_seconds < MIN_ERROR_BACKOFF_SECONDS:
        problems.append(
            f"SKYFLEET_AI_ERROR_BACKOFF_SECONDS must be at least {MIN_ERROR_BACKOFF_SECONDS}"
        )
    return tuple(problems)
