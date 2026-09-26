"""Shared PostgreSQL integration fixtures: one Alembic upgrade per run, engine per test loop."""

import logging
import secrets
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from app.api.auth.endpoints import get_directory_login, get_login_rate_limiter
from app.core.config import Settings, get_settings
from app.core.login_throttle import LoginRateLimiter
from app.db.session import async_session_factory, engine
from app.domain.directory import (
    DirectoryAccount,
    DirectoryCredentialsRejected,
)
from app.main import app
from app.scripts.create_super_admin import ensure_super_admin


@pytest.fixture(scope="session")
def migrated_database(postgres_database_url: str) -> Iterator[None]:
    del postgres_database_url  # the Alembic environment reads the same typed setting
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    yield


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncIterator[None]:
    # Each test runs in its own event loop; pooled asyncpg connections must not outlive it.
    yield
    await engine.dispose()


UPN_SUFFIX = "corp.example.test"
CLIENT_ADDRESS = "10.0.0.5"


@dataclass
class DirectoryEntry:
    password: str
    account: DirectoryAccount


@dataclass
class FakeDirectory:
    """Signature-constrained DirectoryLoginPort: exact calls recorded, typed results replayed."""

    entries: dict[str, DirectoryEntry] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    failure: Exception | None = None

    def add(
        self,
        account_name: str,
        *,
        password: str | None = None,
        enabled: bool = True,
        is_human: bool = True,
        mail: str | None = None,
        display_name: str | None = None,
        object_guid: UUID | None = None,
    ) -> tuple[str, str, DirectoryAccount]:
        upn = f"{account_name}@{UPN_SUFFIX}"
        secret = password or secrets.token_urlsafe(18)
        account = DirectoryAccount(
            object_guid=object_guid or uuid4(),
            user_principal_name=upn,
            display_name=display_name or account_name.title(),
            mail=mail if mail is not None else f"{account_name}@{UPN_SUFFIX}",
            enabled=enabled,
            is_human=is_human,
        )
        self.entries[upn] = DirectoryEntry(secret, account)
        return upn, secret, account

    async def authenticate(self, user_principal_name: str, password: str) -> DirectoryAccount:
        self.calls.append((user_principal_name, password))
        if self.failure is not None:
            raise self.failure
        entry = self.entries.get(user_principal_name)
        if entry is None or entry.password != password:
            raise DirectoryCredentialsRejected()
        return entry.account


@dataclass
class AuthHarness:
    client: AsyncClient
    directory: FakeDirectory
    limiter: LoginRateLimiter
    settings: Settings
    use_settings: Callable[..., Settings]

    @property
    def prefix(self) -> str:
        return self.settings.api_prefix

    def origin_headers(self) -> dict[str, str]:
        return {"origin": self.settings.public_origin}

    def auth_headers(self, login_body: dict[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {login_body['access_token']}",
            self.settings.tenant_header: login_body["user"]["tenant_id"],
        }

    async def login(self, username: str, password: str, **kwargs: Any) -> Any:
        return await self.client.post(
            f"{self.prefix}/auth/login",
            json={"username": username, "password": password},
            **kwargs,
        )


@pytest.fixture
async def auth(migrated_database: None) -> AsyncIterator[AuthHarness]:
    base = get_settings()
    state: dict[str, Settings] = {
        "settings": base.model_copy(
            update={
                "environment": "staging",
                "directory_enabled": True,
                "directory_upn_suffix": UPN_SUFFIX,
            }
        )
    }
    directory = FakeDirectory()
    limiter = LoginRateLimiter()

    def use_settings(**updates: Any) -> Settings:
        state["settings"] = state["settings"].model_copy(update=updates)
        return state["settings"]

    def directory_login() -> FakeDirectory | None:
        return directory if state["settings"].directory_enabled else None

    app.dependency_overrides[get_settings] = lambda: state["settings"]
    app.dependency_overrides[get_directory_login] = directory_login
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    transport = ASGITransport(app=app, client=(CLIENT_ADDRESS, 50000))
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield AuthHarness(client, directory, limiter, state["settings"], use_settings)
    finally:
        for dependency in (get_settings, get_directory_login, get_login_rate_limiter):
            app.dependency_overrides.pop(dependency, None)


@dataclass(frozen=True)
class SuperAdmin:
    username: str
    password: str
    public_id: UUID


@pytest.fixture
async def super_admin(migrated_database: None) -> SuperAdmin:
    suffix = uuid4().hex[:10]
    username = f"admin-{suffix}"
    password = secrets.token_urlsafe(24)
    async with async_session_factory() as session:
        result = await ensure_super_admin(
            session,
            email=f"{username}@example.test",
            username=username,
            password=password,
        )
    return SuperAdmin(username, password, result.user_public_id)


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def events(self, name: str) -> list[dict[str, Any]]:
        return [
            dict(getattr(record, "structured_fields", {}))
            for record in self.records
            if record.getMessage() == name
        ]


@pytest.fixture
def recorded_logs() -> Iterator[RecordingHandler]:
    handler = RecordingHandler()
    loggers = [logging.getLogger(name) for name in ("app.auth", "app.admin", "app.http")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)
