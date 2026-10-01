"""SQL Server connection settings (sql-review/PRDs/002-sql-server-connection).

Three modes follow from the typed settings (Requirement 5):

- ``local``: values start from the settings and a rule manager may change them; the change lives
  only in this process and is never written to a file or the process environment (Decision 3, 8).
- ``deployment``: nonprod whose deployment supplies server, user and password, or which has no
  settings encryption key. Nothing is editable and only the state is shown.
- ``stored``: nonprod without a complete deployment connection. The super admin saves the
  connection in PostgreSQL with the password encrypted (Requirement 10); every replica reads the
  row again before it uses the connection, so a save needs no restart (Requirement 11).

Responses carry ``password_set``, never the password; logs carry field names, never values.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import replace
from enum import StrEnum

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.core.secret_cipher import SecretCipher, SecretUnreadable
from app.domain.models.role import SUPER_ADMIN_ROLE
from app.domain.models.sql_connection import SqlConnectionSetting
from app.domain.models.tenant import PLATFORM_TENANT_CODE
from app.domain.sql_server import (
    SqlConnectionProbe,
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerNotConfigured,
)
from app.infrastructure.repositories.sql_connection_setting_repository import (
    SqlConnectionSettingRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.sql_server.connection_string import (
    InvalidConnectionValue,
    validate_server,
    validate_user,
)
from app.schemas.sql_connection.contracts import (
    EnvironmentValue,
    ManagedByValue,
    SqlConnectionChange,
    SqlConnectionTestResult,
    SqlConnectionView,
)
from app.services.request_scope import acting_user

logger = logging.getLogger("app.sql_server")

_CHANGE_FIELDS = ("server", "port", "user", "password", "encrypt", "trust_server_certificate")


class SqlConnectionMode(StrEnum):
    LOCAL = "local"
    DEPLOYMENT = "deployment"
    STORED = "stored"


def sql_connection_mode(settings: Settings) -> SqlConnectionMode:
    if settings.runtime_environment == "local":
        return SqlConnectionMode.LOCAL
    # Deployment values take priority; without the key nothing can be stored, so it stays closed.
    if settings.mssql_connection_complete or settings.settings_encryption_key is None:
        return SqlConnectionMode.DEPLOYMENT
    return SqlConnectionMode.STORED


def initial_sql_connection(settings: Settings) -> SqlServerConnectionConfig:
    """The connection at process start; the stored mode is empty until its first read."""

    if sql_connection_mode(settings) is SqlConnectionMode.STORED:
        return SqlServerConnectionConfig()
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
    """The effective connection of this process; the catalog adapter reads it on every call."""

    def __init__(self, initial: SqlServerConnectionConfig) -> None:
        self._connection = initial
        self._lock = threading.Lock()

    def current(self) -> SqlServerConnectionConfig:
        return self._connection

    def replace(self, connection: SqlServerConnectionConfig) -> None:
        with self._lock:
            self._connection = connection


def _invalid() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "sql_connection_invalid",
        "Sunucu veya kullanıcı adı geçersiz.",
    )


def _setting_fixed() -> ApplicationError:
    return ApplicationError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "sql_setting_fixed",
        "Bu ayar bu ortamda değiştirilemez.",
    )


def _forbidden() -> ApplicationError:
    return ApplicationError(status.HTTP_403_FORBIDDEN, "forbidden", "Bu işlem için yetkiniz yok.")


def _not_found() -> ApplicationError:
    return ApplicationError(status.HTTP_404_NOT_FOUND, "not_found", "Bulunamadı.")


def _password_context(tenant_public_id: str) -> str:
    return f"sql-connection-password:{tenant_public_id}"


class StoredSqlConnection:
    """The nonprod connection kept in PostgreSQL for the single platform tenant.

    ``refresh`` copies the saved row into the process store; the API calls it before every use of
    the connection, so a save made through another replica is picked up on the next request. A
    password that cannot be opened with the configured key (the key changed) leaves the connection
    not configured until the super admin saves it again.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: SecretCipher,
        store: SqlConnectionStore,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._store = store
        self._reported: tuple[str, str | None] | None = None

    async def refresh(self) -> None:
        try:
            async with self._session_factory() as session:
                found = await SqlConnectionSettingRepository(session).get_by_tenant_code(
                    PLATFORM_TENANT_CODE
                )
                loaded = SqlServerConnectionConfig() if found is None else self._read(*found)
        except Exception as error:  # noqa: BLE001 - the last known connection stays in force
            log_event(logger, "sql_connection.refresh_failed", error_type=type(error).__name__)
            return
        self._store.replace(loaded)

    async def save(
        self,
        context: RequestContext,
        change: Callable[[SqlServerConnectionConfig], SqlServerConnectionConfig],
    ) -> tuple[SqlServerConnectionConfig, SqlServerConnectionConfig]:
        """Apply ``change`` to the saved row in one transaction; returns before and after."""

        async with self._session_factory() as session:
            users = UserRepository(session)
            actor = await acting_user(users, context)
            # rules/21: the permission is read again, so a token issued before the role was
            # removed cannot save the connection.
            if SUPER_ADMIN_ROLE not in await users.role_codes(actor):
                raise _forbidden()
            tenant = await users.get_tenant_by_code(PLATFORM_TENANT_CODE)
            if tenant is None:
                raise ApplicationError(
                    status.HTTP_404_NOT_FOUND, "tenant_not_found", "Kiracı bulunamadı."
                )
            settings = SqlConnectionSettingRepository(session)
            row = await settings.lock(tenant.tenant_id)
            before = (
                SqlServerConnectionConfig() if row is None else self._read(row, tenant.public_id)
            )
            after = change(before)
            password = after.password
            ciphertext = (
                self._cipher.encrypt(password, context=_password_context(tenant.public_id))
                if password
                else None
            )
            try:
                if row is None:
                    await settings.add(
                        SqlConnectionSetting(
                            tenant_id=tenant.tenant_id,
                            server=after.server,
                            port=after.port,
                            user_name=after.user,
                            password_ciphertext=ciphertext,
                            trust_server_certificate=after.trust_server_certificate,
                            created_by=actor.user_id,
                            updated_by=actor.user_id,
                        )
                    )
                else:
                    row.server = after.server
                    row.port = after.port
                    row.user_name = after.user
                    row.password_ciphertext = ciphertext
                    row.trust_server_certificate = after.trust_server_certificate
                    row.updated_by = actor.user_id
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ApplicationError(
                    status.HTTP_409_CONFLICT,
                    "sql_connection_conflict",
                    "Bağlantı ayarı aynı anda başka biri tarafından kaydedildi; sayfayı yenileyip "
                    "yeniden deneyin.",
                ) from None
        self._store.replace(after)
        return before, after

    def _read(self, row: SqlConnectionSetting, tenant_public_id: str) -> SqlServerConnectionConfig:
        password: str | None = None
        problem: str | None = None
        if row.password_ciphertext is not None:
            try:
                password = self._cipher.decrypt(
                    row.password_ciphertext, context=_password_context(tenant_public_id)
                )
            except SecretUnreadable:
                problem = "password_unreadable"
        self._report(problem, row.password_ciphertext)
        return SqlServerConnectionConfig(
            server=row.server,
            port=row.port,
            user=row.user_name,
            password=password,
            encrypt=True,
            trust_server_certificate=row.trust_server_certificate,
        )

    def _report(self, problem: str | None, ciphertext: str | None) -> None:
        """One ``sql_connection.stored_unusable`` event per unusable saved value, not per read."""

        state = None if problem is None else (problem, ciphertext)
        if state is not None and state != self._reported:
            log_event(logger, "sql_connection.stored_unusable", reason=problem)
        self._reported = state


