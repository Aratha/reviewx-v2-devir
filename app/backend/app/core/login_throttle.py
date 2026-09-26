"""In-process limit on failed login attempts (rules/58 rate limit).

The key is the account name together with the client address, so a stranger cannot lock the real
user out of their own address. Each process keeps its own counters: behind a reverse proxy the
client address is the proxy's, and several replicas each count separately. A shared limit at the
ingress or WAF remains an operations decision.
"""

import math
import time
from collections import deque
from collections.abc import Callable

MAX_FAILED_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
_MAX_TRACKED_KEYS = 10_000

LoginKey = tuple[str, str]


class LoginThrottle:
    def __init__(
        self,
        *,
        max_failures: int = MAX_FAILED_ATTEMPTS,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[LoginKey, deque[float]] = {}

    def retry_after(self, key: LoginKey) -> int | None:
        """Return the seconds to wait when the key has used up its attempts, otherwise None."""

        failures = self._current(key)
        if failures is None or len(failures) < self._max_failures:
            return None
        return max(1, math.ceil(failures[0] + self._window_seconds - self._clock()))

    def record_failure(self, key: LoginKey) -> None:
        failures = self._current(key)
        if failures is None:
            if len(self._failures) >= _MAX_TRACKED_KEYS:
                # Bounded memory: forget the oldest tracked key before adding a new one.
                del self._failures[next(iter(self._failures))]
            failures = self._failures[key] = deque()
        failures.append(self._clock())

    def reset(self, key: LoginKey) -> None:
        self._failures.pop(key, None)

    def _current(self, key: LoginKey) -> deque[float] | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        horizon = self._clock() - self._window_seconds
        while failures and failures[0] <= horizon:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures


login_throttle = LoginThrottle()
