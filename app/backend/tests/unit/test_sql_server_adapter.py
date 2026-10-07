"""SQL Server connection string, error classes, database list, catalog filters, metadata limits.

sql-review/PRDs/002-sql-server-connection Requirement 2, 6, 7 and 8 (Acceptance 1 and 2). A fake
driver replaces pyodbc; it answers the ported catalog queries from an in-memory server model.
"""

import asyncio
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pyodbc
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.domain.sql_server import (
    DatabaseNotAllowed,
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerErrorClass,
    SqlServerNotConfigured,
)
from app.infrastructure.sql_server import queries
from app.infrastructure.sql_server.catalog_adapter import (
    PyodbcSqlCatalog,
    classify_driver_error,
)
from app.infrastructure.sql_server.connection_string import (
    InvalidConnectionValue,
    build_connection_string,
)
from app.infrastructure.sql_server.dependency_metadata import (
    MAX_DATABASES_TO_SCAN,
    MAX_OBJECTS_WITH_COLUMNS,
    MAX_OUTPUT_CHARS,
    format_column_type,
    split_sql_identifiers,
    try_parse_three_part,
)
from app.main import app
from tests.fakes.telemetry import TelemetryCapture

pytestmark = pytest.mark.unit

PASSWORD = "p;w}d={x"
CONFIG = SqlServerConnectionConfig(
    server="sql.corp.example.test", port=1433, user="okuyucu", password=PASSWORD
)


def parse_connection_string(value: str) -> dict[str, str]:
    """ODBC rules: a value in braces runs to the matching single '}' ('}}' is a literal)."""

    result: dict[str, str] = {}
    index = 0
    while index < len(value):
        equals = value.index("=", index)
        key = value[index:equals]
        index = equals + 1
        if value[index] == "{":
            index += 1
            chars: list[str] = []
            while True:
                if value[index] == "}":
                    if value[index + 1 : index + 2] == "}":
                        chars.append("}")
                        index += 2
                        continue
                    index += 1
                    break
                chars.append(value[index])
                index += 1
            parsed = "".join(chars)
        else:
            end = value.index(";", index)
            parsed = value[index:end]
            index = end
        assert key not in result, f"duplicate keyword {key}"
        result[key] = parsed
        assert value[index] == ";"
        index += 1
    return result


def test_connection_string_braces_every_credential_and_database() -> None:
    config = SqlServerConnectionConfig(
        server="sql.corp.example.test",
        port=14330,
        user="u;Server=evil",
        password="p};Encrypt=no;{x=",
        encrypt=True,
        trust_server_certificate=False,
    )

    fields = parse_connection_string(build_connection_string(config, "DB;x}=1"))

    assert fields == {
        "Driver": "ODBC Driver 18 for SQL Server",
        "Server": "sql.corp.example.test,14330",
        "Database": "DB;x}=1",
        "UID": "u;Server=evil",
        "PWD": "p};Encrypt=no;{x=",
        "Encrypt": "yes",
        "TrustServerCertificate": "no",
    }


@pytest.mark.parametrize(
    "server", ["sql\nhost", "sql;Encrypt=no", "sql{x}", "sql host", "sql=1", "sql\x00"]
)
def test_unsafe_server_names_are_rejected(server: str) -> None:
    with pytest.raises(InvalidConnectionValue):
        build_connection_string(SqlServerConnectionConfig(server, 1433, "u", "p"), "master")


def test_server_names_with_instances_and_addresses_are_accepted() -> None:
    for server in ("10.1.2.3", "sql-01.corp.example.test", "SQL01\\DWH", "[fd00::1]"):
        assert build_connection_string(SqlServerConnectionConfig(server, 1433, "u", "p"), "master")


def test_control_characters_in_the_user_name_are_rejected() -> None:
    with pytest.raises(InvalidConnectionValue):
        build_connection_string(SqlServerConnectionConfig("sql", 1433, "u\tx", "p"), "master")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("08001", "[08001] TCP Provider: Error code 0x2749"), "sql_server_unreachable"),
        (("08S01", "[08S01] Communication link failure"), "sql_server_unreachable"),
        (("28000", "[28000] Login failed for user 'x'."), "sql_login_failed"),
        (("HYT00", "[HYT00] Login timeout expired (0)"), "sql_timeout"),
        (("HYT01", "[HYT01] Connection timeout expired"), "sql_timeout"),
        (
            ("08001", "[08001] SSL Provider: certificate verify failed: unable to get issuer"),
            "sql_tls_failed",
        ),
        (("42000", "[42000] Invalid object name 'x'."), "sql_query_failed"),
        (
            ("HYT00", "[HYT00] Login timeout expired; [08001] TCP Provider: timeout"),
            "sql_server_unreachable",
        ),
        ((), "sql_query_failed"),
    ],
)
def test_driver_errors_map_to_fixed_classes(args: tuple[str, ...], expected: str) -> None:
    classified = classify_driver_error(pyodbc.OperationalError(*args))
    assert classified.error_class.value == expected
    assert "Login" not in classified.message and "Provider" not in classified.message


