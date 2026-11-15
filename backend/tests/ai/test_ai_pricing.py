"""The model allowlist and the exact (integer) cost arithmetic."""

import random
from datetime import date, timedelta

import pytest

from app.ai.pricing import (
    ALLOWED_MODELS,
    NANO_USD_PER_USD,
    PRICING_MAX_AGE_DAYS,
    actual_cost_nano_usd,
    get_pricing,
    pricing_age_problem,
    reservation_nano_usd,
)
from app.ai.request import REQUEST_OVERHEAD_TOKENS
from app.ai.types import TransportUsage

HAIKU = ALLOWED_MODELS["claude-haiku-5-5"]


def test_the_allowlist_ties_each_model_id_to_its_own_prices() -> None:
    assert set(ALLOWED_MODELS) == {"claude-haiku-5-5"}
    for model_id, pricing in ALLOWED_MODELS.items():
        assert pricing.model_id == model_id
        assert pricing.tiers[-1].up_to_prompt_tokens is None  # the last tier has no limit
    assert get_pricing("claude-opus-5-5") is None  # not allow-listed: never usable
    assert get_pricing("claude-haiku-5-5-20260101") is None  # no invented variants


def test_the_haiku_5_5_prices_match_the_verified_documentation() -> None:
    base, long_prompt = HAIKU.tiers
    # USD per million tokens x 1000 = nano-USD per token
    assert (base.up_to_prompt_tokens, base.input_nano_usd, base.output_nano_usd) == (
        100_000,
        100,  # $0.10 / MTok
        500,  # $0.50 / MTok
    )
    assert (
        base.cache_read_nano_usd,
        base.cache_write_5m_nano_usd,
        base.cache_write_1h_nano_usd,
    ) == (
        10,  # $0.01
        125,  # $0.125
        200,  # $0.20
    )
    assert (long_prompt.input_nano_usd, long_prompt.output_nano_usd) == (
        500,
        2_500,
    )  # $0.50 / $2.50
    assert (long_prompt.cache_read_nano_usd, long_prompt.cache_write_1h_nano_usd) == (50, 1_000)
    assert HAIKU.verified_on == date(2026, 11, 15)


def test_actual_cost_is_exact_integer_arithmetic() -> None:
    usage = TransportUsage(input_tokens=1_000, output_tokens=200)

    assert actual_cost_nano_usd(HAIKU, usage) == 1_000 * 100 + 200 * 500  # 200,000 nano-USD
    assert actual_cost_nano_usd(HAIKU, usage) / NANO_USD_PER_USD == pytest.approx(0.0002)
    assert isinstance(actual_cost_nano_usd(HAIKU, usage), int)


def test_cache_tokens_are_priced_and_count_toward_the_prompt_size() -> None:
    usage = TransportUsage(
        input_tokens=10, output_tokens=0, cache_creation_input_tokens=20, cache_read_input_tokens=30
    )

    assert usage.prompt_tokens == 60
    # writes at the dearer 1-hour rate (the usage does not say which lifetime was used)
    assert actual_cost_nano_usd(HAIKU, usage) == 10 * 100 + 20 * 200 + 30 * 10


def test_the_price_tier_switches_above_100_000_prompt_tokens_including_cache() -> None:
    at_limit = TransportUsage(input_tokens=100_000, output_tokens=1)
    over = TransportUsage(input_tokens=100_001, output_tokens=1)
    mostly_cached = TransportUsage(
        input_tokens=1, output_tokens=1, cache_read_input_tokens=100_000
    )  # 100,001 prompt tokens: the cache reads count toward the tier

    assert actual_cost_nano_usd(HAIKU, at_limit) == 100_000 * 100 + 500
    assert actual_cost_nano_usd(HAIKU, over) == 100_001 * 500 + 2_500
    assert actual_cost_nano_usd(HAIKU, mostly_cached) == 1 * 500 + 100_000 * 50 + 2_500


def test_the_reservation_for_the_mvp_limits() -> None:
    reserved_input = 16 * 1024 + REQUEST_OVERHEAD_TOKENS  # the largest request plus the overhead

    reserved = reservation_nano_usd(HAIKU, reserved_input, 400)

    assert reserved == 17_408 * 100 + 400 * 500 == 1_940_800  # $0.0019408
    ceiling = 4 * NANO_USD_PER_USD
    assert ceiling // reserved == 2_061  # worst-case requests the $4 ceiling pays for


def test_a_reservation_over_the_tier_threshold_is_priced_at_the_higher_tier() -> None:
    assert reservation_nano_usd(HAIKU, 100_001, 400) == 100_001 * 500 + 400 * 2_500


def test_the_reservation_is_never_below_the_actual_cost_when_the_assumptions_hold() -> None:
    rng = random.Random(24)
    for _ in range(2_000):
        reserved_input = rng.randint(1_100, 16_384 + REQUEST_OVERHEAD_TOKENS)
        max_output = rng.randint(1, 400)
        usage = TransportUsage(
            input_tokens=rng.randint(0, reserved_input), output_tokens=rng.randint(0, max_output)
        )

        assert actual_cost_nano_usd(HAIKU, usage) <= reservation_nano_usd(
            HAIKU, reserved_input, max_output
        )


def test_prices_older_than_the_limit_are_reported_as_stale() -> None:
    fresh = HAIKU.verified_on + timedelta(days=PRICING_MAX_AGE_DAYS)
    stale = HAIKU.verified_on + timedelta(days=PRICING_MAX_AGE_DAYS + 1)

    assert pricing_age_problem(HAIKU, fresh) is None
    problem = pricing_age_problem(HAIKU, stale)
    assert problem is not None and "claude-haiku-5-5" in problem and "official pricing" in problem
