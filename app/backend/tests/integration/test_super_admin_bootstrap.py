"""Start-up creation of the local super admin on PostgreSQL (application-foundation 001).

Requirement 14 and Decision 13: the backend creates the configured super admin once, through the
same path as the operator command; an existing account is never changed, a weak password creates
nothing and never reaches a log, and backend replicas starting together create one account.
"""

import asyncio
import logging
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter
from app.db.session import async_session_factory
from app.domain.models.role import ROLE_REVIEWER
from app.domain.models.tenant import PLATFORM_TENANT_CODE
from app.domain.models.user import AccountType, User
from app.infrastructure.repositories.user_repository import UserRepository
from app.services.super_admin_service import (
    BootstrapOutcome,
    bootstrap_super_admin,
    ensure_super_admin,
    run_super_admin_bootstrap,
)
from tests.integration.conftest import AuthHarness, RecordingHandler

pytestmark = pytest.mark.integration


class _Rendered(logging.Handler):
    """Every app.auth record rendered exactly as the deployment writes it."""

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def rendered_auth_log() -> Iterator[_Rendered]:
    handler = _Rendered()
    logger = logging.getLogger("app.auth")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def _identity() -> tuple[str, str]:
    name = f"admin-{uuid4().hex[:10]}"
    return name, f"{name}@example.invalid"


def _settings(username: str, email: str, password: str | None) -> Settings:
    return get_settings().model_copy(
        update={
            "environment": "staging",
            "bootstrap_super_admin_username": username,
            "bootstrap_super_admin_email": email,
            "bootstrap_super_admin_password": SecretStr(password) if password else None,
        }
    )