# --- fake driver -------------------------------------------------------------------------


@dataclass
class FakeObject:
    object_id: int
    schema: str
    name: str
    type_code: str
    definition: str | None = None
    created: datetime | None = None
    modified: datetime | None = None
    # (schema, name, referenced_id[, referenced_database_name]) as sys.dm_sql_referenced_entities
    # reports them; the id of a three-part reference belongs to the named database.
    references: list[tuple[Any, ...]] = field(default_factory=list)
    columns: list[tuple[str, str, int, int, int, bool]] = field(default_factory=list)


@dataclass
class FakeServer:
    databases: dict[str, list[FakeObject]] = field(default_factory=dict)
    offline: set[str] = field(default_factory=set)
    connections: list[str] = field(default_factory=list)
    connection_strings: list[str] = field(default_factory=list)
    delay_seconds: float = 0.0
    active: int = 0
    peak: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    error: pyodbc.Error | None = None
    query_error: pyodbc.Error | None = None

    def connect(
        self, connection_string: str, *, timeout: int, autocommit: bool
    ) -> "FakeConnection":
        assert autocommit is True and timeout > 0
        database = parse_connection_string(connection_string)["Database"]
        self.connection_strings.append(connection_string)
        self.connections.append(database)
        if self.error is not None:
            raise self.error
        return FakeConnection(self, database)


