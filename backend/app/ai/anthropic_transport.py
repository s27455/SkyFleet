"""The real transport: one non-streaming Messages API call (the only SDK import).

What it guarantees, and why:

* `max_retries=0`: the SDK would otherwise retry timeouts, 429s and 5xx on its own, which would hide
  attempts from the budget. The gateway counts every attempt itself and never retries.
* A fixed `base_url`: an `ANTHROPIC_BASE_URL` in the environment can never redirect the key.
* The key is passed explicitly from a `SecretStr`; the SDK's environment lookup is not relied on.
* No `tools`, no `tool_choice`, no streaming, no beta features: the model can only return text.
* `thinking` is disabled and `max_tokens` is the hard output cap, so thinking tokens cannot add to
  the bill beyond the reserved amount.
* Errors are classified only from the status code, error type and error code, which the SDK
  documents as stable. The wording of a provider message is never matched, kept or logged.
"""

from typing import Any

import anthropic
from pydantic import SecretStr

from app.ai.errors import UpstreamError, UpstreamKind
from app.ai.types import TransportRequest, TransportResult, TransportUsage

API_BASE_URL = "https://api.anthropic.com"
SPEND_LIMIT_ERROR_CODE = "enforced_spend_limit_reached"


def classify_sdk_error(error: anthropic.APIError) -> UpstreamError:
    """Map an SDK error to an `UpstreamError`, from status, type and error code only."""
    if isinstance(error, anthropic.APITimeoutError):
        return UpstreamError(UpstreamKind.TIMEOUT)
    if isinstance(error, anthropic.APIConnectionError):
        return UpstreamError(UpstreamKind.CONNECTION)
    if not isinstance(error, anthropic.APIStatusError):
        return UpstreamError(UpstreamKind.UNKNOWN)

    status = error.status_code
    error_type = error.type
    kind: UpstreamKind
    if status == 401 or error_type == "authentication_error":
        kind = UpstreamKind.AUTHENTICATION
    elif status == 403 or error_type == "permission_error":
        kind = UpstreamKind.PERMISSION
    elif status == 402 or error_type == "billing_error":
        kind = UpstreamKind.BILLING
    elif status == 429:
        kind = (
            UpstreamKind.SPEND_LIMIT
            if error.error_code == SPEND_LIMIT_ERROR_CODE
            else UpstreamKind.RATE_LIMIT
        )
    elif status == 529 or error_type == "overloaded_error":
        kind = UpstreamKind.OVERLOADED
    elif status == 408:
        kind = UpstreamKind.TIMEOUT
    elif status >= 500:
        kind = UpstreamKind.SERVER
    elif status in (400, 404, 413, 422):
        kind = UpstreamKind.INVALID_REQUEST
    else:
        kind = UpstreamKind.UNKNOWN
    return UpstreamError(kind, status_code=status, provider_request_id=error.request_id)


class AnthropicTransport:
    """Sends one request to the Claude API. Build it once; it holds the (secret) client."""

    def __init__(
        self, api_key: SecretStr, *, timeout_seconds: float, client: Any | None = None
    ) -> None:
        # `client` exists so tests can hand in a fake; production code never passes it.
        self._client: Any = client or anthropic.Anthropic(
            api_key=api_key.get_secret_value(),
            base_url=API_BASE_URL,
            max_retries=0,
            timeout=timeout_seconds,
        )

    def send(self, request: TransportRequest) -> TransportResult:
        try:
            response = self._client.messages.create(
                model=request.model,
                max_tokens=request.max_output_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user_content}],
                thinking={"type": "disabled"},
                timeout=request.timeout_seconds,
            )
        except anthropic.APIError as error:
            # `from None`: nothing from the SDK error (text, response, request) travels further.
            raise classify_sdk_error(error) from None

        usage = getattr(response, "usage", None)
        if usage is None or usage.input_tokens is None or usage.output_tokens is None:
            # A success without usage cannot be priced: the gateway keeps the whole reservation.
            raise UpstreamError(UpstreamKind.UNKNOWN)
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return TransportResult(
            text=text,
            usage=TransportUsage(
                input_tokens=int(usage.input_tokens),
                output_tokens=int(usage.output_tokens),
                cache_creation_input_tokens=int(usage.cache_creation_input_tokens or 0),
                cache_read_input_tokens=int(usage.cache_read_input_tokens or 0),
            ),
            stop_reason=response.stop_reason,
            provider_request_id=getattr(response, "_request_id", None),
        )
