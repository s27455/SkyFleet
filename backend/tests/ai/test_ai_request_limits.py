"""Question and input size limits, measured on the exact text that is sent."""

import pytest

from app.ai.errors import InvalidQuestionError, PromptTooLargeError
from app.ai.request import (
    REQUEST_OVERHEAD_TOKENS,
    SYSTEM_PROMPT,
    build_user_content,
    prepare_request,
)

LIMITS = {"max_question_chars": 500, "max_input_bytes": 16 * 1024}


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
def test_an_empty_question_is_refused(question: str) -> None:
    with pytest.raises(InvalidQuestionError):
        prepare_request(question, "", **LIMITS)


def test_the_question_limit_is_500_characters() -> None:
    assert prepare_request("a" * 500, "", **LIMITS).user_content.endswith("a" * 500)
    with pytest.raises(InvalidQuestionError, match="500 characters"):
        prepare_request("a" * 501, "", **LIMITS)


def test_the_input_size_counts_everything_that_is_sent() -> None:
    prepared = prepare_request(
        "How many drones are charging?", "Drone DRN-001 is charging.", **LIMITS
    )

    expected = len(SYSTEM_PROMPT.encode()) + len(prepared.user_content.encode())
    assert prepared.input_bytes == expected  # instructions + context + question, nothing outside it
    assert prepared.system == SYSTEM_PROMPT
    assert prepared.user_content == build_user_content(
        "How many drones are charging?", "Drone DRN-001 is charging."
    )


def test_the_limit_is_exact_at_the_boundary() -> None:
    overhead = len(SYSTEM_PROMPT.encode()) + len(build_user_content("q", "x").encode()) - 1
    room = LIMITS["max_input_bytes"] - overhead

    assert prepare_request("q", "x" * room, **LIMITS).input_bytes == LIMITS["max_input_bytes"]
    with pytest.raises(PromptTooLargeError):
        prepare_request("q", "x" * (room + 1), **LIMITS)


def test_the_size_is_measured_in_utf8_bytes_not_characters() -> None:
    question = "ł" * 500  # 500 characters, 1000 bytes

    prepared = prepare_request(question, "", **LIMITS)

    assert len(question) == 500
    assert prepared.input_bytes == len(SYSTEM_PROMPT.encode()) + len(
        build_user_content(question, "").encode()
    )
    assert prepared.input_bytes > len(SYSTEM_PROMPT) + 500 + len("Question:\n")  # bytes > chars


def test_multi_byte_context_cannot_slip_under_a_character_count() -> None:
    context = "ż" * 9_000  # 9,000 characters but 18,000 bytes: over the 16 KiB limit

    with pytest.raises(PromptTooLargeError):
        prepare_request("q", context, **LIMITS)


def test_the_reserved_input_tokens_cover_the_bytes_plus_the_overhead_allowance() -> None:
    prepared = prepare_request("Where is DRN-004?", "DRN-004 is at Forum Gdańsk.", **LIMITS)

    assert prepared.reserved_input_tokens == prepared.input_bytes + REQUEST_OVERHEAD_TOKENS
    assert REQUEST_OVERHEAD_TOKENS >= 1024


def test_the_system_prompt_says_the_assistant_is_read_only() -> None:
    assert "read-only" in SYSTEM_PROMPT and "cannot take actions" in SYSTEM_PROMPT
