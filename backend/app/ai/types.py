"""Plain data types shared by the gateway, the transports and the budget (no SDK, no database)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TransportRequest:
    """Everything sent to the model: one system text, one user text, a hard output cap."""

    model: str
    system: str
    user_content: str
    max_output_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class TransportUsage:
    """Provider-reported token usage of one successful call."""

    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        """All input the provider counted for this request (what the price tier is based on)."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


@dataclass(frozen=True)
class TransportResult:
    text: str
    usage: TransportUsage
    stop_reason: str | None
    provider_request_id: str | None


class AiTransport(Protocol):
    """The only way the gateway reaches a model. Raises `UpstreamError` for provider failures."""

    def send(self, request: TransportRequest) -> TransportResult: ...


@dataclass(frozen=True)
class AiAnswer:
    """What a caller gets back. Costs are integer nano-USD (1e-9 USD)."""

    text: str
    stop_reason: str | None
    prompt_tokens: int
    output_tokens: int
    charged_nano_usd: int
    request_id: int
    provider_request_id: str | None
