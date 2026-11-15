"""AI configuration: disabled by default, explicit validation, no secret in any diagnostic."""

import json
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr

from app.ai.errors import AiMisconfiguredError
from app.ai.pricing import ALLOWED_MODELS, PRICING_MAX_AGE_DAYS
from app.ai.readiness import config_problems
from app.config import Settings

from .ai_fakes import FAKE_KEY, START

TODAY = START.date()
Make = Callable[..., Settings]


def test_ai_is_disabled_and_has_no_key_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_enabled is False
    assert settings.anthropic_api_key is None
    assert settings.ai_model == "claude-haiku-5-5"
    assert settings.ai_max_input_bytes == 16 * 1024
    assert settings.ai_max_question_chars == 500
    assert settings.ai_max_output_tokens == 400
    assert settings.ai_max_requests_per_hour == 10
    assert settings.ai_min_interval_seconds == 30
    assert settings.ai_budget_ceiling_usd == Decimal("4.00")


def test_a_disabled_ai_is_never_a_problem_even_with_nonsense_settings() -> None:
    settings = Settings(
        _env_file=None,
        ai_enabled=False,
        ai_model="whatever",
        ai_max_requests_per_hour=0,
        ai_budget_ceiling_usd=Decimal("-1"),
    )

    assert config_problems(settings, TODAY) == ()


def test_enabled_without_a_key_is_a_problem_that_names_the_setting_only(
    make_settings: Make,
) -> None:
    for key in (None, SecretStr(""), SecretStr("   ")):
        problems = config_problems(make_settings(anthropic_api_key=key), TODAY)

        assert problems == ("ANTHROPIC_API_KEY is not set",)


def test_a_valid_configuration_has_no_problems(make_settings: Make) -> None:
    assert config_problems(make_settings(), TODAY) == ()


def test_the_model_must_be_on_the_allowlist(make_settings: Make) -> None:
    problems = config_problems(make_settings(ai_model="claude-opus-5-5"), TODAY)

    assert len(problems) == 1 and "not on the allowlist" in problems[0]
    assert all(model in problems[0] for model in ALLOWED_MODELS)


def test_stale_prices_close_the_gateway(make_settings: Make) -> None:
    verified = ALLOWED_MODELS["claude-haiku-5-5"].verified_on
    ok_day = verified + timedelta(days=PRICING_MAX_AGE_DAYS)
    stale_day = verified + timedelta(days=PRICING_MAX_AGE_DAYS + 1)

    assert config_problems(make_settings(), ok_day) == ()
    problems = config_problems(make_settings(), stale_day)
    assert len(problems) == 1 and "verify them against the official pricing page" in problems[0]


@pytest.mark.parametrize(
    ("override", "setting"),
    [
        ({"ai_max_input_bytes": 16 * 1024 + 1}, "SKYFLEET_AI_MAX_INPUT_BYTES"),
        ({"ai_max_input_bytes": 0}, "SKYFLEET_AI_MAX_INPUT_BYTES"),
        ({"ai_max_question_chars": 501}, "SKYFLEET_AI_MAX_QUESTION_CHARS"),
        ({"ai_max_output_tokens": 401}, "SKYFLEET_AI_MAX_OUTPUT_TOKENS"),
        ({"ai_max_output_tokens": 0}, "SKYFLEET_AI_MAX_OUTPUT_TOKENS"),
        ({"ai_request_timeout_seconds": 61.0}, "SKYFLEET_AI_REQUEST_TIMEOUT_SECONDS"),
        ({"ai_request_timeout_seconds": 0.0}, "SKYFLEET_AI_REQUEST_TIMEOUT_SECONDS"),
        ({"ai_max_requests_per_hour": 11}, "SKYFLEET_AI_MAX_REQUESTS_PER_HOUR"),
        ({"ai_max_requests_per_hour": 0}, "SKYFLEET_AI_MAX_REQUESTS_PER_HOUR"),
        ({"ai_min_interval_seconds": 29}, "SKYFLEET_AI_MIN_INTERVAL_SECONDS"),
        ({"ai_budget_ceiling_usd": Decimal("4.01")}, "SKYFLEET_AI_BUDGET_CEILING_USD"),
        ({"ai_budget_ceiling_usd": Decimal("0")}, "SKYFLEET_AI_BUDGET_CEILING_USD"),
        ({"ai_budget_ceiling_usd": Decimal("-4")}, "SKYFLEET_AI_BUDGET_CEILING_USD"),
        ({"ai_error_backoff_seconds": 59}, "SKYFLEET_AI_ERROR_BACKOFF_SECONDS"),
    ],
)
def test_a_limit_beyond_the_mvp_maximum_is_refused_not_accepted(
    make_settings: Make, override: dict[str, Any], setting: str
) -> None:
    problems = config_problems(make_settings(**override), TODAY)

    assert len(problems) == 1 and problems[0].startswith(setting)


def test_the_limits_can_be_tightened(make_settings: Make) -> None:
    settings = make_settings(
        ai_max_input_bytes=4096,
        ai_max_question_chars=200,
        ai_max_output_tokens=100,
        ai_max_requests_per_hour=2,
        ai_min_interval_seconds=120,
        ai_budget_ceiling_usd=Decimal("1.50"),
    )

    assert config_problems(settings, TODAY) == ()


def test_no_diagnostic_contains_a_secret_or_a_setting_value(make_settings: Make) -> None:
    settings = make_settings(ai_model="not-a-model", ai_max_requests_per_hour=99)

    problems = config_problems(settings, TODAY)
    error = AiMisconfiguredError(problems)

    for text in (*problems, str(error), repr(error)):
        assert FAKE_KEY not in text and "sk-ant" not in text
        assert "99" not in text  # the offending value is not echoed, only the setting name
    assert error.problems == problems


def test_the_key_is_masked_in_every_representation(make_settings: Make) -> None:
    settings = make_settings()

    for text in (
        repr(settings),
        str(settings),
        str(settings.model_dump()),
        json.dumps(settings.model_dump(mode="json")),
        repr(settings.anthropic_api_key),
    ):
        assert FAKE_KEY not in text
    assert settings.anthropic_api_key is not None
    assert (
        settings.anthropic_api_key.get_secret_value() == FAKE_KEY
    )  # only an explicit call reads it


def test_the_variables_are_read_from_the_environment_under_the_spec_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SKYFLEET_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("SKYFLEET_AI_MAX_REQUESTS_PER_HOUR", "5")
    monkeypatch.setenv("SKYFLEET_AI_BUDGET_CEILING_USD", "2.5")

    settings = Settings(_env_file=None)

    assert settings.ai_enabled is True
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == FAKE_KEY
    assert settings.ai_max_requests_per_hour == 5
    assert settings.ai_budget_ceiling_usd == Decimal("2.5")
    assert config_problems(settings, TODAY) == ()


def test_the_tests_start_without_ai_environment_variables() -> None:
    import os

    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "SKYFLEET_AI_ENABLED",
    ):
        assert name not in os.environ  # removed by the suite-wide guard for every test


def test_the_date_used_for_the_price_check_is_the_gateways_clock_date() -> None:
    assert TODAY == date(2026, 11, 20)
