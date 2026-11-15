"""Fakes for the AI tests. Nothing here can reach the network or read real credentials."""

from datetime import UTC, datetime, timedelta

from app.ai.errors import UpstreamError
from app.ai.types import TransportRequest, TransportResult, TransportUsage

FAKE_KEY = "sk-ant-api03-THIS-IS-A-FAKE-TEST-KEY"
START = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)  # five days after the prices were verified


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def ok_result(
    *, prompt_tokens: int = 1_000, output_tokens: int = 100, text: str = "An answer."
) -> TransportResult:
    return TransportResult(
        text=text,
        usage=TransportUsage(input_tokens=prompt_tokens, output_tokens=output_tokens),
        stop_reason="end_turn",
        provider_request_id="req_fake_001",
    )


class FakeTransport:
    """Records every request and either returns a result or raises the given error."""

    def __init__(
        self,
        result: TransportResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or ok_result()
        self.error = error
        self.requests: list[TransportRequest] = []

    def send(self, request: TransportRequest) -> TransportResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def upstream(kind_name: str, status: int | None = None) -> UpstreamError:
    from app.ai.errors import UpstreamKind

    return UpstreamError(UpstreamKind(kind_name), status_code=status)
