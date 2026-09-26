"""Local SQL Server connection settings: in-process changes, password handling and the test.

sql-review/PRDs/002-sql-server-connection Requirement 3, 4, 5 and 8 (Acceptance 1).
"""

import hashlib
import logging
import os
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.domain.sql_server import (
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerErrorClass,
)
from app.schemas.sql_connection.contracts import SqlConnectionChange
from app.services.sql_connection_service import (
    SqlConnectionService,
    SqlConnectionStore,
    initial_sql_connection,
)

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
STORED_PASSWORD = f"kayitli-{uuid4().hex}"
STORED = SqlServerConnectionConfig(
    server="sql-dev.corp.example.test", port=1433, user="gelistirici", password=STORED_PASSWORD
)
CONTEXT = RequestContext(subject=uuid4())


class FakeProbe:
    def __init__(self, databases: Sequence[str] = (), error: SqlServerError | None = None) -> None:
        self.databases = list(databases)
        self.error = error
        self.calls: list[SqlServerConnectionConfig] = []

    async def probe(self, config: SqlServerConnectionConfig) -> list[str]:
        self.calls.append(config)
        if self.error is not None:
            raise self.error
        return self.databases


def _settings(environment: str = "development", **values: Any) -> Settings:
    return Settings(_env_file=None, environment=environment, **values)


def _service(
    probe: FakeProbe | None = None, environment: str = "development", **values: Any
) -> SqlConnectionService:
    return SqlConnectionService(
        settings=_settings(environment, **values),
        store=SqlConnectionStore(STORED),
        probe=probe or FakeProbe(),
    )


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    captured: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = Handler()
    logger = logging.getLogger("app.sql_server")
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield captured
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def _env_files_digest() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in BACKEND.glob(".env*")
        if path.is_file()
    }


def test_initial_values_come_from_the_typed_settings() -> None:
    config = initial_sql_connection(
        _settings(mssql_server=" sql ", mssql_user="u", mssql_password="p", mssql_port=14330)
    )
    assert (config.server, config.user, config.password, config.port) == ("sql", "u", "p", 14330)
    assert config.trust_server_certificate is False and config.encrypt is True


def test_local_view_shows_values_but_never_the_password() -> None:
    view = _service(mssql_allowed_databases="DWH_B, DWH_A").view().model_dump(exclude_none=True)
    assert view == {
        "environment": "local",
        "editable": True,
        "configured": True,
        "server": STORED.server,
        "port": 1433,
        "user": STORED.user,
        "encrypt": True,
        "trust_server_certificate": False,
        "password_set": True,
        "allowed_databases": ["DWH_A", "DWH_B"],
    }
    assert STORED_PASSWORD not in repr(view)


def test_nonprod_view_hides_server_and_user_and_refuses_changes() -> None:
    service = _service(environment="staging")
    assert service.view().model_dump(exclude_none=True) == {
        "environment": "nonprod",
        "editable": False,
        "configured": True,
    }
    with pytest.raises(ApplicationError) as raised:
        service.update(CONTEXT, SqlConnectionChange(port=1))
    assert raised.value.status_code == 404


def test_update_keeps_a_missing_password_and_removes_an_empty_one(
    records: list[logging.LogRecord],
) -> None:
    service = _service()
    before_files = _env_files_digest()
    before_environment = dict(os.environ)

    kept = service.update(CONTEXT, SqlConnectionChange(server="sql-2.corp.example.test", port=1500))
    assert kept.password_set is True
    assert service.store.current().password == STORED_PASSWORD
    assert service.store.current().server == "sql-2.corp.example.test"

    new_password = f"yeni-{uuid4().hex}"
    service.update(CONTEXT, SqlConnectionChange(password=new_password))
    assert service.store.current().password == new_password

    removed = service.update(CONTEXT, SqlConnectionChange(password=""))
    assert removed.password_set is False and removed.configured is False

    # Decision 3: the change lives in this process only.
    assert _env_files_digest() == before_files
    assert dict(os.environ) == before_environment
    events = [r.structured_fields for r in records if r.getMessage() == "sql_connection.updated"]  # type: ignore[attr-defined]
    assert [event["changed_fields"] for event in events] == ["port,server", "password", "password"]
    assert all(event["user_public_id"] == str(CONTEXT.subject) for event in events)
    rendered = repr([r.__dict__ for r in records])
    assert new_password not in rendered and STORED_PASSWORD not in rendered
    assert "sql-2.corp.example.test" not in rendered


@pytest.mark.parametrize(
    "change",
    [
        SqlConnectionChange(server="sql\nx"),
        SqlConnectionChange(user="u\x07"),
        SqlConnectionChange(server="a;b"),
    ],
)
def test_control_characters_and_separators_are_rejected(change: SqlConnectionChange) -> None:
    service = _service()
    with pytest.raises(ApplicationError) as raised:
        service.update(CONTEXT, change)
    assert (raised.value.status_code, raised.value.code) == (422, "sql_connection_invalid")
    assert service.store.current() == STORED


async def test_a_new_target_without_a_password_never_receives_the_stored_one() -> None:
    probe = FakeProbe(["DWH"])
    service = _service(probe)
    for change in (
        SqlConnectionChange(server="other.corp.example.test"),
        SqlConnectionChange(port=1434),
        SqlConnectionChange(user="baska"),
    ):
        result = await service.test(change)
        assert (result.ok, result.code, result.databases) == (False, "password_required", [])
    assert probe.calls == []


async def test_the_same_target_is_tested_with_the_stored_password_without_saving() -> None:
    probe = FakeProbe(["DWH_A", "DWH_B"])
    service = _service(probe)

    result = await service.test(SqlConnectionChange(encrypt=True))

    assert (result.ok, result.code, result.databases) == (True, None, ["DWH_A", "DWH_B"])
    assert probe.calls[0].password == STORED_PASSWORD
    assert service.store.current() == STORED


async def test_a_new_target_with_its_own_password_is_tested() -> None:
    probe = FakeProbe(["DWH"])
    service = _service(probe)
    result = await service.test(SqlConnectionChange(server="other.corp.example.test", password="x"))
    assert result.ok and probe.calls[0].server == "other.corp.example.test"
    assert service.store.current() == STORED


async def test_connection_failures_become_fixed_classes() -> None:
    probe = FakeProbe(error=SqlServerError(SqlServerErrorClass.TLS_FAILED, "08001"))
    result = await _service(probe).test(SqlConnectionChange())
    assert result.model_dump() == {
        "ok": False,
        "code": "sql_tls_failed",
        "message": "SQL Server ile güvenli bağlantı kurulamadı.",
        "databases": [],
    }


async def test_a_test_without_server_or_user_is_invalid() -> None:
    service = SqlConnectionService(
        settings=_settings(),
        store=SqlConnectionStore(SqlServerConnectionConfig()),
        probe=FakeProbe(),
    )
    with pytest.raises(ApplicationError) as raised:
        await service.test(SqlConnectionChange(password="x"))
    assert raised.value.code == "sql_connection_invalid"
