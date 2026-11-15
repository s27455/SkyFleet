"""Typed refusals of the fleet context. Both derive from `AiError`, so a caller handles them like
every other refusal of the AI gateway. Messages are fixed text: no database error, row or secret
ever travels in them."""

from app.ai.errors import AiError


class FleetContextUnavailableError(AiError):
    """A trustworthy snapshot could not be built. Nothing was reserved and nothing was sent."""

    code = "fleet_context_unavailable"


class FleetContextTooLargeError(AiError):
    """Even the smallest honest snapshot does not fit the request budget. Nothing was sent."""

    code = "fleet_context_too_large"