async def _account(username: str) -> User | None:
    async with async_session_factory() as session:
        return (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()


async def _changes(username: str) -> list[tuple[Any, ...]]:
    async with async_session_factory() as session:
        rows = await session.execute(
            text(
                "SELECT c.changed_field, c.old_value, c.new_value, "
                "c.actor_user_id = c.target_user_id "
                "FROM app_user_change c JOIN app_user u ON u.user_id = c.target_user_id "
                "WHERE u.username = :name ORDER BY c.app_user_change_id"
            ),
            {"name": username},
        )
        return [tuple(row) for row in rows.all()]


async def _roles(username: str) -> tuple[str, ...]:
    async with async_session_factory() as session:
        users = UserRepository(session)
        user = (await session.execute(select(User).where(User.username == username))).scalar_one()
        return await users.role_codes(user)


async def test_the_start_creates_the_super_admin_once_and_it_logs_in(
    auth: AuthHarness, recorded_logs: RecordingHandler, rendered_auth_log: _Rendered
) -> None:
    username, email = _identity()
    password = secrets.token_urlsafe(24)
    settings = _settings(username, email, password)

    first = await bootstrap_super_admin(async_session_factory, settings)
    second = await bootstrap_super_admin(async_session_factory, settings)

    assert (first, second) == (BootstrapOutcome.CREATED, BootstrapOutcome.EXISTS)
    account = await _account(username)
    assert account is not None
    assert (account.account_type, account.is_active, account.is_deleted) == (
        AccountType.LOCAL.value,
        True,
        False,
    )
    assert account.password_hash is not None and password not in account.password_hash
    assert await _roles(username) == ("super_admin",)
    # One history row: the account received super_admin from nobody but itself.
    assert await _changes(username) == [("role", None, "super_admin", True)]

    login = await auth.login(username, password)
    assert login.status_code == 200, login.text
    assert login.json()["user"]["is_super_admin"] is True
    assert login.json()["user"]["account_type"] == "local"

    events = recorded_logs.events("auth.super_admin.bootstrap")
    assert [event["outcome"] for event in events] == ["created", "exists"]
    assert {event["user_public_id"] for event in events} == {account.public_id}
    assert all(event["super_admin"] is True for event in events)
    assert all(password not in line for line in rendered_auth_log.lines)
    assert all(account.password_hash not in line for line in rendered_auth_log.lines)


async def test_a_later_start_never_resets_the_password_the_admin_chose(
    auth: AuthHarness,
) -> None:
    username, email = _identity()
    start_up_password = secrets.token_urlsafe(24)
    chosen_password = secrets.token_urlsafe(24)
    settings = _settings(username, email, start_up_password)

    assert await bootstrap_super_admin(async_session_factory, settings) is BootstrapOutcome.CREATED
    # The administrator later changes the password with the operator command's reset path.
    async with async_session_factory() as session:
        reset = await ensure_super_admin(
            session, email=email, username=username, password=chosen_password
        )
    assert reset.created is False
    before = await _account(username)
    assert before is not None

    assert await bootstrap_super_admin(async_session_factory, settings) is BootstrapOutcome.EXISTS

    after = await _account(username)
    assert after is not None
    assert after.password_hash == before.password_hash
    assert after.updated_at == before.updated_at
    assert (await auth.login(username, chosen_password)).status_code == 200
    assert (await auth.login(username, start_up_password)).status_code == 401
    assert await _changes(username) == [("role", None, "super_admin", True)]


async def test_an_account_holding_the_name_keeps_its_role_and_status(
    recorded_logs: RecordingHandler, migrated_database: None
) -> None:
    username, email = _identity()
    other_password = secrets.token_urlsafe(24)
    async with async_session_factory() as session:
        users = UserRepository(session)
        tenant = await users.get_tenant_by_code(PLATFORM_TENANT_CODE)
        role = await users.get_role(ROLE_REVIEWER)
        assert tenant is not None and role is not None
        existing = await users.add_user(
            User(
                home_tenant_id=tenant.tenant_id,
                username=username,
                email=email,
                display_name="Existing",
                account_type=AccountType.LOCAL.value,
                password_hash="not-a-real-hash-for-this-test",
                is_active=False,
            )
        )
        await users.set_application_role(
            existing, role, actor_user_id=existing.user_id, now=datetime.now(UTC)
        )
        await session.commit()

    outcome = await bootstrap_super_admin(
        async_session_factory, _settings(username, f"other-{email}", other_password)
    )

    assert outcome is BootstrapOutcome.EXISTS
    account = await _account(username)
    assert account is not None
    assert (account.is_active, account.email, account.password_hash) == (
        False,
        email,
        "not-a-real-hash-for-this-test",
    )
    assert await _roles(username) == (ROLE_REVIEWER,)
    assert await _changes(username) == []
    (event,) = recorded_logs.events("auth.super_admin.bootstrap")
    assert (event["outcome"], event["super_admin"]) == ("exists", False)


@pytest.mark.parametrize(
    "weak",
    [
        "short-pass-11",  # below the 15-character minimum
        "passwordpassword",  # on the common-password blocklist
        "{name}-with-own-name",  # contains the account name
    ],
)
async def test_a_weak_password_creates_nothing_and_never_reaches_a_log(
    weak: str,
    recorded_logs: RecordingHandler,
    rendered_auth_log: _Rendered,
    migrated_database: None,
) -> None:
    username, email = _identity()
    password = weak.format(name=username)
    delays: list[float] = []

    async def recorded_sleep(delay: float) -> None:
        delays.append(delay)

    outcome = await run_super_admin_bootstrap(
        async_session_factory, _settings(username, email, password), sleep=recorded_sleep
    )

    assert outcome is BootstrapOutcome.REJECTED
    assert delays == []
    assert await _account(username) is None
    assert recorded_logs.events("auth.super_admin.bootstrap") == [
        {"event": "auth.super_admin.bootstrap", "outcome": "rejected", "reason": "password_policy"}
    ]
    assert all(password not in line for line in rendered_auth_log.lines)


async def test_an_email_owned_by_another_account_creates_nothing(
    recorded_logs: RecordingHandler, migrated_database: None
) -> None:
    owner, email = _identity()
    async with async_session_factory() as session:
        await ensure_super_admin(
            session, email=email, username=owner, password=secrets.token_urlsafe(24)
        )
    username, _ = _identity()

    outcome = await bootstrap_super_admin(
        async_session_factory, _settings(username, email, secrets.token_urlsafe(24))
    )

    assert outcome is BootstrapOutcome.REJECTED
    assert await _account(username) is None
    (event,) = recorded_logs.events("auth.super_admin.bootstrap")
    assert (event["outcome"], event["reason"]) == ("rejected", "identity_conflict")


async def test_replicas_starting_together_create_one_account(migrated_database: None) -> None:
    username, email = _identity()
    settings = _settings(username, email, secrets.token_urlsafe(24))

    outcomes = await asyncio.gather(
        *(bootstrap_super_admin(async_session_factory, settings) for _ in range(4))
    )

    assert sorted(outcomes) == sorted([BootstrapOutcome.CREATED] + [BootstrapOutcome.EXISTS] * 3)
    async with async_session_factory() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(User).where(User.username == username)
            )
        ).scalar_one()
    assert count == 1
    assert await _changes(username) == [("role", None, "super_admin", True)]


async def test_the_start_retries_until_the_database_answers(
    recorded_logs: RecordingHandler, migrated_database: None
) -> None:
    username, email = _identity()
    password = secrets.token_urlsafe(24)
    opened = 0
    delays: list[float] = []

    def reachable_on_third_attempt() -> AsyncSession:
        nonlocal opened
        opened += 1
        if opened < 3:
            raise ConnectionRefusedError("database not accepting connections yet")
        return async_session_factory()

    async def recorded_sleep(delay: float) -> None:
        delays.append(delay)

    outcome = await run_super_admin_bootstrap(
        reachable_on_third_attempt, _settings(username, email, password), sleep=recorded_sleep
    )

    assert outcome is BootstrapOutcome.CREATED
    assert delays == [2.0, 4.0]
    assert await _account(username) is not None
    retries = recorded_logs.events("auth.super_admin.bootstrap_retry")
    assert [(event["attempt"], event["error_type"]) for event in retries] == [
        (1, "ConnectionRefusedError"),
        (2, "ConnectionRefusedError"),
    ]
