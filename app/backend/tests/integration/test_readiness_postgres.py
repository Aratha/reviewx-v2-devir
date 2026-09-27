"""Readiness against the disposable PostgreSQL database: real login and real schema version."""

import logging
import secrets
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.readiness import DatabaseReadiness, PackagedSchema, packaged_schema

pytestmark = pytest.mark.integration

FUTURE_HEAD = "kt-readiness-future-head"


@pytest.fixture
async def runtime_engine(
    postgres_database_url: str, migrated_database: None
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


def _not_ready_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, str]]:
    return [
        record.structured_fields  # type: ignore[attr-defined]
        for record in caplog.records
        if record.name == "app.readiness" and record.getMessage() == "readiness.not_ready"
    ]


async def test_runtime_login_on_the_image_head_is_ready(runtime_engine: AsyncEngine) -> None:
    assert await DatabaseReadiness(runtime_engine).is_ready() is True


async def test_role_the_migration_has_not_created_yet_is_not_ready(
    postgres_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    # A first installation: the runtime role does not exist until the migration Job creates it.
    absent_role = make_url(postgres_database_url).set(
        username="kt_readiness_absent_role", password=secrets.token_urlsafe(24)
    )
    engine = create_async_engine(absent_role, poolclass=NullPool)
    try:
        assert await DatabaseReadiness(engine).is_ready() is False
    finally:
        await engine.dispose()

    assert _not_ready_events(caplog) == [
        {
            "event": "readiness.not_ready",
            "reason": "database_unavailable",
            "error_type": "InvalidPasswordError",
        }
    ]
    assert all(record.exc_info is None for record in caplog.records)


async def test_schema_behind_the_image_head_is_not_ready(
    runtime_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.readiness")
    shipped = packaged_schema()
    # An image one migration ahead of the database: its head is new, the recorded one is known.
    newer_image = PackagedSchema(
        heads=frozenset({FUTURE_HEAD}), revisions=shipped.revisions | {FUTURE_HEAD}
    )

    assert await DatabaseReadiness(runtime_engine, packaged=lambda: newer_image).is_ready() is False
    assert _not_ready_events(caplog) == [
        {"event": "readiness.not_ready", "reason": "schema_behind"}
    ]
