"""Who may ask the Copilot (Feature 026).

The credential is ONE operator token that lives only in the server's Git-ignored `backend/.env`
(`SKYFLEET_AI_ACCESS_TOKEN`). The operator types it into the Copilot panel, which keeps it in
memory only and sends it as `Authorization: Bearer <token>`. It is never in the frontend bundle,
a URL, a cookie or storage, and it is never logged or returned.

Why this and not CORS, loopback binding or a hidden URL: none of those authenticates anybody. The
checks, in order, all run before any database read, snapshot, reservation or provider call:

 1. `Origin` must be present and in the CORS allow-list (a browser always sends it on a POST, so a
    foreign page and a DNS-rebinding page are refused; a non-browser client must add it).
 2. AI must be enabled and correctly configured (a missing or short token is a configuration
    problem: the route then refuses everybody, it never accepts anonymous callers).
 3. A failed-attempt throttle (below) is not blocking.
 4. The bearer token must match, compared in constant time on SHA-256 digests (so neither the
    content nor the length of the token leaks through timing).

THE THROTTLE is deliberately small: a bounded in-memory sliding window (at most `MAX_FAILURES`
timestamps) kept by the running API process. After `MAX_FAILURES` failed attempts within
`FAILURE_WINDOW_SECONDS` every request is refused with 429 until the oldest failure leaves the
window, a correct token included: that is what makes guessing useless, at the price that someone who
can reach the API can lock the operator out for at most one window. It only ADDS a refusal, it
cannot accept anything, and it never touches the database. It is process-local and resets when the
API restarts (the token's entropy, not the throttle, is the real protection against guessing).
"""

import hashlib
import hmac
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence

from pydantic import SecretStr

from app.config import Settings

MIN_TOKEN_CHARS = 32  # `secrets.token_urlsafe(32)` gives 43
MAX_FAILURES = 10
FAILURE_WINDOW_SECONDS = 60.0


def token_problem(settings: Settings) -> str | None:
    """Why the operator token cannot be used, naming the setting and never a value."""
    token = settings.ai_access_token
    if token is None or not token.get_secret_value().strip():
        return "SKYFLEET_AI_ACCESS_TOKEN is not set"
    if len(token.get_secret_value()) < MIN_TOKEN_CHARS:
        return f"SKYFLEET_AI_ACCESS_TOKEN must be at least {MIN_TOKEN_CHARS} characters"
    return None


def origin_allowed(origin: str | None, allowed: Sequence[str]) -> bool:
    """Exact match against the allow-list; a missing or `null` Origin is never allowed."""
    return origin is not None and origin in allowed


def bearer_token(authorization: str | None) -> str | None:
    """The token of an `Authorization: Bearer <token>` header, or None if it is not one."""
    if authorization is None:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def token_matches(provided: str, expected: SecretStr) -> bool:
    """Constant-time comparison of digests (equal length whatever the tokens are)."""
    return hmac.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.get_secret_value().encode("utf-8")).digest(),
    )


class FailedAuthThrottle:
    """At most `max_failures` recent failure times, process-local, bounded, thread-safe."""

    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILURES,
        window_seconds: float = FAILURE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: deque[float] = deque(maxlen=max_failures)
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] >= self._window:
            self._failures.popleft()

    def retry_after(self) -> int:
        """Seconds until requests are accepted again; 0 when the throttle is not blocking."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            if len(self._failures) < self._max:
                return 0
            return max(1, math.ceil(self._window - (now - self._failures[0])))

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failures.append(now)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
