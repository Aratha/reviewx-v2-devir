"""SQL Server catalog port and its fixed error classes (sql-review/PRDs/002-sql-server-connection).

The application reads only catalog views, object definitions and dependency metadata through
``SqlCatalogPort`` (Decision 2). Failures reach callers as one of the Requirement 8 classes with
a fixed Turkish message; the driver text, server, user and SQL never leave the adapter.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

# Object types of LIST_OBJECTS_SQL and their display names.
CATALOG_OBJECT_TYPES: dict[str, str] = {
    "P": "PROCEDURE",
    "V": "VIEW",
    "FN": "FUNCTION_SCALAR",
    "IF": "FUNCTION_INLINE",
    "TF": "FUNCTION_TABLE",
    "SF": "FUNCTION_SQL_INLINE",
}
SYSTEM_DATABASES = frozenset({"master", "tempdb", "model", "msdb"})
SERVER_MAX_LENGTH = 255
USER_NAME_MAX_LENGTH = 128
# SQL Server identifiers (sysname) hold at most 128 characters.
DATABASE_NAME_MAX_LENGTH = 128


class SqlServerErrorClass(StrEnum):
    UNREACHABLE = "sql_server_unreachable"
    LOGIN_FAILED = "sql_login_failed"
    TIMEOUT = "sql_timeout"
    TLS_FAILED = "sql_tls_failed"
    QUERY_FAILED = "sql_query_failed"


SQL_SERVER_ERROR_MESSAGES: dict[SqlServerErrorClass, str] = {
    SqlServerErrorClass.UNREACHABLE: "SQL Server'a ulaşılamadı.",
    SqlServerErrorClass.LOGIN_FAILED: "SQL Server girişi reddedildi.",
    SqlServerErrorClass.TIMEOUT: "SQL Server zamanında yanıt vermedi.",
    SqlServerErrorClass.TLS_FAILED: "SQL Server ile güvenli bağlantı kurulamadı.",
    SqlServerErrorClass.QUERY_FAILED: "SQL Server sorgusu tamamlanamadı.",
}


class SqlServerError(Exception):
    """A classified SQL Server failure; ``sqlstate`` is for logs only."""

    def __init__(self, error_class: SqlServerErrorClass, sqlstate: str | None = None) -> None:
        super().__init__(error_class.value)
        self.error_class = error_class
        self.sqlstate = sqlstate

    @property
    def message(self) -> str:
        return SQL_SERVER_ERROR_MESSAGES[self.error_class]


NOT_CONFIGURED_CODE = "sql_connection_not_configured"
NOT_CONFIGURED_MESSAGE = "SQL Server bağlantısı yapılandırılmamış."
DATABASE_NOT_ALLOWED_CODE = "database_not_allowed"
DATABASE_NOT_ALLOWED_MESSAGE = "Bu veritabanı inceleme için izinli değil."


class SqlServerNotConfigured(Exception):
    """No server, user or password is configured; catalog endpoints answer 503."""


class DatabaseNotAllowed(Exception):
    """The database is outside the allow-list; rejected before any SQL Server call."""


@dataclass(frozen=True, slots=True)
class SqlServerConnectionConfig:
    """The structured connection fields (Decision 1); there is no free connection string."""

    server: str = ""
    port: int = 1433
    user: str = ""
    password: str | None = field(default=None, repr=False)
    encrypt: bool = True
    trust_server_certificate: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.server and self.user and self.password)


@dataclass(frozen=True, slots=True)
class EffectiveSqlConnection:
    """The connection in force together with its allow-list; both always change together.

    ``allowed_databases`` keeps the names as they were entered. An empty list means every online
    database and is possible only in the local environment (Requirement 7).
    """

    config: SqlServerConnectionConfig = field(default_factory=SqlServerConnectionConfig)
    allowed_databases: tuple[str, ...] = ()
    _allowed_keys: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "_allowed_keys", frozenset(name.casefold() for name in self.allowed_databases)
        )

    @property
    def configured(self) -> bool:
        return self.config.configured

    def allows(self, database: str) -> bool:
        """Case-insensitive allow-list check."""

        return not self._allowed_keys or database.casefold() in self._allowed_keys


@dataclass(frozen=True, slots=True)
class CatalogObject:
    schema: str
    name: str
    type: str
    type_code: str
    created_at: datetime | None
    last_modified: datetime | None


class SqlCatalogPort(Protocol):
    """The four read-only SQL Server operations of Decision 2 and the allow-list check."""

    def is_allowed(self, database: str) -> bool:
        """Requirement 7 allow-list (case-insensitive); checked before any SQL Server call."""
        ...

    async def list_databases(self) -> list[str]:
        """Online databases inside the allow-list, ordered by name."""
        ...

    async def list_objects(
        self, database: str, *, query: str | None = None, from_date: date | None = None
    ) -> list[CatalogObject]:
        """User procedures, views and functions ordered by schema, name and type code."""
        ...

    async def fetch_definition(
        self, database: str, schema: str, name: str, type_code: str
    ) -> str | None:
        """OBJECT_DEFINITION of one object; None when it is missing or not readable."""
        ...

    async def fetch_object_metadata(self, database: str, schema: str, name: str) -> str:
        """Dependency and column summary of one object; empty when nothing was found."""
        ...


class SqlConnectionProbe(Protocol):
    """Connection test: login to master with candidate values that are not saved."""

    async def probe(self, connection: EffectiveSqlConnection) -> Sequence[str]:
        """Online databases inside the candidate's allow-list, or a raised SqlServerError."""
        ...