class FakeConnection:
    def __init__(self, server: FakeServer, database: str) -> None:
        self.server = server
        self.database = database
        self.timeout = 0

    def cursor(self) -> "FakeCursor":
        return FakeCursor(self)

    def close(self) -> None:
        pass


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.rows: list[tuple[Any, ...]] = []

    @property
    def objects(self) -> list[FakeObject]:
        return self.connection.server.databases.get(self.connection.database, [])

    def execute(self, sql: str, *params: Any) -> None:
        server = self.connection.server
        with server.lock:
            server.active += 1
            server.peak = max(server.peak, server.active)
        try:
            if server.delay_seconds:
                time.sleep(server.delay_seconds)
            if server.query_error is not None:
                raise server.query_error
            self.rows = self._answer(sql, params)
        finally:
            with server.lock:
                server.active -= 1

    def _answer(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        if sql == queries.LIST_DATABASES_SQL:
            names = sorted(set(self.connection.server.databases) | {"master", "tempdb"})
            return [(name,) for name in names if name not in self.connection.server.offline]
        if sql == queries.LIST_OBJECTS_SQL:
            ordered = sorted(self.objects, key=lambda o: (o.schema, o.name))
            return [
                (o.schema, o.name, o.type_code.ljust(2), _label(o.type_code), o.created, o.modified)
                for o in ordered
                if o.type_code in {"P", "V", "FN", "IF", "TF", "SF"}
            ]
        if sql == queries.GET_DEFINITION_SQL:
            schema, name, type_code = params
            return [
                (o.definition,)
                for o in self.objects
                if (o.schema, o.name, o.type_code) == (schema, name, type_code)
            ]
        if sql == queries.REFERENCED_ENTITIES_SQL:
            (qualified,) = params
            match = [o for o in self.objects if f"{o.schema}.{o.name}" == qualified]
            return [(*ref, None)[:4] for ref in match[0].references] if match else []
        if sql == queries.OBJECT_BY_ID_SQL:
            (object_id,) = params
            return [(o.object_id, o.type_code) for o in self.objects if o.object_id == object_id]
        if sql == queries.OBJECT_BY_NAME_SQL:
            schema, name = params
            return [
                (o.object_id, o.type_code)
                for o in self.objects
                if (o.schema, o.name) == (schema, name)
            ]
        if sql == queries.SCHEMA_AND_NAME_BY_ID_SQL:
            (object_id,) = params
            return [(o.schema, o.name) for o in self.objects if o.object_id == object_id]
        if sql == queries.columns_sql(len(params)):
            wanted = set(params)
            rows: list[tuple[Any, ...]] = []
            for o in self.objects:
                if o.object_id in wanted:
                    for index, (name, type_name, length, precision, scale, nullable) in enumerate(
                        o.columns, 1
                    ):
                        rows.append(
                            (
                                o.schema,
                                o.name,
                                o.type_code,
                                name,
                                type_name,
                                length,
                                precision,
                                scale,
                                nullable,
                                index,
                            )
                        )
            return rows
        raise AssertionError("unexpected statement")

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None


def _sql_datetime(year: int, month: int, day: int) -> datetime:
    # sys.objects dates are SQL Server datetime values, which carry no time zone.
    return datetime(year, month, day)  # noqa: DTZ001


def _label(type_code: str) -> str:
    return {"P": "PROCEDURE", "V": "VIEW", "FN": "FUNCTION_SCALAR", "U": "TABLE"}.get(
        type_code, type_code
    )


def _catalog(
    server: FakeServer,
    *,
    config: SqlServerConnectionConfig = CONFIG,
    max_concurrency: int = 4,
) -> PyodbcSqlCatalog:
    return PyodbcSqlCatalog(
        config=lambda: config,
        login_timeout_seconds=15,
        query_timeout_seconds=60,
        max_concurrency=max_concurrency,
        connect=server.connect,
    )


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
    target.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(previous)


async def test_every_online_database_is_offered_except_the_system_databases() -> None:
    # Requirement 7 and Decision 5: no list narrows what the account can access.
    server = FakeServer(
        databases={"DWH_Sales": [], "dwh_risk": [], "Scratch": [], "Model": [], "MSDB": []},
        offline={"dwh_risk"},
    )
    catalog = _catalog(server)
    try:
        assert await catalog.list_databases() == ["DWH_Sales", "Scratch"]
        assert await catalog.probe(CONFIG) == ["DWH_Sales", "Scratch"]
    finally:
        catalog.close()


def test_the_database_list_asks_only_for_online_databases_the_account_can_enter() -> None:
    sql = " ".join(queries.LIST_DATABASES_SQL.split())
    assert (
        sql
        == "SELECT name FROM sys.databases WHERE state = 0 AND HAS_DBACCESS(name) = 1 ORDER BY name;"
    )


@pytest.mark.parametrize("database", ["master", "TempDB", "model", " msdb "])
async def test_system_databases_never_reach_sql_server(database: str) -> None:
    server = FakeServer(databases={"DWH": [FakeObject(1, "dbo", "p", "P", "select 1")]})
    catalog = _catalog(server)
    try:
        assert catalog.is_allowed("DWH") and catalog.is_allowed("AnyOtherDatabase")
        assert not catalog.is_allowed(database)
        for call in (
            catalog.list_objects(database),
            catalog.fetch_definition(database, "dbo", "p", "P"),
            catalog.fetch_object_metadata(database, "dbo", "p"),
        ):
            with pytest.raises(DatabaseNotAllowed):
                await call
        assert server.connections == []
    finally:
        catalog.close()


async def test_a_database_the_account_cannot_open_fails_with_a_fixed_class() -> None:
    # No allow-list stands in front of the account's own permissions: the driver answers.
    server = FakeServer(
        databases={"DWH": []},
        error=pyodbc.ProgrammingError(
            "42000", "[42000] Cannot open database requested by the login. (4060)"
        ),
    )
    catalog = _catalog(server)
    try:
        with pytest.raises(SqlServerError) as raised:
            await catalog.list_objects("Closed")
        assert raised.value.error_class is SqlServerErrorClass.QUERY_FAILED
    finally:
        catalog.close()


async def test_calls_without_configuration_are_refused_before_connecting() -> None:
    server = FakeServer()
    catalog = _catalog(server, config=SqlServerConnectionConfig(server="sql", user="u"))
    try:
        with pytest.raises(SqlServerNotConfigured):
            await catalog.list_databases()
        assert server.connections == []
    finally:
        catalog.close()


async def test_a_changed_connection_is_used_on_the_next_call() -> None:
    # Requirement 11: a save takes effect without a restart.
    server = FakeServer(databases={"DWH": [FakeObject(1, "dbo", "p", "P")]})
    current = [CONFIG]
    catalog = PyodbcSqlCatalog(
        config=lambda: current[0],
        login_timeout_seconds=15,
        query_timeout_seconds=60,
        max_concurrency=2,
        connect=server.connect,
    )
    try:
        assert await catalog.list_databases() == ["DWH"]
        first = parse_connection_string(server.connection_strings[-1])
        assert (first["Server"], first["TrustServerCertificate"]) == (
            "sql.corp.example.test,1433",
            "no",
        )

        current[0] = SqlServerConnectionConfig(
            server="sql-2.corp.example.test",
            port=1500,
            user="yeni",
            password="yeni-parola",
            trust_server_certificate=True,
        )

        assert [item.name for item in await catalog.list_objects("DWH")] == ["p"]
        last = parse_connection_string(server.connection_strings[-1])
        assert (last["Server"], last["UID"]) == ("sql-2.corp.example.test,1500", "yeni")
        # Decision 6 exception: still encrypted, the certificate is not verified.
        assert (last["Encrypt"], last["TrustServerCertificate"]) == ("yes", "yes")

        current[0] = SqlServerConnectionConfig()
        with pytest.raises(SqlServerNotConfigured):
            await catalog.list_databases()
    finally:
        catalog.close()


async def test_object_list_filters_by_text_and_date_like_the_source() -> None:
    objects = [
        FakeObject(
            1,
            "dbo",
            "usp_Load",
            "P",
            created=_sql_datetime(2026, 1, 1),
            modified=_sql_datetime(2026, 5, 2),
        ),
        FakeObject(2, "rpt", "vw_Sales", "V", created=_sql_datetime(2026, 6, 1), modified=None),
        FakeObject(
            3,
            "dbo",
            "fn_Old",
            "FN",
            created=_sql_datetime(2025, 1, 1),
            modified=_sql_datetime(2025, 2, 1),
        ),
        FakeObject(4, "dbo", "Customers", "U"),
    ]
    catalog = _catalog(FakeServer(databases={"DWH": objects}))
    try:
        everything = await catalog.list_objects("DWH")
        by_text = await catalog.list_objects("DWH", query="  PROCEDURE ")
        by_date = await catalog.list_objects("DWH", from_date=date(2026, 5, 2))
    finally:
        catalog.close()

    assert [(o.schema, o.name, o.type_code, o.type) for o in everything] == [
        ("dbo", "fn_Old", "FN", "FUNCTION_SCALAR"),
        ("dbo", "usp_Load", "P", "PROCEDURE"),
        ("rpt", "vw_Sales", "V", "VIEW"),
    ]
    assert [o.name for o in by_text] == ["usp_Load"]
    assert [o.name for o in by_date] == ["usp_Load", "vw_Sales"]


async def test_definition_is_read_with_parameters_and_missing_is_none() -> None:
    server = FakeServer(
        databases={"DWH": [FakeObject(1, "dbo", "p", "P", "CREATE PROC p AS SELECT 1")]}
    )
    catalog = _catalog(server)
    try:
        assert (
            await catalog.fetch_definition("DWH", "dbo", "p", " P ") == "CREATE PROC p AS SELECT 1"
        )
        assert await catalog.fetch_definition("DWH", "dbo", "missing", "P") is None
    finally:
        catalog.close()


async def test_driver_failures_surface_as_classes_and_log_without_secrets(
    sql_logs: list[logging.LogRecord],
) -> None:
    server = FakeServer(
        error=pyodbc.OperationalError(
            "28000", f"[28000] Login failed for user 'okuyucu' on sql.corp.example.test {PASSWORD}"
        )
    )
    catalog = _catalog(server)
    try:
        with pytest.raises(SqlServerError) as raised:
            await catalog.list_databases()
    finally:
        catalog.close()

    assert raised.value.error_class is SqlServerErrorClass.LOGIN_FAILED
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    (event,) = [r for r in sql_logs if r.getMessage() == "sql_server.call"]
    fields = event.structured_fields  # type: ignore[attr-defined]
    assert fields["operation"] == "list_databases"
    assert fields["outcome"] == "sql_login_failed" and fields["sqlstate"] == "28000"
    rendered = repr(fields)
    for secret in (PASSWORD, "okuyucu", "sql.corp.example.test", "Login failed"):
        assert secret not in rendered


async def test_successful_calls_log_operation_database_rows_and_duration(
    sql_logs: list[logging.LogRecord],
) -> None:
    catalog = _catalog(FakeServer(databases={"DWH": [FakeObject(1, "dbo", "p", "P")]}))
    try:
        await catalog.list_objects("DWH")
    finally:
        catalog.close()
    (event,) = [r for r in sql_logs if r.getMessage() == "sql_server.call"]
    fields = event.structured_fields  # type: ignore[attr-defined]
    assert fields["operation"] == "list_objects" and fields["database"] == "DWH"
    assert fields["outcome"] == "ok" and fields["rows"] == 1 and fields["sqlstate"] is None
    assert isinstance(fields["duration_ms"], int)


def _chain(database: str, length: int, start: int = 1) -> list[FakeObject]:
    """view_1 -> view_2 -> ... -> view_n, each with one column."""

    objects: list[FakeObject] = []
    for index in range(start, start + length):
        references = [("dbo", f"view_{index + 1}", None)] if index < start + length - 1 else []
        objects.append(
            FakeObject(
                index,
                "dbo",
                f"view_{index}",
                "V",
                references=references,
                columns=[("c", "int", 4, 10, 0, False)],
            )
        )
    return objects


async def test_metadata_follows_dependencies_at_most_four_levels_deep() -> None:
    objects = [FakeObject(100, "dbo", "usp_Root", "P", references=[("dbo", "view_1", None)])]
    objects += _chain("DWH", 7)
    catalog = _catalog(FakeServer(databases={"DWH": objects}))
    try:
        text = await catalog.fetch_object_metadata("DWH", "dbo", "usp_Root")
    finally:
        catalog.close()

    assert text.startswith("Analiz kökü veritabanı: DWH\n")
    assert "### Veritabanı: [DWH]" in text
    listed = [line for line in text.splitlines() if line.startswith("- dbo.view_")]
    assert listed == [f"- dbo.view_{n} (VIEW)" for n in range(1, 6)]


async def test_metadata_is_capped_at_48_objects_and_95000_characters() -> None:
    wide_columns = [(f"kolon_{n:03d}_" + "x" * 40, "nvarchar", 400, 0, 0, True) for n in range(60)]
    targets = [
        FakeObject(1000 + n, "dbo", f"tbl_{n:03d}", "U", columns=wide_columns) for n in range(60)
    ]
    root = FakeObject(
        1, "dbo", "usp_Wide", "P", references=[("dbo", t.name, t.object_id) for t in targets]
    )
    catalog = _catalog(FakeServer(databases={"DWH": [root, *targets]}))
    try:
        text = await catalog.fetch_object_metadata("DWH", "dbo", "usp_Wide")
    finally:
        catalog.close()

    assert len(text) <= MAX_OUTPUT_CHARS
    assert text.endswith("[… metin uzunluk sınırı nedeniyle kesildi …]")
    tables = {line for line in text.splitlines() if line.startswith("- dbo.tbl_")}
    assert 0 < len(tables) <= MAX_OBJECTS_WITH_COLUMNS
    assert "- dbo.tbl_048 (TABLE)" not in tables


async def test_cross_database_lookup_scans_accessible_databases_but_never_system_ones() -> None:
    root = FakeObject(
        1, "dbo", "usp_Root", "P", references=[("dbo", "Shared", None), ("dbo", "Hidden", None)]
    )
    server = FakeServer(
        databases={
            "DWH": [root],
            "Ref": [FakeObject(7, "dbo", "Shared", "U", columns=[("id", "int", 4, 10, 0, False)])],
            "msdb": [
                FakeObject(8, "dbo", "Hidden", "U", columns=[("gizli", "int", 4, 10, 0, False)])
            ],
        }
    )
    catalog = _catalog(server)
    try:
        text = await catalog.fetch_object_metadata("DWH", "dbo", "usp_Root")
    finally:
        catalog.close()

    assert "### Veritabanı: [Ref]" in text and "- dbo.Shared (TABLE)" in text
    assert "Hidden" not in text and "gizli" not in text
    # master is opened only to list the databases; no system database is scanned for objects.
    assert set(server.connections) == {"DWH", "Ref", "master"}


async def test_cross_database_search_is_bounded_per_name_and_per_request() -> None:
    # Without an allow-list the bounds are the collector's own: at most 48 databases per missing
    # name, and each missing name is searched once however many objects refer to it.
    references = [("dbo", "Missing", None), ("dbo", "Missing", None), ("dbo", "Child", None)]
    child = FakeObject(2, "dbo", "Child", "V", references=[("dbo", "Missing", None)])
    databases: dict[str, list[FakeObject]] = {
        "AAA": [FakeObject(1, "dbo", "usp_Root", "P", references=references), child]
    }
    databases.update({f"DB{number:03d}": [] for number in range(60)})
    server = FakeServer(databases=databases)
    catalog = _catalog(server)
    try:
        await catalog.fetch_object_metadata("AAA", "dbo", "usp_Root")
    finally:
        catalog.close()

    scanned = [name for name in server.connections if name.startswith("DB")]
    assert len(scanned) == len(set(scanned)) == MAX_DATABASES_TO_SCAN - 1
    assert "DB059" not in scanned


async def test_a_three_part_reference_resolves_its_id_in_the_named_database() -> None:
    # The referenced id of EDW.CON.Account is its id inside EDW; the referencing database holds
    # an unrelated object with the same id, which must never be reported or expanded.
    root = FakeObject(
        1,
        "CON",
        "ins_Summary",
        "P",
        references=[("CON", "Account", 7, "edw"), ("CON", "Secret", 8, "Other")],
    )
    unrelated = FakeObject(
        7,
        "SMT",
        "vUnrelated",
        "V",
        columns=[("ilgisiz", "int", 4, 10, 0, False)],
        references=[("SMT", "Deeper", 9, None)],
    )
    server = FakeServer(
        databases={
            "EDWDM": [root, unrelated, FakeObject(9, "SMT", "Deeper", "U")],
            "EDW": [
                FakeObject(
                    7, "CON", "Account", "U", columns=[("AccountId", "int", 4, 10, 0, False)]
                )
            ],
            "Other": [
                FakeObject(8, "CON", "Secret", "U", columns=[("gizli", "int", 4, 10, 0, False)])
            ],
        },
        offline={"Other"},
    )
    catalog = _catalog(server)
    try:
        text = await catalog.fetch_object_metadata("EDWDM", "CON", "ins_Summary")
    finally:
        catalog.close()

    assert "### Veritabanı: [EDW]\n- CON.Account (TABLE)\n  - AccountId int NOT NULL" in text
    assert "vUnrelated" not in text and "ilgisiz" not in text and "Deeper" not in text
    assert "Secret" not in text and "gizli" not in text
    assert "Other" not in server.connections


async def test_a_login_timeout_is_unreachable_but_a_query_timeout_stays_a_timeout(
    sql_logs: list[logging.LogRecord],
) -> None:
    # The driver answers a closed port or an unknown host only with the login timeout HYT00.
    server = FakeServer(
        databases={"DWH": []},
        error=pyodbc.OperationalError("HYT00", "[HYT00] Login timeout expired (0)"),
    )
    catalog = _catalog(server)
    try:
        with pytest.raises(SqlServerError) as unreachable:
            await catalog.list_databases()
        server.error = None
        server.query_error = pyodbc.OperationalError("HYT00", "[HYT00] Query timeout expired (0)")
        with pytest.raises(SqlServerError) as timed_out:
            await catalog.list_objects("DWH")
    finally:
        catalog.close()

    assert unreachable.value.error_class is SqlServerErrorClass.UNREACHABLE
    assert unreachable.value.sqlstate == "HYT00"
    assert timed_out.value.error_class is SqlServerErrorClass.TIMEOUT
    outcomes = [
        record.structured_fields["outcome"]  # type: ignore[attr-defined]
        for record in sql_logs
        if getattr(record, "structured_fields", {}).get("event") == "sql_server.call"
    ]
    assert outcomes == ["sql_server_unreachable", "sql_timeout"]


async def test_a_failing_metadata_connection_is_reported_as_its_class() -> None:
    server = FakeServer(error=pyodbc.OperationalError("08001", "[08001] TCP Provider"))
    catalog = _catalog(server)
    try:
        with pytest.raises(SqlServerError) as raised:
            await catalog.fetch_object_metadata("DWH", "dbo", "p")
    finally:
        catalog.close()
    assert raised.value.error_class is SqlServerErrorClass.UNREACHABLE


def test_ported_identifier_and_type_helpers_keep_the_source_semantics() -> None:
    assert split_sql_identifiers("[Sales DB].[dbo].[Orders]") == ["Sales DB", "dbo", "Orders"]
    assert split_sql_identifiers(" Ref . dbo.Shared") == ["Ref", "dbo", "Shared"]
    assert try_parse_three_part("dbo", "Ref.dbo.Shared") == ("Ref", "dbo", "Shared")
    assert try_parse_three_part("", "srv.Ref.dbo.Shared") == ("Ref", "dbo", "Shared")
    assert try_parse_three_part("dbo", "Shared") is None
    assert format_column_type("nvarchar", 100, 0, 0) == "nvarchar(50)"
    assert format_column_type("varchar", -1, 0, 0) == "varchar(max)"
    assert format_column_type("decimal", 9, 18, 2) == "decimal(18,2)"
    assert format_column_type("datetime2", 8, 27, 7) == "datetime2(7)"


async def test_a_slow_catalog_call_never_blocks_the_event_loop() -> None:
    """Requirement 6: a 5 second SQL Server wait leaves the API answering under 200 ms."""

    server = FakeServer(databases={"DWH": []}, delay_seconds=5.0)
    catalog = _catalog(server)
    prefix = get_settings().api_prefix
    try:
        slow = asyncio.create_task(catalog.list_databases())
        await asyncio.sleep(0.1)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            started = time.monotonic()
            response = await client.get(f"{prefix}/liveness")
            elapsed = time.monotonic() - started
        assert response.status_code == 200
        assert elapsed < 0.2
        assert not slow.done()
        assert await slow == ["DWH"]
    finally:
        catalog.close()


async def test_concurrent_calls_never_exceed_the_configured_limit() -> None:
    server = FakeServer(databases={"DWH": []}, delay_seconds=0.05)
    catalog = _catalog(server, max_concurrency=2)
    try:
        await asyncio.gather(*(catalog.list_databases() for _ in range(8)))
    finally:
        catalog.close()
    assert server.peak == 2


async def test_calls_emit_the_prd_metrics_and_spans_without_names_or_secrets(
    telemetry_capture: TelemetryCapture,
) -> None:
    """Gözlemlenebilirlik: calls, duration and in-flight gauge by operation and outcome class."""

    ok = _catalog(FakeServer(databases={"DWH_Secret_Sales": [FakeObject(1, "dbo", "p", "P")]}))
    failing = _catalog(
        FakeServer(
            error=pyodbc.OperationalError(
                "28000", f"[28000] Login failed for user 'okuyucu' {PASSWORD}"
            )
        )
    )
    try:
        await ok.list_objects("DWH_Secret_Sales", query="musteri")
        with pytest.raises(SqlServerError):
            await failing.fetch_definition("DWH_Secret_Sales", "dbo", "p", "P")
    finally:
        ok.close()
        failing.close()

    calls = "dwhcodereview_sql_server_calls_total"
    assert telemetry_capture.value(calls, operation="list_objects", outcome="ok") == 1
    assert (
        telemetry_capture.value(calls, operation="fetch_definition", outcome="sql_login_failed")
        == 1
    )
    assert {
        labels["operation"]
        for labels, _ in telemetry_capture.points("dwhcodereview_sql_server_call_duration_seconds")
    } == {"list_objects", "fetch_definition"}
    assert telemetry_capture.value("dwhcodereview_sql_server_inflight") == 0
    (failed_span,) = telemetry_capture.spans("sql_server fetch_definition")
    assert failed_span.attributes is not None
    assert failed_span.attributes["dwhcodereview.outcome"] == "sql_login_failed"
    captured = telemetry_capture.everything()
    for forbidden in (
        "DWH_Secret_Sales",
        "musteri",
        PASSWORD,
        "okuyucu",
        "sql.corp.example.test",
        "Login failed",
        "SELECT",
    ):
        assert forbidden not in captured


async def test_the_in_flight_gauge_counts_calls_waiting_for_the_pool(
    telemetry_capture: TelemetryCapture,
) -> None:
    server = FakeServer(databases={"DWH": []}, delay_seconds=0.2)
    catalog = _catalog(server, max_concurrency=1)
    try:
        calls = [asyncio.create_task(catalog.list_databases()) for _ in range(3)]
        await asyncio.sleep(0.05)
        assert telemetry_capture.value("dwhcodereview_sql_server_inflight") == 3
        await asyncio.gather(*calls)
    finally:
        catalog.close()
    assert telemetry_capture.value("dwhcodereview_sql_server_inflight") == 0
