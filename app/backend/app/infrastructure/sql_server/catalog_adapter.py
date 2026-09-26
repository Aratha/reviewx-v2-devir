"""pyodbc adapter of the SQL Server catalog port (sql-review/PRDs/002-sql-server-connection).

Every driver call runs in a thread pool of ``DWHCODEREVIEW_MSSQL_MAX_CONCURRENCY`` workers, never
on the event loop (Requirement 6). Login and query timeouts come from the settings. The
allow-list is applied before any connection opens (Requirement 7). Driver errors become the
fixed classes of Requirement 8; the only log is one ``sql_server.call`` event per operation
without server, user, password, SQL text or driver message.
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, TypeVar

import pyodbc

from app.core.logging import log_event
from app.domain.sql_server import (
    CatalogObject,
    DatabaseNotAllowed,
    SqlCatalogPort,
    SqlConnectionProbe,
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerErrorClass,
    SqlServerNotConfigured,
)
from app.infrastructure.sql_server.connection_string import build_connection_string
from app.infrastructure.sql_server.dependency_metadata import (
    Connection,
    DependencyMetadataCollector,
)
from app.infrastructure.sql_server.queries import (
    GET_DEFINITION_SQL,
    LIST_DATABASES_SQL,
    LIST_OBJECTS_SQL,
)

logger = logging.getLogger("app.sql_server")

# The connection test always uses a 15 second login timeout (Requirement 4).
CONNECTION_TEST_LOGIN_TIMEOUT_SECONDS = 15
_CONNECTION_STATES = frozenset({"08001", "08S01"})
_TIMEOUT_STATES = frozenset({"HYT00", "HYT01"})
_TLS_MARKERS = ("ssl provider", "certificate", "ssl routines", "tls")
_SQLSTATE_IN_TEXT = re.compile(r"\[([0-9A-Z]{5})\]")

T = TypeVar("T")
# pyodbc.connect-compatible factory: (connection string, timeout=, autocommit=) -> connection.
ConnectFactory = Callable[..., Any]


def classify_driver_error(error: pyodbc.Error) -> SqlServerError:
    """Map a driver error to its Requirement 8 class by SQLSTATE; the text stays internal."""

    args = error.args
    sqlstate = args[0] if args and isinstance(args[0], str) else None
    detail = str(args[1]) if len(args) > 1 else ""
    states = set(_SQLSTATE_IN_TEXT.findall(detail))
    if sqlstate:
        states.add(sqlstate)
    lowered = detail.lower()
    if states & _CONNECTION_STATES and any(marker in lowered for marker in _TLS_MARKERS):
        error_class = SqlServerErrorClass.TLS_FAILED
    elif "28000" in states:
        error_class = SqlServerErrorClass.LOGIN_FAILED
    elif states & _CONNECTION_STATES:
        error_class = SqlServerErrorClass.UNREACHABLE
    elif states & _TIMEOUT_STATES:
        error_class = SqlServerErrorClass.TIMEOUT
    else:
        error_class = SqlServerErrorClass.QUERY_FAILED
    return SqlServerError(error_class, sqlstate)


class PyodbcSqlCatalog:
    """SqlCatalogPort and SqlConnectionProbe over pyodbc and ODBC Driver 18."""

    def __init__(
        self,
        *,
        config: Callable[[], SqlServerConnectionConfig],
        allowed_databases: frozenset[str],
        login_timeout_seconds: int,
        query_timeout_seconds: int,
        max_concurrency: int,
        connect: ConnectFactory = pyodbc.connect,
    ) -> None:
        self._config = config
        # Case-insensitive; empty means every online database (possible only locally).
        self._allowed = frozenset(name.casefold() for name in allowed_databases)
        self._login_timeout = login_timeout_seconds
        self._query_timeout = query_timeout_seconds
        self._connect_factory = connect
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="sql-server"
        )

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def is_allowed(self, database: str) -> bool:
        return not self._allowed or database.casefold() in self._allowed

    async def list_databases(self) -> list[str]:
        config = self._configured()
        return await self._run(
            "list_databases", "master", lambda: self._online_databases(config, self._login_timeout)
        )

    async def list_objects(
        self, database: str, *, query: str | None = None, from_date: date | None = None
    ) -> list[CatalogObject]:
        config = self._configured()
        self._require_allowed(database)
        return await self._run(
            "list_objects",
            database,
            lambda: self._objects(config, database, query, from_date),
        )

    async def fetch_definition(
        self, database: str, schema: str, name: str, type_code: str
    ) -> str | None:
        config = self._configured()
        self._require_allowed(database)
        return await self._run(
            "fetch_definition",
            database,
            lambda: self._definition(config, database, schema, name, type_code.strip()),
        )

    async def fetch_object_metadata(self, database: str, schema: str, name: str) -> str:
        config = self._configured()
        self._require_allowed(database)
        return await self._run(
            "dependency_metadata",
            database,
            lambda: self._metadata(config, database, schema, name),
        )

    async def probe(self, config: SqlServerConnectionConfig) -> list[str]:
        if not config.configured:
            raise SqlServerNotConfigured()
        return await self._run(
            "connection_test",
            "master",
            lambda: self._online_databases(config, CONNECTION_TEST_LOGIN_TIMEOUT_SECONDS),
        )

    def _configured(self) -> SqlServerConnectionConfig:
        config = self._config()
        if not config.configured:
            raise SqlServerNotConfigured()
        return config

    def _require_allowed(self, database: str) -> None:
        if not self.is_allowed(database):
            raise DatabaseNotAllowed()

    async def _run(self, operation: str, database: str, work: Callable[[], T]) -> T:
        started = time.monotonic()
        outcome = "ok"
        sqlstate: str | None = None
        rows: int | None = None
        try:
            result = await asyncio.get_running_loop().run_in_executor(self._executor, work)
            rows = len(result) if isinstance(result, list) else int(bool(result))
        except pyodbc.Error as error:
            classified = classify_driver_error(error)
            outcome, sqlstate = classified.error_class.value, classified.sqlstate
            raise classified from None
        finally:
            log_event(
                logger,
                "sql_server.call",
                operation=operation,
                database=database,
                outcome=outcome,
                sqlstate=sqlstate,
                duration_ms=int((time.monotonic() - started) * 1000),
                rows=rows,
            )
        return result

    def _open(
        self, config: SqlServerConnectionConfig, database: str, login_timeout: int
    ) -> Connection:
        connection = self._connect_factory(
            build_connection_string(config, database), timeout=login_timeout, autocommit=True
        )
        connection.timeout = self._query_timeout
        return connection  # type: ignore[no-any-return]

    def _online_databases(self, config: SqlServerConnectionConfig, login_timeout: int) -> list[str]:
        with closing(self._open(config, "master", login_timeout)) as connection:
            cursor = connection.cursor()
            cursor.execute(LIST_DATABASES_SQL)
            names = [str(row[0]) for row in cursor.fetchall()]
        return [name for name in names if self.is_allowed(name)]

    def _objects(
        self,
        config: SqlServerConnectionConfig,
        database: str,
        query: str | None,
        from_date: date | None,
    ) -> list[CatalogObject]:
        with closing(self._open(config, database, self._login_timeout)) as connection:
            cursor = connection.cursor()
            cursor.execute(LIST_OBJECTS_SQL)
            fetched = cursor.fetchall()
        needle = (query or "").strip().lower()
        cutoff = datetime.combine(from_date, datetime.min.time()) if from_date else None
        result: list[CatalogObject] = []
        for row in fetched:
            schema, name, object_type = str(row[0]), str(row[1]), str(row[3])
            created_at, last_modified = row[4], row[5]
            if cutoff is not None and not (
                (created_at is not None and created_at >= cutoff)
                or (last_modified is not None and last_modified >= cutoff)
            ):
                continue
            if needle and needle not in f"{schema} {name} {object_type}".lower():
                continue
            result.append(
                CatalogObject(
                    schema=schema,
                    name=name,
                    type=object_type,
                    type_code=str(row[2] or "").strip(),
                    created_at=created_at,
                    last_modified=last_modified,
                )
            )
        return result

    def _definition(
        self,
        config: SqlServerConnectionConfig,
        database: str,
        schema: str,
        name: str,
        type_code: str,
    ) -> str | None:
        with closing(self._open(config, database, self._login_timeout)) as connection:
            cursor = connection.cursor()
            cursor.execute(GET_DEFINITION_SQL, schema, name, type_code)
            row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0])

    def _metadata(
        self, config: SqlServerConnectionConfig, database: str, schema: str, name: str
    ) -> str:
        collector = DependencyMetadataCollector(
            connect=lambda db: self._open(config, db, self._login_timeout),
            database_names=self._online_databases(config, self._login_timeout),
        )
        return collector.collect(database, schema, name)


if TYPE_CHECKING:

    def _implements_catalog(catalog: PyodbcSqlCatalog) -> SqlCatalogPort:
        return catalog

    def _implements_probe(catalog: PyodbcSqlCatalog) -> SqlConnectionProbe:
        return catalog
