"""Failed-login limits and trusted client address (application-foundation 001 Requirement 9)."""

from ipaddress import ip_network

import pytest

from app.core.client_address import resolve_client_address
from app.core.login_throttle import (
    ADDRESS_MAX_FAILURES,
    NAME_ADDRESS_MAX_FAILURES,
    WINDOW_SECONDS,
    LoginRateLimiter,
    LoginThrottle,
)

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limits_follow_the_accepted_values() -> None:
    assert NAME_ADDRESS_MAX_FAILURES == 5
    assert ADDRESS_MAX_FAILURES == 30
    assert WINDOW_SECONDS == 15 * 60


def test_attempts_are_limited_inside_the_window_and_released_after_it() -> None:
    clock = _Clock()
    throttle = LoginThrottle(max_failures=3, window_seconds=60, clock=clock)
    key = ("admin", "10.0.0.1")

    for _ in range(3):
        assert throttle.retry_after(key) is None
        throttle.record_failure(key)

    assert throttle.retry_after(key) == 60
    clock.now += 59.5
    assert throttle.retry_after(key) == 1
    clock.now += 0.5
    assert throttle.retry_after(key) is None


def test_fifth_failure_of_one_name_and_address_blocks_only_that_pair() -> None:
    limiter = LoginRateLimiter(clock=_Clock())
    for _ in range(NAME_ADDRESS_MAX_FAILURES):
        assert limiter.blocked("ad.soyad", "10.0.0.1") is None
        limiter.record_failure("ad.soyad", "10.0.0.1")

    blocked = limiter.blocked("ad.soyad", "10.0.0.1")
    assert blocked is not None and blocked[0] == "user" and blocked[1] > 0
    # The same person from another address and another person from this address still pass,
    # so an attacker cannot lock a real user out.
    assert limiter.blocked("ad.soyad", "10.0.0.2") is None
    assert limiter.blocked("baska.kisi", "10.0.0.1") is None


def test_thirtieth_failure_from_one_address_blocks_the_address() -> None:
    limiter = LoginRateLimiter(clock=_Clock())
    for index in range(ADDRESS_MAX_FAILURES):
        limiter.record_failure(f"user-{index}", "10.0.0.9")

    blocked = limiter.blocked("someone-new", "10.0.0.9")
    assert blocked is not None and blocked[0] == "address"
    assert limiter.blocked("someone-new", "10.0.0.10") is None


def test_success_resets_only_the_user_counter() -> None:
    limiter = LoginRateLimiter(clock=_Clock())
    for _ in range(NAME_ADDRESS_MAX_FAILURES):
        limiter.record_failure("ad.soyad", "10.0.0.1")
    limiter.record_success("ad.soyad", "10.0.0.1")
    assert limiter.blocked("ad.soyad", "10.0.0.1") is None
    for _ in range(ADDRESS_MAX_FAILURES - NAME_ADDRESS_MAX_FAILURES):
        limiter.record_failure("other", "10.0.0.1")
    assert limiter.blocked("ad.soyad", "10.0.0.1") == ("address", WINDOW_SECONDS)


TRUSTED = (ip_network("10.42.0.0/16"),)


@pytest.mark.parametrize(
    ("peer", "forwarded_for", "expected"),
    (
        # A request that did not come through the ingress cannot choose its own address.
        ("203.0.113.7", "198.51.100.1", "203.0.113.7"),
        ("10.42.3.4", "198.51.100.1", "198.51.100.1"),
        ("10.42.3.4", "198.51.100.1, 10.42.9.9", "198.51.100.1"),
        # Only the hops the trusted proxy appended count; a forged left-most value is skipped.
        ("10.42.3.4", "1.2.3.4, 198.51.100.1", "198.51.100.1"),
        ("10.42.3.4", "not-an-address", "10.42.3.4"),
        ("10.42.3.4", None, "10.42.3.4"),
        (None, "198.51.100.1", ""),
    ),
)
def test_forwarded_for_is_honoured_only_from_the_trusted_ingress(
    peer: str | None, forwarded_for: str | None, expected: str
) -> None:
    assert resolve_client_address(peer, forwarded_for, TRUSTED) == expected


def test_without_trusted_networks_the_header_is_ignored() -> None:
    assert resolve_client_address("10.42.3.4", "198.51.100.1", ()) == "10.42.3.4"
