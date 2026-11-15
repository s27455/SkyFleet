"""The access primitives of the Copilot: token rules, Origin, bearer parsing, the throttle."""

import hashlib
import hmac
import threading
from collections import deque
from typing import Any

import pytest
from pydantic import SecretStr

from app.copilot.access import (
    FAILURE_WINDOW_SECONDS,
    MAX_FAILURES,
    MIN_TOKEN_CHARS,
    FailedAuthThrottle,
    bearer_token,
    origin_allowed,
    token_matches,
    token_problem,
)

from .helpers import TOKEN, copilot_settings

# --- the configured token ----------------------------------------------------------------------


def test_the_token_must_be_set_and_at_least_32_characters() -> None:
    assert token_problem(copilot_settings()) is None
    assert token_problem(copilot_settings(ai_access_token="x" * MIN_TOKEN_CHARS)) is None
    assert token_problem(copilot_settings(ai_access_token=None)) == (
        "SKYFLEET_AI_ACCESS_TOKEN is not set"
    )
    assert token_problem(copilot_settings(ai_access_token="   ")) == (
        "SKYFLEET_AI_ACCESS_TOKEN is not set"
    )
    short = token_problem(copilot_settings(ai_access_token="x" * (MIN_TOKEN_CHARS - 1)))
    assert short == "SKYFLEET_AI_ACCESS_TOKEN must be at least 32 characters"


def test_the_problem_text_names_the_setting_and_never_the_value() -> None:
    secret = "s3cr3t-value-" + "z" * 10
    problem = token_problem(copilot_settings(ai_access_token=secret))

    assert problem is not None and secret not in problem and "s3cr3t" not in problem


# --- origin ------------------------------------------------------------------------------------


def test_origin_must_match_the_allow_list_exactly() -> None:
    allowed = ["http://localhost:5173", "http://127.0.0.1:5173"]

    assert origin_allowed("http://localhost:5173", allowed)
    assert origin_allowed("http://127.0.0.1:5173", allowed)
    for bad in (
        None,
        "",
        "null",
        "http://localhost:5174",
        "http://localhost:5173/",
        "HTTP://LOCALHOST:5173",
        "https://localhost:5173",
        "http://localhost:5173.evil.test",
        "http://evil.test",
        "*",
    ):
        assert not origin_allowed(bad, allowed), bad
    assert not origin_allowed("http://localhost:5173", [])  # an empty list allows nobody


# --- bearer parsing ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (f"Bearer {TOKEN}", TOKEN),
        (f"bearer {TOKEN}", TOKEN),
        (f"BEARER    {TOKEN}  ", TOKEN),
        ("Bearer a b", "a b"),
        (None, None),
        ("", None),
        ("Bearer", None),
        ("Bearer   ", None),
        (f"Basic {TOKEN}", None),
        (TOKEN, None),
        (f"Token {TOKEN}", None),
    ],
)
def test_the_bearer_token_is_parsed_strictly(header: str | None, expected: str | None) -> None:
    assert bearer_token(header) == expected


# --- the comparison ----------------------------------------------------------------------------


def test_the_token_comparison_is_exact_and_covers_every_character() -> None:
    expected = SecretStr(TOKEN)

    assert token_matches(TOKEN, expected)
    assert not token_matches("", expected)
    assert not token_matches(TOKEN + "x", expected)
    assert not token_matches(TOKEN[:-1], expected)
    for position in range(len(TOKEN)):  # one wrong character anywhere is a mismatch
        changed = (
            TOKEN[:position] + ("Z" if TOKEN[position] != "Z" else "Y") + TOKEN[position + 1 :]
        )
        assert not token_matches(changed, expected), position
    assert not token_matches("tőkén-" + TOKEN, expected)  # non-ASCII input is simply a mismatch


def test_the_comparison_uses_hmac_compare_digest_on_equal_length_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[int, int]] = []
    real = hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        seen.append((len(a), len(b)))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)

    token_matches("short", SecretStr(TOKEN))
    token_matches(TOKEN * 5, SecretStr(TOKEN))

    # whatever the lengths of the two tokens, the compared values are two 32-byte digests
    assert seen == [(hashlib.sha256().digest_size,) * 2] * 2


# --- the throttle ------------------------------------------------------------------------------


class Ticker:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_it_blocks_only_after_the_limit_and_for_the_rest_of_the_window() -> None:
    ticker = Ticker()
    throttle = FailedAuthThrottle(clock=ticker)

    for number in range(MAX_FAILURES - 1):
        throttle.record_failure()
        assert throttle.retry_after() == 0, number
    throttle.record_failure()  # the tenth

    assert throttle.retry_after() == int(FAILURE_WINDOW_SECONDS)
    ticker.now += 30
    assert throttle.retry_after() == 30
    ticker.now += 29.5
    assert throttle.retry_after() == 1  # never reports 0 while still blocking
    ticker.now += 1
    assert throttle.retry_after() == 0


def test_failures_age_out_one_by_one() -> None:
    ticker = Ticker()
    start = ticker.now
    throttle = FailedAuthThrottle(max_failures=3, window_seconds=10, clock=ticker)
    for offset in (0, 4, 8):  # three failures, at t=0, 4 and 8
        ticker.now = start + offset
        throttle.record_failure()

    assert throttle.retry_after() == 2  # blocked until the first one leaves the window at t=10
    ticker.now = start + 10
    assert throttle.retry_after() == 0  # two failures remain: below the limit again
    throttle.record_failure()  # t=10: the second, third and this one are inside the window
    assert throttle.retry_after() == 4  # blocked until t=14, when the failure of t=4 has left


def test_memory_is_bounded_whatever_the_number_of_failures() -> None:
    throttle = FailedAuthThrottle(clock=Ticker())

    for _ in range(100_000):
        throttle.record_failure()

    failures: deque[float] = throttle._failures  # noqa: SLF001 - the bound is the point
    assert len(failures) <= MAX_FAILURES and failures.maxlen == MAX_FAILURES


def test_reset_clears_the_failures() -> None:
    throttle = FailedAuthThrottle(clock=Ticker())
    for _ in range(MAX_FAILURES):
        throttle.record_failure()
    assert throttle.retry_after() > 0

    throttle.reset()

    assert throttle.retry_after() == 0


def test_it_can_only_refuse_it_has_no_way_to_accept_anything() -> None:
    public = {name for name in dir(FailedAuthThrottle) if not name.startswith("_")}

    assert public == {"retry_after", "record_failure", "reset"}  # no `allow`, `check` or `login`


def test_it_is_thread_safe_and_stays_bounded() -> None:
    throttle = FailedAuthThrottle(clock=Ticker())
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            for _ in range(500):
                throttle.record_failure()
                throttle.retry_after()
        except BaseException as error:  # pragma: no cover - the test fails if this runs
            errors.append(error)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [] and len(throttle._failures) <= MAX_FAILURES  # noqa: SLF001
    assert throttle.retry_after() > 0
