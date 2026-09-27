"""In-process limit on review run starts per signed-in user (sql-review 003 Requirement 18).

Object and script reviews share one counter per tenant and user: at most ``max_requests`` starts
in a sliding window of ``window_seconds``. Both values come from the typed settings. Each backend
process counts on its own.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Hashable

_MAX_TRACKED_KEYS = 10_000


class ReviewRateLimiter:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._starts: dict[Hashable, deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: Hashable, *, max_requests: int, window_seconds: int) -> int | None:
        """Count one start; the Retry-After seconds instead when the limit is used up."""

        with self._lock:
            now = self._clock()
            starts = self._starts.get(key)
            if starts is None:
                if len(self._starts) >= _MAX_TRACKED_KEYS:
                    del self._starts[next(iter(self._starts))]
                starts = self._starts[key] = deque()
            horizon = now - window_seconds
            while starts and starts[0] <= horizon:
                starts.popleft()
            if len(starts) >= max_requests:
                return max(1, math.ceil(starts[0] + window_seconds - now))
            starts.append(now)
            return None
