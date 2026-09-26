"""Shared PostgreSQL integration fixtures: one Alembic upgrade per run, engine per test loop."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.db.session import engine


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
