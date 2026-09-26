"""In-process limits on failed login attempts (application-foundation 001 Requirement 9).

Two limits apply: five failures per normalized login name and client address, and thirty per
client address, both in a 15-minute window. No permanent account lock exists, so a stranger
cannot lock a real user out. Each process keeps its own counters; several backend replicas each
count separately (a risk recorded in the PRD).
"""

import math
import time
from collections import deque
from collections.abc import Callable, Hashable

NAME_ADDRESS_MAX_FAILURES = 5
ADDRESS_MAX_FAILURES = 30
WINDOW_SECONDS = 15 * 60
_MAX_TRACKED_KEYS = 10_000


class LoginThrottle:
    def __init__(
        self,
        *,
        max_failures: int,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[Hashable, deque[float]] = {}

    def retry_after(self, key: Hashable) -> int | None:
        """Return the seconds to wait when the key has used up its attempts, otherwise None."""

        failures = self._current(key)
        if failures is None or len(failures) < self._max_failures:
            return None
        return max(1, math.ceil(failures[0] + self._window_seconds - self._clock()))

    def record_failure(self, key: Hashable) -> None:
        failures = self._current(key)
        if failures is None:
            if len(self._failures) >= _MAX_TRACKED_KEYS:
                # Bounded memory: forget the oldest tracked key before adding a new one.
                del self._failures[next(iter(self._failures))]
            failures = self._failures[key] = deque()
        failures.append(self._clock())

    def reset(self, key: Hashable) -> None:
        self._failures.pop(key, None)

    def _current(self, key: Hashable) -> deque[float] | None:
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


class LoginRateLimiter:
    """The name+address and address limits applied together to one login attempt."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.by_name_and_address = LoginThrottle(
            max_failures=NAME_ADDRESS_MAX_FAILURES, clock=clock
        )
        self.by_address = LoginThrottle(max_failures=ADDRESS_MAX_FAILURES, clock=clock)

    def blocked(self, name: str, address: str) -> tuple[str, int] | None:
        """Return the exceeded limit kind ("user" or "address") and its Retry-After seconds."""

        user_wait = self.by_name_and_address.retry_after((name, address))
        if user_wait is not None:
            return "user", user_wait
        address_wait = self.by_address.retry_after(address)
        if address_wait is not None:
            return "address", address_wait
        return None

    def record_failure(self, name: str, address: str) -> None:
        self.by_name_and_address.record_failure((name, address))
        self.by_address.record_failure(address)

    def record_success(self, name: str, address: str) -> None:
        self.by_name_and_address.reset((name, address))

    def clear(self) -> None:
        """Forget every counter; used when a test needs a fresh process state."""

        self.by_name_and_address = LoginThrottle(
            max_failures=NAME_ADDRESS_MAX_FAILURES, clock=self._clock
        )
        self.by_address = LoginThrottle(max_failures=ADDRESS_MAX_FAILURES, clock=self._clock)


login_rate_limiter = LoginRateLimiter()