def _merge(
    current: SqlServerConnectionConfig, change: SqlConnectionChange, mode: SqlConnectionMode
) -> SqlServerConnectionConfig:
    if mode is SqlConnectionMode.STORED:
        # Decision 6: encryption is fixed outside local; only the certificate exception is a choice.
        if change.encrypt is False:
            raise _setting_fixed()
        encrypt = True
    else:
        encrypt = change.encrypt if change.encrypt is not None else current.encrypt
    trust = (
        change.trust_server_certificate
        if change.trust_server_certificate is not None
        else current.trust_server_certificate
    )
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
        encrypt=encrypt,
        trust_server_certificate=trust,
    )


def _changed_fields(before: SqlServerConnectionConfig, after: SqlServerConnectionConfig) -> str:
    return ",".join(
        sorted(name for name in _CHANGE_FIELDS if getattr(before, name) != getattr(after, name))
    )


class SqlConnectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        store: SqlConnectionStore,
        probe: SqlConnectionProbe,
        storage: StoredSqlConnection | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.probe = probe
        self.storage = storage

    @property
    def mode(self) -> SqlConnectionMode:
        if self.settings.runtime_environment == "local":
            return SqlConnectionMode.LOCAL
        return SqlConnectionMode.DEPLOYMENT if self.storage is None else SqlConnectionMode.STORED

    async def view(self, context: RequestContext) -> SqlConnectionView:
        if self.mode is SqlConnectionMode.STORED and self.storage is not None:
            await self.storage.refresh()
        return self._view(context, self.store.current())

    async def update(
        self, context: RequestContext, change: SqlConnectionChange
    ) -> SqlConnectionView:
        mode = self._require_editable(context)

        def apply(current: SqlServerConnectionConfig) -> SqlServerConnectionConfig:
            updated = _merge(current, change, mode)
            # A saved connection always names its server and account.
            if mode is SqlConnectionMode.STORED and not (updated.server and updated.user):
                raise _invalid()
            return updated

        if mode is SqlConnectionMode.STORED and self.storage is not None:
            before, after = await self.storage.save(context, apply)
        else:
            before = self.store.current()
            after = apply(before)
            self.store.replace(after)
        log_event(
            logger,
            "sql_connection.updated",
            changed_fields=_changed_fields(before, after),
            managed_by=self._managed_by(mode),
            trust_server_certificate=after.trust_server_certificate,
            user_public_id=str(context.subject) if context.subject else None,
        )
        return self._view(context, after)

    async def test(
        self, context: RequestContext, change: SqlConnectionChange
    ) -> SqlConnectionTestResult:
        mode = self._require_editable(context)
        if mode is SqlConnectionMode.STORED and self.storage is not None:
            await self.storage.refresh()
        current = self.store.current()
        candidate = _merge(current, change, mode)
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

    def _view(
        self, context: RequestContext, config: SqlServerConnectionConfig
    ) -> SqlConnectionView:
        mode = self.mode
        environment: EnvironmentValue = "local" if mode is SqlConnectionMode.LOCAL else "nonprod"
        managed_by = self._managed_by(mode)
        if not self._editable_by(context, mode):
            return SqlConnectionView(
                environment=environment,
                editable=False,
                configured=config.configured,
                managed_by=managed_by,
            )
        return SqlConnectionView(
            environment=environment,
            editable=True,
            configured=config.configured,
            managed_by=managed_by,
            server=config.server,
            port=config.port,
            user=config.user,
            encrypt=config.encrypt,
            trust_server_certificate=config.trust_server_certificate,
            password_set=config.password is not None,
        )

    @staticmethod
    def _managed_by(mode: SqlConnectionMode) -> ManagedByValue:
        if mode is SqlConnectionMode.LOCAL:
            return "local_process"
        return "deployment" if mode is SqlConnectionMode.DEPLOYMENT else "super_admin"

    @staticmethod
    def _editable_by(context: RequestContext, mode: SqlConnectionMode) -> bool:
        if mode is SqlConnectionMode.LOCAL:
            return True
        return mode is SqlConnectionMode.STORED and context.is_super_admin

    def _require_editable(self, context: RequestContext) -> SqlConnectionMode:
        # The routes carry the same guards; this keeps the service closed if it is reused.
        mode = self.mode
        if mode is SqlConnectionMode.DEPLOYMENT:
            raise _not_found()
        if not self._editable_by(context, mode):
            raise _forbidden()
        return mode
