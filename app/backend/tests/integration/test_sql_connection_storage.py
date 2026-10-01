"""The SQL Server connection saved in PostgreSQL (sql-review/PRDs/002-sql-server-connection).

Requirement 10 and 11, Decision 12 and 13 (Acceptance 1) against the migrated database: the
password is encrypted at rest, another replica uses a save without a restart, an unreadable or
unusable saved value leaves the connection not configured, the saving account is re-read, and the
migration goes down and up.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.core.secret_cipher import SecretCipher
from app.db.session import async_session_factory, engine
from app.domain.sql_server import (
    EffectiveSqlConnection,
    SqlServerConnectionConfig,
    SqlServerNotConfigured,
)
from app.infrastructure.sql_server import queries
from app.infrastructure.sql_server.catalog_adapter import PyodbcSqlCatalog
from app.services.sql_connection_service import SqlConnectionStore, StoredSqlConnection
from tests.integration.conftest import SuperAdmin

pytestmark = pytest.mark.integration

PASSWORD = f"sakli-parola-{uuid4().hex};=}}"
SAVED = EffectiveSqlConnection(
    SqlServerConnectionConfig(
        server="sql-dwh.corp.example.test", port=1444, user="dwh_okuyucu", password=PASSWORD
    ),
    ("DWH_Sales", "DWH_Risk"),
)


class Replica:
    """One backend process: its own store, storage and catalog over a fake driver."""

    def __init__(self, key: bytes) -> None:
        self.store = SqlConnectionStore(EffectiveSqlConnection())
        self.storage = StoredSqlConnection(
            session_factory=async_session_factory, cipher=SecretCipher(key), store=self.store
        )
        self.connection_strings: list[str] = []
        self.catalog = PyodbcSqlCatalog(
            connection=self.store.current,
            login_timeout_seconds=15,
            query_timeout_seconds=60,
            max_concurrency=2,
            connect=self._connect,
        )

    def _connect(self, connection_string: str, *, timeout: int, autocommit: bool) -> Any:
        self.connection_strings.append(connection_string)
        return _Connection()


class _Connection:
    timeout = 0

    def cursor(self) -> _Connection:
        return self

    def execute(self, sql: str, *params: Any) -> None:
        assert sql == queries.LIST_DATABASES_SQL and not params

    def fetchall(self) -> list[tuple[str]]:
        return [(name,) for name in ("DWH_Risk", "DWH_Sales", "Scratch", "master")]

    def close(self) -> None:
        pass


@pytest.fixture
async def clean(migrated_database: None) -> AsyncIterator[None]:
    async def delete() -> None:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM sql_connection_setting"))

    await delete()
    yield
    await delete()


@pytest.fixture
def key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def sql_logs() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Handler()
    target = logging.getLogger("app.sql_server")
    previous = target.level
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(previous)


def _events(records: list[logging.LogRecord], name: str) -> list[dict[str, Any]]:
    return [
        dict(getattr(record, "structured_fields", {}))
        for record in records
        if record.getMessage() == name
    ]


def _context(admin: SuperAdmin) -> RequestContext:
    return RequestContext(subject=admin.public_id, is_super_admin=True)


async def _row() -> dict[str, Any]:
    async with engine.connect() as connection:
        row = (await connection.execute(text("SELECT * FROM sql_connection_setting"))).one()
    return dict(row._mapping)


async def _user_id(admin: SuperAdmin) -> int:
    async with engine.connect() as connection:
        return int(
            (
                await connection.execute(
                    text("SELECT user_id FROM app_user WHERE public_id = :public_id"),
                    {"public_id": str(admin.public_id)},
                )
            ).scalar_one()
        )


async def test_the_password_is_encrypted_at_rest_and_the_row_records_who_saved(
    clean: None, key: bytes, super_admin: SuperAdmin
) -> None:
    replica = Replica(key)
    try:
        before, after = await replica.storage.save(_context(super_admin), lambda current: SAVED)
        row = await _row()

        assert before == EffectiveSqlConnection() and after == SAVED
        assert (row["server"], row["port"], row["user_name"]) == (
            "sql-dwh.corp.example.test",
            1444,
            "dwh_okuyucu",
        )
        assert row["allowed_databases"] == ["DWH_Sales", "DWH_Risk"]
        assert row["password_ciphertext"].startswith("v1.")
        assert PASSWORD not in repr(row) and PASSWORD.encode().hex() not in repr(row)
        actor = await _user_id(super_admin)
        assert (row["created_by"], row["updated_by"], row["is_deleted"]) == (actor, actor, False)
        assert row["created_at"].tzinfo is not None and row["updated_at"] >= row["created_at"]

        # A second save updates the same row; the same password is sealed with a new nonce.
        await replica.storage.save(
            _context(super_admin),
            lambda current: EffectiveSqlConnection(current.config, ("DWH_Risk",)),
        )
        again = await _row()
        assert again["sql_connection_setting_id"] == row["sql_connection_setting_id"]
        assert again["password_ciphertext"] != row["password_ciphertext"]
        assert (
            again["allowed_databases"] == ["DWH_Risk"] and again["updated_at"] > row["updated_at"]
        )
        assert replica.store.current().config.password == PASSWORD
    finally:
        replica.catalog.close()


async def test_another_replica_uses_a_save_without_a_restart(
    clean: None, key: bytes, super_admin: SuperAdmin
) -> None:
    saving, serving = Replica(key), Replica(key)
    try:
        await serving.storage.refresh()
        with pytest.raises(SqlServerNotConfigured):
            await serving.catalog.list_databases()

        await saving.storage.save(_context(super_admin), lambda current: SAVED)
        await serving.storage.refresh()

        assert await serving.catalog.list_databases() == ["DWH_Risk", "DWH_Sales"]
        assert serving.catalog.is_allowed("dwh_sales") and not serving.catalog.is_allowed("Scratch")
        used = serving.connection_strings[-1]
        assert "Server=sql-dwh.corp.example.test,1444;" in used
        assert "Encrypt=yes;TrustServerCertificate=no;" in used

        await saving.storage.save(
            _context(super_admin),
            lambda current: EffectiveSqlConnection(
                SqlServerConnectionConfig(
                    server="sql-2.corp.example.test", user="dwh_okuyucu", password=PASSWORD
                ),
                ("DWH_Sales",),
            ),
        )
        await serving.storage.refresh()
        assert await serving.catalog.list_databases() == ["DWH_Sales"]
        assert "Server=sql-2.corp.example.test,1433;" in serving.connection_strings[-1]

        await saving.storage.save(
            _context(super_admin),
            lambda current: EffectiveSqlConnection(
                SqlServerConnectionConfig(server="sql-2.corp.example.test", user="dwh_okuyucu"),
                current.allowed_databases,
            ),
        )
        await serving.storage.refresh()
        with pytest.raises(SqlServerNotConfigured):
            await serving.catalog.list_databases()
    finally:
        saving.catalog.close()
        serving.catalog.close()


async def test_a_password_sealed_with_another_key_leaves_the_connection_not_configured(
    clean: None, key: bytes, super_admin: SuperAdmin, sql_logs: list[logging.LogRecord]
) -> None:
    # Decision 13: after a key change the super admin enters the password again.
    old, new = Replica(key), Replica(os.urandom(32))
    try:
        await old.storage.save(_context(super_admin), lambda current: SAVED)

        for _ in range(3):
            await new.storage.refresh()
        current = new.store.current()

        assert current.configured is False and current.config.password is None
        assert current.config.server == SAVED.config.server
        assert current.allowed_databases == SAVED.allowed_databases
        with pytest.raises(SqlServerNotConfigured):
            await new.catalog.list_databases()
        assert _events(sql_logs, "sql_connection.stored_unusable") == [
            {"event": "sql_connection.stored_unusable", "reason": "password_unreadable"}
        ]

        await new.storage.save(
            _context(super_admin),
            lambda found: EffectiveSqlConnection(
                SqlServerConnectionConfig(
                    server=found.config.server,
                    port=found.config.port,
                    user=found.config.user,
                    password=PASSWORD,
                ),
                found.allowed_databases,
            ),
        )
        await new.storage.refresh()
        assert new.store.current() == SAVED
        assert len(_events(sql_logs, "sql_connection.stored_unusable")) == 1
        rendered = repr([record.__dict__ for record in sql_logs])
        assert PASSWORD not in rendered and (await _row())["password_ciphertext"] not in rendered
    finally:
        old.catalog.close()
        new.catalog.close()


@pytest.mark.parametrize("allowed", [["DWH_Sales", "MASTER"], ["tempdb"]])
async def test_a_saved_allow_list_that_lost_its_guarantees_is_never_used(
    clean: None,
    key: bytes,
    super_admin: SuperAdmin,
    sql_logs: list[logging.LogRecord],
    allowed: list[str],
) -> None:
    replica = Replica(key)
    try:
        await replica.storage.save(_context(super_admin), lambda current: SAVED)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE sql_connection_setting "
                    "SET allowed_databases = CAST(:allowed AS varchar[])"
                ),
                {"allowed": allowed},
            )

        await replica.storage.refresh()

        assert replica.store.current().configured is False
        with pytest.raises(SqlServerNotConfigured):
            await replica.catalog.list_databases()
        assert _events(sql_logs, "sql_connection.stored_unusable") == [
            {"event": "sql_connection.stored_unusable", "reason": "allowed_databases_invalid"}
        ]
    finally:
        replica.catalog.close()


async def test_only_a_current_super_admin_account_can_save(
    clean: None, key: bytes, super_admin: SuperAdmin
) -> None:
    replica = Replica(key)
    try:
        # A token that still says "super admin" for an account that is not one, or is unknown.
        async with engine.begin() as connection:
            tenant_id = (
                await connection.execute(text("SELECT tenant_id FROM tenant WHERE code='platform'"))
            ).scalar_one()
            marker = uuid4().hex
            other = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO app_user (home_tenant_id, public_id, username, email, "
                    "display_name, account_type, directory_object_guid) VALUES (:tenant, "
                    ":public_id, :name, :name, 'Test Person', 'directory', :guid)"
                ),
                {
                    "tenant": tenant_id,
                    "public_id": str(other),
                    "name": f"{marker}@corp.example.test",
                    "guid": uuid4(),
                },
            )
        for subject, status_code in ((other, 403), (uuid4(), 401)):
            with pytest.raises(ApplicationError) as raised:
                await replica.storage.save(
                    RequestContext(subject=subject, is_super_admin=True), lambda current: SAVED
                )
            assert raised.value.status_code == status_code
        async with engine.connect() as connection:
            count = (
                await connection.execute(text("SELECT count(*) FROM sql_connection_setting"))
            ).scalar_one()
        assert count == 0 and replica.store.current() == EffectiveSqlConnection()
    finally:
        replica.catalog.close()


async def test_a_rejected_change_writes_nothing(
    clean: None, key: bytes, super_admin: SuperAdmin
) -> None:
    replica = Replica(key)
    try:
        await replica.storage.save(_context(super_admin), lambda current: SAVED)
        before = await _row()

        def reject(current: EffectiveSqlConnection) -> EffectiveSqlConnection:
            raise ApplicationError(422, "sql_allowed_databases_invalid", "x")

        with pytest.raises(ApplicationError):
            await replica.storage.save(_context(super_admin), reject)

        assert await _row() == before and replica.store.current() == SAVED
    finally:
        replica.catalog.close()


async def test_a_failed_read_keeps_the_last_connection_and_reports_the_error_type(
    clean: None, key: bytes, super_admin: SuperAdmin, sql_logs: list[logging.LogRecord]
) -> None:
    replica = Replica(key)
    try:
        await replica.storage.save(_context(super_admin), lambda current: SAVED)

        def broken() -> Any:
            raise ConnectionError("postgresql is away")

        unreachable = StoredSqlConnection(
            session_factory=broken,  # type: ignore[arg-type]
            cipher=SecretCipher(key),
            store=replica.store,
        )
        await unreachable.refresh()

        assert replica.store.current() == SAVED
        assert _events(sql_logs, "sql_connection.refresh_failed") == [
            {"event": "sql_connection.refresh_failed", "error_type": "ConnectionError"}
        ]
    finally:
        replica.catalog.close()


def test_the_migration_goes_down_and_up_again(migrated_database: None) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    async def table_exists() -> bool:
        probe = create_async_engine(get_settings().database_url)
        try:
            async with probe.connect() as connection:
                found = await connection.execute(
                    text("SELECT to_regclass('public.sql_connection_setting') IS NOT NULL")
                )
                return bool(found.scalar_one())
        finally:
            await probe.dispose()

    try:
        command.downgrade(config, "202609260003")
        assert asyncio.run(table_exists()) is False
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(table_exists()) is True
    command.check(config)
