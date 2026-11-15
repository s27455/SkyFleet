"""The model allowlist: each model identifier together with its prices, in integer nano-USD.

A model is usable only if it is listed here, and its prices cannot be configured separately, so an
identifier can never be paired with the wrong price. All amounts are whole numbers of nano-USD
(1e-9 USD) per token, so cost arithmetic is exact and has no floating-point error.

The table records the day it was checked against the official documentation. Prices change: once
the entry is older than `PRICING_MAX_AGE_DAYS` the readiness check refuses to run the gateway until
someone re-verifies the prices against the official pricing page and updates this file.

Source: https://platform.claude.com/docs/en/about-claude/pricing and
https://platform.claude.com/docs/en/about-claude/models/overview (checked 2026-11-15).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from app.ai.types import TransportUsage

NANO_USD_PER_USD = 1_000_000_000
PRICING_MAX_AGE_DAYS = 90


@dataclass(frozen=True)
class PriceTier:
    """Prices per token for prompts up to `up_to_prompt_tokens` (None: no upper limit)."""

    up_to_prompt_tokens: int | None
    input_nano_usd: int
    output_nano_usd: int
    cache_read_nano_usd: int
    cache_write_5m_nano_usd: int
    cache_write_1h_nano_usd: int


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    verified_on: date
    tiers: tuple[PriceTier, ...]  # ordered by `up_to_prompt_tokens`; the last has no limit


# $/MTok x 1000 = nano-USD per token. Claude Haiku 5.5 is priced by prompt length: a request
# whose prompt (all input tokens, cache reads and writes included) is over 100,000 tokens pays the
# higher prices for that request.
_HAIKU_5_5 = ModelPricing(
    model_id="claude-haiku-5-5",
    verified_on=date(2026, 11, 15),
    tiers=(
        PriceTier(100_000, 100, 500, 10, 125, 200),  # $0.10 / $0.50, cache $0.01 / $0.125 / $0.20
        PriceTier(None, 500, 2_500, 50, 625, 1_000),  # $0.50 / $2.50, cache $0.05 / $0.625 / $1
    ),
)

ALLOWED_MODELS: Mapping[str, ModelPricing] = {_HAIKU_5_5.model_id: _HAIKU_5_5}


def get_pricing(model_id: str) -> ModelPricing | None:
    return ALLOWED_MODELS.get(model_id)


def pricing_age_problem(pricing: ModelPricing, today: date) -> str | None:
    """A message when the entry is too old to trust, else None."""
    age_days = (today - pricing.verified_on).days
    if age_days > PRICING_MAX_AGE_DAYS:
        return (
            f"the prices of model '{pricing.model_id}' were last verified {age_days} days ago "
            f"(limit {PRICING_MAX_AGE_DAYS}); verify them against the official pricing page and "
            "update app/ai/pricing.py"
        )
    return None


def _tier_for(pricing: ModelPricing, prompt_tokens: int) -> PriceTier:
    for tier in pricing.tiers:
        if tier.up_to_prompt_tokens is None or prompt_tokens <= tier.up_to_prompt_tokens:
            return tier
    return pricing.tiers[-1]  # unreachable: the last tier has no limit


def reservation_nano_usd(
    pricing: ModelPricing, reserved_input_tokens: int, max_output_tokens: int
) -> int:
    """The most one request can cost: every reserved input token plus the full output cap.

    The price tier follows the reserved prompt size, so a bigger request is never priced too low.
    """
    tier = _tier_for(pricing, reserved_input_tokens)
    return reserved_input_tokens * tier.input_nano_usd + max_output_tokens * tier.output_nano_usd


def actual_cost_nano_usd(pricing: ModelPricing, usage: TransportUsage) -> int:
    """What the provider's reported usage cost. The tier follows the provider's own prompt count.

    Cache writes are priced at the more expensive 1-hour rate because the usage totals do not say
    which lifetime was used (caching is not enabled by the gateway, so this is normally zero).
    """
    tier = _tier_for(pricing, usage.prompt_tokens)
    return (
        usage.input_tokens * tier.input_nano_usd
        + usage.cache_creation_input_tokens * tier.cache_write_1h_nano_usd
        + usage.cache_read_input_tokens * tier.cache_read_nano_usd
        + usage.output_tokens * tier.output_nano_usd
    )
