"""Schema-aware readiness: runtime login, migration head, positive cache and bounded logging."""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from asyncpg.exceptions import InvalidPasswordError
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import health as health_module
from app.core.config import get_settings
from app.core.logging import JsonFormatter
from app.db.readiness import (
    NOT_READY_LOG_INTERVAL_SECONDS,
    DatabaseReadiness,
    PackagedSchema,
    packaged_schema,
    schema_position,
)
from app.main import app

pytestmark = pytest.mark.unit

PREVIOUS = "202601010001"
HEAD = "202601010002"
PACKAGED = PackagedSchema(heads=frozenset({HEAD}), revisions=frozenset({PREVIOUS, HEAD}))
RUNTIME_LOGIN_ERROR = 'password authentication failed for user "app_runtime"'


class _Result:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def scalars(self) -> Iterator[str]:
        return iter(self._rows)


class _Database:
    """Stands in for the engine: answers from ``recorded`` or fails the connection like asyncpg."""

    def __init__(self, recorded: set[str] | None = None) -> None:
        self.recorded = recorded
        self.error: Exception | None = None
        self.statements: list[str] = []

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[_Database]:
        if self.error is not None:
            raise self.error
        yield self

    async def scalar(self, statement: Any) -> bool:
        self.statements.append(str(statement))
        return self.recorded is not None

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(str(statement))
        return _Result(sorted(self.recorded or ()))


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _readiness(database: _Database, clock: _Clock | None = None) -> DatabaseReadiness:
    return DatabaseReadiness(
        cast(AsyncEngine, database), packaged=lambda: PACKAGED, clock=clock or _Clock()
    )


def _not_ready_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, str]]:
    return [
        record.structured_fields  # type: ignore[attr-defined]
        for record in caplog.records
        if record.name == "app.readiness" and record.getMessage() == "readiness.not_ready"
    ]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def use_readiness(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    def install(readiness: DatabaseReadiness) -> None:
        monkeypatch.setattr(health_module, "database_readiness", readiness)

    yield install


async def test_schema_at_the_image_head_is_ready(client: AsyncClient, use_readiness: Any) -> None:
    use_readiness(_readiness(_Database({HEAD})))

    response = await client.get(f"{get_settings().api_prefix}/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.parametrize("recorded", [None, set(), {PREVIOUS}], ids=["no-table", "empty", "old"])
async def test_schema_behind_the_image_head_is_not_ready(
    client: AsyncClient,
    use_readiness: Any,
    caplog: pytest.LogCaptureFixture,
    recorded: set[str] | None,
) -> None:
    caplog.set_level(logging.INFO, logger="app.readiness")
    use_readiness(_readiness(_Database(recorded)))

    response = await client.get(f"{get_settings().api_prefix}/readiness")

    assert response.status_code == 503
    assert response.content == b'{"status":"not-ready"}'
    assert _not_ready_events(caplog) == [
        {"event": "readiness.not_ready", "reason": "schema_behind"}
    ]


async def test_rejected_runtime_login_is_not_ready_without_a_traceback(
    client: AsyncClient,
    use_readiness: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    database = _Database({HEAD})
    # SQLAlchemy does not wrap asyncpg's login failure; it reaches the probe unchanged.
    database.error = InvalidPasswordError(RUNTIME_LOGIN_ERROR)
    use_readiness(_readiness(database))

    response = await client.get(f"{get_settings().api_prefix}/readiness")

    assert response.status_code == 503
    assert response.content == b'{"status":"not-ready"}'
    assert _not_ready_events(caplog) == [
        {
            "event": "readiness.not_ready",
            "reason": "database_unavailable",
            "error_type": "InvalidPasswordError",
        }
    ]
    assert all(record.exc_info is None for record in caplog.records)
    assert all(record.levelno < logging.ERROR for record in caplog.records)
    rendered = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "app_runtime" not in rendered
    assert "password authentication" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.parametrize(
    ("error", "error_type"),
    [
        (ConnectionRefusedError("connection refused"), "ConnectionRefusedError"),
        (OSError("name resolution failed"), "OSError"),
    ],
)
async def test_unreachable_database_is_not_ready(
    caplog: pytest.LogCaptureFixture, error: Exception, error_type: str
) -> None:
    caplog.set_level(logging.INFO, logger="app.readiness")
    database = _Database({HEAD})
    database.error = error

    assert await _readiness(database).is_ready() is False
    assert _not_ready_events(caplog)[0]["error_type"] == error_type


async def test_wrapped_driver_error_is_reported_by_its_driver_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.readiness")
    wrapped = OperationalError("SELECT 1", {}, Exception("driver"))
    wrapped.__cause__ = InvalidPasswordError(RUNTIME_LOGIN_ERROR)
    database = _Database({HEAD})
    database.error = wrapped

    assert await _readiness(database).is_ready() is False
    assert _not_ready_events(caplog)[0]["error_type"] == "InvalidPasswordError"


async def test_confirmed_schema_is_cached_while_the_connection_is_still_checked() -> None:
    database = _Database({HEAD})
    readiness = _readiness(database)

    assert await readiness.is_ready() is True
    assert any("alembic_version" in statement for statement in database.statements)

    database.statements.clear()
    assert await readiness.is_ready() is True
    assert database.statements == ["SELECT 1"]

    database.error = ConnectionRefusedError("connection refused")
    assert await readiness.is_ready() is False

    database.error = None
    database.statements.clear()
    assert await readiness.is_ready() is True
    assert database.statements == ["SELECT 1"]


async def test_schema_a_later_release_migrated_stays_ready() -> None:
    # Migrations are expand-only and a rollback never downgrades the schema; the previous image
    # must keep serving on the newer schema.
    assert await _readiness(_Database({"202601010003"})).is_ready() is True


async def test_not_ready_events_are_rate_limited(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.readiness")
    clock = _Clock()
    database = _Database({PREVIOUS})
    readiness = _readiness(database, clock)

    for _ in range(3):
        assert await readiness.is_ready() is False
    assert len(_not_ready_events(caplog)) == 1

    database.error = InvalidPasswordError(RUNTIME_LOGIN_ERROR)
    assert await readiness.is_ready() is False
    assert len(_not_ready_events(caplog)) == 2

    database.error = None
    clock.now += NOT_READY_LOG_INTERVAL_SECONDS - 1
    assert await readiness.is_ready() is False
    assert len(_not_ready_events(caplog)) == 2

    clock.now += 1
    assert await readiness.is_ready() is False
    assert len(_not_ready_events(caplog)) == 3


async def test_liveness_does_not_depend_on_the_database(
    client: AsyncClient, use_readiness: Any
) -> None:
    database = _Database()
    database.error = InvalidPasswordError(RUNTIME_LOGIN_ERROR)
    use_readiness(_readiness(database))
    prefix = get_settings().api_prefix

    assert (await client.get(f"{prefix}/readiness")).status_code == 503
    response = await client.get(f"{prefix}/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_packaged_schema_reads_the_shipped_migrations_once() -> None:
    packaged = packaged_schema()

    assert packaged.heads
    assert packaged.heads <= packaged.revisions
    assert packaged_schema() is packaged
    assert schema_position(packaged.heads, packaged) == "current"
