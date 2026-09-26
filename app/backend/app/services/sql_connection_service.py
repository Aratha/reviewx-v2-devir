"""SQL Server connection settings of this process (sql-review/PRDs/002-sql-server-connection).

Values start from the typed settings. In the local environment a rule manager may change them;
the change lives only in this process and is never written to a file or the process environment
(Decision 3 and 8). Nonprod exposes only a read view without server or user. Responses carry
``password_set``, never the password.
"""

import logging
import threading
from dataclasses import replace

from fastapi import status

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.sql_server import (
    SqlConnectionProbe,
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerNotConfigured,
)
from app.infrastructure.sql_server.connection_string import (
    InvalidConnectionValue,
    validate_server,
    validate_user,
)
from app.schemas.sql_connection.contracts import (
    SqlConnectionChange,
    SqlConnectionTestResult,
    SqlConnectionView,
)

logger = logging.getLogger("app.sql_server")


def initial_sql_connection(settings: Settings) -> SqlServerConnectionConfig:
    password = settings.mssql_password
    return SqlServerConnectionConfig(
        server=settings.mssql_server.strip(),
        port=settings.mssql_port,
        user=settings.mssql_user.strip(),
        password=password.get_secret_value() if password is not None else None,
        encrypt=settings.mssql_encrypt,
        trust_server_certificate=settings.mssql_trust_server_certificate,
    )


class SqlConnectionStore:
    """The effective connection values; the catalog adapter reads them on every call."""

    def __init__(self, initial: SqlServerConnectionConfig) -> None:
        self._config = initial
        self._lock = threading.Lock()

    def current(self) -> SqlServerConnectionConfig:
        return self._config

    def replace(self, config: SqlServerConnectionConfig) -> None:
        with self._lock:
            self._config = config


def _invalid() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "sql_connection_invalid",
        "Sunucu veya kullanıcı adı geçersiz.",
    )


def _merge(
    current: SqlServerConnectionConfig, change: SqlConnectionChange
) -> SqlServerConnectionConfig:
    try:
        server = validate_server(change.server) if change.server is not None else current.server
        user = validate_user(change.user) if change.user is not None else current.user
    except InvalidConnectionValue:
        raise _invalid() from None
    password = current.password
    if change.password is not None:
        password = change.password or None
    return SqlServerConnectionConfig(
        server=server,
        port=change.port if change.port is not None else current.port,
        user=user,
        password=password,
        encrypt=change.encrypt if change.encrypt is not None else current.encrypt,
        trust_server_certificate=(
            change.trust_server_certificate
            if change.trust_server_certificate is not None
            else current.trust_server_certificate
        ),
    )


class SqlConnectionService:
    def __init__(
        self, *, settings: Settings, store: SqlConnectionStore, probe: SqlConnectionProbe
    ) -> None:
        self.settings = settings
        self.store = store
        self.probe = probe

    @property
    def editable(self) -> bool:
        return self.settings.runtime_environment == "local"

    def view(self) -> SqlConnectionView:
        config = self.store.current()
        if not self.editable:
            return SqlConnectionView(
                environment="nonprod", editable=False, configured=config.configured
            )
        return SqlConnectionView(
            environment="local",
            editable=True,
            configured=config.configured,
            server=config.server,
            port=config.port,
            user=config.user,
            encrypt=config.encrypt,
            trust_server_certificate=config.trust_server_certificate,
            password_set=config.password is not None,
            allowed_databases=sorted(
                name.strip()
                for name in self.settings.mssql_allowed_databases.split(",")
                if name.strip()
            ),
        )

    def update(self, context: RequestContext, change: SqlConnectionChange) -> SqlConnectionView:
        self._require_local()
        current = self.store.current()
        updated = _merge(current, change)
        changed = sorted(
            name
            for name in (
                "server",
                "port",
                "user",
                "password",
                "encrypt",
                "trust_server_certificate",
            )
            if getattr(current, name) != getattr(updated, name)
        )
        self.store.replace(updated)
        log_event(
            logger,
            "sql_connection.updated",
            changed_fields=",".join(changed),
            user_public_id=str(context.subject) if context.subject else None,
        )
        return self.view()

    async def test(self, change: SqlConnectionChange) -> SqlConnectionTestResult:
        self._require_local()
        current = self.store.current()
        candidate = _merge(current, change)
        if not candidate.server or not candidate.user:
            raise _invalid()
        same_target = (candidate.server, candidate.port, candidate.user) == (
            current.server,
            current.port,
            current.user,
        )
        if not same_target and not change.password:
            # Requirement 4: the stored password is never sent to another server or user.
            candidate = replace(candidate, password=None)
        if candidate.password is None:
            return SqlConnectionTestResult(
                ok=False,
                code="password_required",
                message="Bağlantıyı test etmek için parolayı girin.",
                databases=[],
            )
        try:
            databases = list(await self.probe.probe(candidate))
        except SqlServerError as error:
            return SqlConnectionTestResult(
                ok=False, code=error.error_class.value, message=error.message, databases=[]
            )
        except SqlServerNotConfigured:
            raise _invalid() from None
        return SqlConnectionTestResult(
            ok=True, code=None, message="Bağlantı başarılı.", databases=databases
        )

    def _require_local(self) -> None:
        # The routes exist only locally; this keeps the service closed if it is reused.
        if not self.editable:
            raise ApplicationError(status.HTTP_404_NOT_FOUND, "not_found", "Bulunamadı.")
