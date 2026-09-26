"""Failed-login rate limit contract tests."""

import secrets
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.auth.endpoints import get_auth_service
from app.core.config import get_settings
from app.core.login_throttle import MAX_FAILED_ATTEMPTS, LoginThrottle, login_throttle
from app.main import app

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


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


def test_other_client_address_and_success_are_not_locked() -> None:
    throttle = LoginThrottle(max_failures=1, window_seconds=60, clock=_Clock())
    throttle.record_failure(("admin", "10.0.0.1"))

    assert throttle.retry_after(("admin", "10.0.0.1")) is not None
    assert throttle.retry_after(("admin", "10.0.0.2")) is None
    throttle.reset(("admin", "10.0.0.1"))
    assert throttle.retry_after(("admin", "10.0.0.1")) is None


class _RejectingService:
    async def authenticate(self, username: str, password: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


@pytest.fixture
def rejecting_login() -> Iterator[None]:
    app.dependency_overrides[get_auth_service] = _RejectingService
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_auth_service, None)
        login_throttle.reset(("throttled-user", "127.0.0.1"))


@pytest.fixture
async def client(rejecting_login: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_login_endpoint_answers_429_after_repeated_failures(client: AsyncClient) -> None:
    url = f"{get_settings().api_prefix}/auth/login"
    body = {"username": "Throttled-User", "password": secrets.token_urlsafe(24)}

    for _ in range(MAX_FAILED_ATTEMPTS):
        assert (await client.post(url, json=body)).status_code == 401
    limited = await client.post(url, json=body)

    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
