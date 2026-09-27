"""Start-up creation of the local super admin without a database (application-foundation 001).

Requirement 14: a missing start-up password or name is a no-op that never reaches the database;
an unreachable database is retried with a growing, capped delay; a rejected identity is final and
never retried; the operator command never takes the deployment's start-up password.
"""

import asyncio
import io
import logging
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

import app.main as main_module
from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter
from app.scripts import create_super_admin
from app.services.super_admin_service import (
    BootstrapOutcome,
    bootstrap_super_admin,
    run_super_admin_bootstrap,
)

pytestmark = pytest.mark.unit

# Test-process value only; never a usable password of any environment.
START_UP_PASSWORD = "unit-start-up-password-not-real-9f3"


class _Recorder(logging.Handler):
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

    def rendered(self) -> str:
        formatter = JsonFormatter()
        return "\n".join(formatter.format(record) for record in self.records)


@pytest.fixture
def auth_events() -> Iterator[_Recorder]:
    recorder = _Recorder()
    logger = logging.getLogger("app.auth")
    level = logger.level
    logger.addHandler(recorder)
    logger.setLevel(logging.INFO)
    try:
        yield recorder
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(level)


def _settings(**updates: Any) -> Settings:
    return get_settings().model_copy(
        update={
            "environment": "staging",
            "bootstrap_super_admin_username": "admin",
            "bootstrap_super_admin_password": SecretStr(START_UP_PASSWORD),
            **updates,
        }
    )


def _never_opened() -> AsyncSession:
    raise AssertionError("the database must not be reached")


@pytest.mark.parametrize(
    "updates",
    [
        {"bootstrap_super_admin_password": None},
        {"bootstrap_super_admin_username": "  "},
    ],
)
async def test_missing_settings_do_nothing_and_never_reach_the_database(
    updates: dict[str, Any], auth_events: _Recorder
) -> None:
    outcome = await bootstrap_super_admin(_never_opened, _settings(**updates))

    assert outcome is BootstrapOutcome.NOT_CONFIGURED
    assert auth_events.events("auth.super_admin.bootstrap") == [
        {"event": "auth.super_admin.bootstrap", "outcome": "not_configured"}
    ]


def test_an_empty_start_up_password_counts_as_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD", "")
    assert Settings().bootstrap_super_admin_password is None  # type: ignore[call-arg]


async def test_an_unreachable_database_is_retried_with_a_growing_capped_delay(
    auth_events: _Recorder,
) -> None:
    opened = 0
    delays: list[float] = []

    def unreachable() -> AsyncSession:
        nonlocal opened
        opened += 1
        raise ConnectionRefusedError("database not accepting connections yet")

    async def recorded_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) == 7:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await run_super_admin_bootstrap(unreachable, _settings(), sleep=recorded_sleep)

    assert delays == [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
    assert opened == 7
    retries = auth_events.events("auth.super_admin.bootstrap_retry")
    assert [event["attempt"] for event in retries] == [1, 2, 3, 4, 5, 6, 7]
    assert {event["error_type"] for event in retries} == {"ConnectionRefusedError"}
    assert [event["retry_in_seconds"] for event in retries] == [2, 4, 8, 16, 32, 60, 60]
    assert START_UP_PASSWORD not in auth_events.rendered()
    assert "not accepting" not in auth_events.rendered()


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"bootstrap_super_admin_email": "not-an-address"}, "invalid_email"),
        (
            {
                "bootstrap_super_admin_username": "admin@corp.example.test",
                "directory_upn_suffix": "corp.example.test",
            },
            "invalid_username",
        ),
    ],
)
async def test_a_rejected_identity_is_final_and_never_retried(
    updates: dict[str, Any], reason: str, auth_events: _Recorder
) -> None:
    delays: list[float] = []

    async def recorded_sleep(delay: float) -> None:
        delays.append(delay)

    # An unbound session: the identity is refused before any statement is sent.
    outcome = await run_super_admin_bootstrap(
        AsyncSession, _settings(**updates), sleep=recorded_sleep
    )

    assert outcome is BootstrapOutcome.REJECTED
    assert delays == []
    assert auth_events.events("auth.super_admin.bootstrap") == [
        {"event": "auth.super_admin.bootstrap", "outcome": "rejected", "reason": reason}
    ]
    assert START_UP_PASSWORD not in auth_events.rendered()


def test_the_operator_command_never_takes_the_start_up_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD", START_UP_PASSWORD)
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(sys, "stdin", io.StringIO("operator-typed-password-42\n"))
        assert create_super_admin._password_from_operator(True) == "operator-typed-password-42"
        monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
        with pytest.raises(ValueError, match="empty"):
            create_super_admin._password_from_operator(True)
    finally:
        get_settings.cache_clear()


async def test_the_start_runs_the_bootstrap_in_the_background_and_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()
    received: list[Settings] = []

    async def blocked_bootstrap(session_factory: object, settings: Settings) -> BootstrapOutcome:
        received.append(settings)
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("unreachable")  # pragma: no cover

    monkeypatch.setattr(main_module, "run_super_admin_bootstrap", blocked_bootstrap)
    settings = _settings(environment="development")
    application = main_module.create_application(settings)
    async with application.router.lifespan_context(application):
        # The application serves while the bootstrap still waits for the database.
        await asyncio.wait_for(started.wait(), timeout=5)
        assert not cancelled.is_set()

    assert cancelled.is_set()
    assert received == [settings]


def test_bootstrap_log_fields_are_bounded_values() -> None:
    # The event vocabulary the PRD names: outcomes are a fixed set of plain strings.
    assert {outcome.value for outcome in BootstrapOutcome} == {
        "created",
        "exists",
        "rejected",
        "not_configured",
    }
