"""The per-user limit on review starts (sql-review 003 Requirement 18)."""

import pytest

from app.core.review_throttle import ReviewRateLimiter

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_limit_counts_per_key_in_a_sliding_window() -> None:
    clock = Clock()
    limiter = ReviewRateLimiter(clock=clock)
    for _ in range(3):
        assert limiter.acquire("kişi", max_requests=3, window_seconds=60) is None
    assert limiter.acquire("kişi", max_requests=3, window_seconds=60) == 60
    assert limiter.acquire("başka kişi", max_requests=3, window_seconds=60) is None
    clock.now += 45
    assert limiter.acquire("kişi", max_requests=3, window_seconds=60) == 15
    clock.now += 15
    assert limiter.acquire("kişi", max_requests=3, window_seconds=60) is None
