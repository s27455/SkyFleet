"""The real transport against a fake client: the exact call and the error classification."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.ai.anthropic_transport import (
    API_BASE_URL,
    AnthropicTransport,
    classify_sdk_error,
)
from app.ai.errors import UpstreamError, UpstreamKind
from app.ai.types import TransportRequest

from .ai_fakes import FAKE_KEY

REQUEST = TransportRequest(
    model="claude-haiku-5-5",
    system="SYSTEM TEXT",
    user_content="USER TEXT",
    max_output_tokens=400,
    timeout_seconds=30.0,
)


class FakeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages


def response(
    *,
    blocks: tuple[Any, ...] | None = None,
    usage: Any = "default",
    stop_reason: str | None = "end_turn",
) -> Any:
    content = blocks or (SimpleNamespace(type="text", text="Hello"),)
    if usage == "default":
        usage = SimpleNamespace(
            input_tokens=120,
            output_tokens=30,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
        )
    return SimpleNamespace(
        content=content, usage=usage, stop_reason=stop_reason, _request_id="req_abc"
    )


def transport(messages: FakeMessages) -> AnthropicTransport:
    return AnthropicTransport(
        SecretStr(FAKE_KEY), timeout_seconds=30.0, client=FakeClient(messages)
    )


def status_error(status: int, body: object | None = None) -> anthropic.APIStatusError:
    http_request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    http_response = httpx2.Response(status, request=http_request, headers={"request-id": "req_err"})
    return anthropic.APIStatusError(
        "provider text with sk-ant-LEAK", response=http_response, body=body
    )


# --- the exact call ----


def test_the_call_has_exactly_the_planned_shape_and_nothing_else() -> None:
    messages = FakeMessages(response())

    transport(messages).send(REQUEST)

    (call,) = messages.calls
    assert call == {
        "model": "claude-haiku-5-5",
        "max_tokens": 400,
        "system": "SYSTEM TEXT",
        "messages": [{"role": "user", "content": "USER TEXT"}],
        "thinking": {"type": "disabled"},
        "timeout": 30.0,
    }
    for forbidden in ("tools", "tool_choice", "stream", "betas", "temperature", "top_p", "top_k"):
        assert forbidden not in call  # no tools, no streaming, no beta features: text only


def test_a_successful_response_is_mapped_without_the_sdk_types() -> None:
    result = transport(FakeMessages(response())).send(REQUEST)

    assert result.text == "Hello" and result.stop_reason == "end_turn"
    assert result.provider_request_id == "req_abc"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    assert (result.usage.cache_creation_input_tokens, result.usage.cache_read_input_tokens) == (
        0,
        0,
    )


def test_only_text_blocks_are_returned() -> None:
    blocks = (
        SimpleNamespace(type="thinking", thinking="private reasoning"),
        SimpleNamespace(type="text", text="Part one. "),
        SimpleNamespace(type="tool_use", name="x", input={}),
        SimpleNamespace(type="text", text="Part two."),
    )

    result = transport(FakeMessages(response(blocks=blocks))).send(REQUEST)

    assert result.text == "Part one. Part two."


def test_cache_token_counts_are_carried_into_the_usage() -> None:
    usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=5,
        cache_creation_input_tokens=7,
        cache_read_input_tokens=3,
    )

    result = transport(FakeMessages(response(usage=usage))).send(REQUEST)

    assert result.usage.prompt_tokens == 20


@pytest.mark.parametrize("usage", [None, SimpleNamespace(input_tokens=None, output_tokens=5)])
def test_a_response_without_usable_usage_cannot_be_priced_and_is_an_unknown_failure(
    usage: Any,
) -> None:
    with pytest.raises(UpstreamError) as failed:
        transport(FakeMessages(response(usage=usage))).send(REQUEST)

    assert failed.value.kind is UpstreamKind.UNKNOWN  # the gateway keeps the whole reservation


# --- the client is built safely ----


def test_the_real_client_is_built_without_retries_with_a_fixed_url_and_the_explicit_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            built.update(kwargs)

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://evil.example")  # must never be used
    monkeypatch.setattr(anthropic, "Anthropic", Recorder)

    AnthropicTransport(SecretStr(FAKE_KEY), timeout_seconds=12.5)

    assert API_BASE_URL == "https://api.anthropic.com"
    assert built == {
        "api_key": FAKE_KEY,
        "base_url": "https://api.anthropic.com",
        "max_retries": 0,  # the SDK never retries: every attempt is seen by the budget
        "timeout": 12.5,
    }


def test_the_suite_guard_blocks_a_real_client_even_by_mistake() -> None:
    with pytest.raises(AssertionError, match="must not create a real Anthropic client"):
        anthropic.Anthropic(api_key="x")


def test_the_suite_guard_blocks_any_connection_that_leaves_this_machine() -> None:
    import socket

    sock = socket.socket()
    try:
        with pytest.raises(AssertionError, match="must not connect to the network"):
            sock.connect(("api.anthropic.com", 443))
        with pytest.raises(AssertionError, match="must not connect to the network"):
            sock.connect(("160.79.104.10", 443))
    finally:
        sock.close()


# --- error classification ----


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (
            401,
            {"error": {"type": "authentication_error", "message": "m"}},
            UpstreamKind.AUTHENTICATION,
        ),
        (403, {"error": {"type": "permission_error", "message": "m"}}, UpstreamKind.PERMISSION),
        (402, {"error": {"type": "billing_error", "message": "m"}}, UpstreamKind.BILLING),
        (429, {"error": {"type": "rate_limit_error", "message": "m"}}, UpstreamKind.RATE_LIMIT),
        (
            429,
            {
                "error": {
                    "type": "rate_limit_error",
                    "message": "m",
                    "details": {"error_code": "enforced_spend_limit_reached"},
                }
            },
            UpstreamKind.SPEND_LIMIT,
        ),
        (529, {"error": {"type": "overloaded_error", "message": "m"}}, UpstreamKind.OVERLOADED),
        (500, {"error": {"type": "api_error", "message": "m"}}, UpstreamKind.SERVER),
        (503, None, UpstreamKind.SERVER),
        (408, None, UpstreamKind.TIMEOUT),
        (
            400,
            {"error": {"type": "invalid_request_error", "message": "m"}},
            UpstreamKind.INVALID_REQUEST,
        ),
        (404, None, UpstreamKind.INVALID_REQUEST),
        (413, None, UpstreamKind.INVALID_REQUEST),
        (422, None, UpstreamKind.INVALID_REQUEST),
        (409, None, UpstreamKind.UNKNOWN),
        (418, None, UpstreamKind.UNKNOWN),
    ],
)
def test_provider_errors_are_classified_from_status_type_and_code(
    status: int, body: object | None, kind: UpstreamKind
) -> None:
    classified = classify_sdk_error(status_error(status, body))

    assert classified.kind is kind
    assert classified.status_code == status
    assert classified.provider_request_id == "req_err"


def test_timeouts_and_connection_failures_are_classified_before_status_errors() -> None:
    http_request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    assert classify_sdk_error(anthropic.APITimeoutError(http_request)).kind is UpstreamKind.TIMEOUT
    assert (
        classify_sdk_error(anthropic.APIConnectionError(request=http_request)).kind
        is UpstreamKind.CONNECTION
    )


def test_a_failed_call_raises_a_safe_error_without_the_providers_text() -> None:
    messages = FakeMessages(error=status_error(401, {"error": {"type": "authentication_error"}}))

    with pytest.raises(UpstreamError) as failed:
        transport(messages).send(REQUEST)

    assert failed.value.kind is UpstreamKind.AUTHENTICATION
    assert "sk-ant" not in str(failed.value) and "provider text" not in str(failed.value)
    assert failed.value.__cause__ is None
    assert failed.value.__suppress_context__ is True  # the SDK error does not travel further
    assert len(messages.calls) == 1  # and nothing was retried
