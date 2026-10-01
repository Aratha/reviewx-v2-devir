"""SQL Server connection settings: modes, in-process and saved changes, validation and the test.

sql-review/PRDs/002-sql-server-connection Requirement 3, 4, 5, 8 and 10 (Acceptance 1). The saved
(nonprod) mode runs here against an in-memory stand-in of the PostgreSQL storage; the real storage
is covered by tests/integration/test_sql_connection_storage.py.
"""

import base64
import hashlib
import logging
import os
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.domain.sql_server import (
    EffectiveSqlConnection,
    SqlServerConnectionConfig,
    SqlServerError,
    SqlServerErrorClass,
)
from app.schemas.sql_connection.contracts import SqlConnectionChange
from app.services.sql_connection_service import (
    InvalidAllowedDatabases,
    SqlConnectionMode,
    SqlConnectionService,
    SqlConnectionStore,
    StoredSqlConnection,
    initial_sql_connection,
    normalize_allowed_databases,
    sql_connection_mode,
)

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parents[2]
STORED_PASSWORD = f"kayitli-{uuid4().hex}"
STORED = EffectiveSqlConnection(
    SqlServerConnectionConfig(
        server="sql-dev.corp.example.test", port=1433, user="gelistirici", password=STORED_PASSWORD
    ),
    ("DWH_B", "DWH_A"),
)
CONTEXT = RequestContext(subject=uuid4(), roles=frozenset({"kural-yoneticisi"}))
SUPER_ADMIN = RequestContext(subject=uuid4(), is_super_admin=True)
KEY = base64.b64encode(os.urandom(32)).decode()
_KEPT_VARIABLES = {"DWHCODEREVIEW_JWT_PRIVATE_KEY", "DWHCODEREVIEW_DATABASE_URL"}


@pytest.fixture(autouse=True)
def _defaults_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("DWHCODEREVIEW_") and name not in _KEPT_VARIABLES:
            monkeypatch.delenv(name)


class FakeProbe:
    def __init__(self, databases: Sequence[str] = (), error: SqlServerError | None = None) -> None:
        self.databases = list(databases)
        self.error = error
        self.calls: list[EffectiveSqlConnection] = []

    async def probe(self, connection: EffectiveSqlConnection) -> list[str]:
        self.calls.append(connection)
        if self.error is not None:
            raise self.error
        return [name for name in self.databases if connection.allows(name)]


class InMemoryStorage(StoredSqlConnection):
    """The storage contract without PostgreSQL: one saved value, copied into the store."""

    def __init__(self, store: SqlConnectionStore, saved: EffectiveSqlConnection) -> None:
        self._store = store
        self.saved = saved
        self.refreshes = 0

    async def refresh(self) -> None:
        self.refreshes += 1
        self._store.replace(self.saved)

    async def save(
        self,
        context: RequestContext,
        change: Callable[[EffectiveSqlConnection], EffectiveSqlConnection],
    ) -> tuple[EffectiveSqlConnection, EffectiveSqlConnection]:
        before = self.saved
        self.saved = change(before)
        self._store.replace(self.saved)
        return before, self.saved


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


def _stored_service(
    probe: FakeProbe | None = None, saved: EffectiveSqlConnection = STORED
) -> SqlConnectionService:
    store = SqlConnectionStore(EffectiveSqlConnection())
    return SqlConnectionService(
        settings=_settings("staging", settings_encryption_key=KEY),
        store=store,
        probe=probe or FakeProbe(),
        storage=InMemoryStorage(store, saved),
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


def _events(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
    return [
        r.structured_fields  # type: ignore[attr-defined]
        for r in records
        if r.getMessage() == "sql_connection.updated"
    ]


def _env_files_digest() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in BACKEND.glob(".env*")
        if path.is_file()
    }


# --- modes -------------------------------------------------------------------------------------

_DEPLOYED = {"mssql_server": "sql.corp.example.test", "mssql_user": "u", "mssql_password": "p"}


def test_the_mode_follows_the_environment_the_deployment_and_the_key() -> None:
    assert sql_connection_mode(_settings()) is SqlConnectionMode.LOCAL
    assert sql_connection_mode(_settings(settings_encryption_key=KEY)) is SqlConnectionMode.LOCAL
    # Deployment values take priority, with or without the key.
    for extra in ({}, {"settings_encryption_key": KEY}):
        assert (
            sql_connection_mode(_settings("staging", **_DEPLOYED, **extra))
            is SqlConnectionMode.DEPLOYMENT
        )
    # Without the key nothing can be stored, so the interface stays closed.
    assert sql_connection_mode(_settings("staging")) is SqlConnectionMode.DEPLOYMENT
    for missing in _DEPLOYED:
        incomplete = {**_DEPLOYED, missing: "", "settings_encryption_key": KEY}
        assert sql_connection_mode(_settings("staging", **incomplete)) is SqlConnectionMode.STORED
    assert (
        sql_connection_mode(_settings("unknown-value", settings_encryption_key=KEY))
        is SqlConnectionMode.STORED
    )


def test_initial_values_come_from_the_typed_settings() -> None:
    initial = initial_sql_connection(
        _settings(
            mssql_server=" sql ",
            mssql_user="u",
            mssql_password="p",
            mssql_port=14330,
            mssql_allowed_databases=" DWH_B , DWH_A,,",
        )
    )
    config = initial.config
    assert (config.server, config.user, config.password, config.port) == ("sql", "u", "p", 14330)
    assert config.trust_server_certificate is False and config.encrypt is True
    assert initial.allowed_databases == ("DWH_B", "DWH_A")


def test_the_stored_mode_starts_empty_whatever_the_partial_deployment_values_are() -> None:
    settings = _settings("staging", mssql_user="u", mssql_password="p", settings_encryption_key=KEY)
    assert initial_sql_connection(settings) == EffectiveSqlConnection()


# --- local -------------------------------------------------------------------------------------


async def test_local_view_shows_values_but_never_the_password() -> None:
    view = (await _service().view(CONTEXT)).model_dump(exclude_none=True)
    assert view == {
        "environment": "local",
        "editable": True,
        "configured": True,
        "managed_by": "local_process",
        "server": STORED.config.server,
        "port": 1433,
        "user": STORED.config.user,
        "encrypt": True,
        "trust_server_certificate": False,
        "password_set": True,
        "allowed_databases": ["DWH_A", "DWH_B"],
    }
    assert STORED_PASSWORD not in repr(view)


async def test_update_keeps_a_missing_password_and_removes_an_empty_one(
    records: list[logging.LogRecord],
) -> None:
    service = _service()
    before_files = _env_files_digest()
    before_environment = dict(os.environ)

    kept = await service.update(
        CONTEXT, SqlConnectionChange(server="sql-2.corp.example.test", port=1500)
    )
    assert kept.password_set is True
    assert service.store.current().config.password == STORED_PASSWORD
    assert service.store.current().config.server == "sql-2.corp.example.test"
    assert service.store.current().allowed_databases == STORED.allowed_databases

    new_password = f"yeni-{uuid4().hex}"
    await service.update(CONTEXT, SqlConnectionChange(password=new_password))
    assert service.store.current().config.password == new_password

    removed = await service.update(CONTEXT, SqlConnectionChange(password=""))
    assert removed.password_set is False and removed.configured is False

    # Decision 3: the change lives in this process only.
    assert _env_files_digest() == before_files
    assert dict(os.environ) == before_environment
    events = _events(records)
    assert [event["changed_fields"] for event in events] == ["port,server", "password", "password"]
    assert all(event["user_public_id"] == str(CONTEXT.subject) for event in events)
    assert all(event["managed_by"] == "local_process" for event in events)
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
async def test_control_characters_and_separators_are_rejected(change: SqlConnectionChange) -> None:
    service = _service()
    with pytest.raises(ApplicationError) as raised:
        await service.update(CONTEXT, change)
    assert (raised.value.status_code, raised.value.code) == (422, "sql_connection_invalid")
    assert service.store.current() == STORED


async def test_the_local_allow_list_is_not_editable_from_the_interface() -> None:
    service = _service()
    with pytest.raises(ApplicationError) as raised:
        await service.update(CONTEXT, SqlConnectionChange(allowed_databases=["DWH_C"]))
    assert (raised.value.status_code, raised.value.code) == (422, "sql_setting_fixed")
    assert service.store.current() == STORED


async def test_a_new_target_without_a_password_never_receives_the_stored_one() -> None:
    probe = FakeProbe(["DWH_A"])
    for service in (_service(probe), _stored_service(probe)):
        context = CONTEXT if service.mode is SqlConnectionMode.LOCAL else SUPER_ADMIN
        for change in (
            SqlConnectionChange(server="other.corp.example.test"),
            SqlConnectionChange(port=1434),
            SqlConnectionChange(user="baska"),
        ):
            result = await service.test(context, change)
            assert (result.ok, result.code, result.databases) == (False, "password_required", [])
    assert probe.calls == []


async def test_the_same_target_is_tested_with_the_stored_password_without_saving() -> None:
    probe = FakeProbe(["DWH_A", "DWH_B", "Scratch"])
    service = _service(probe)

    result = await service.test(CONTEXT, SqlConnectionChange(encrypt=True))

    assert (result.ok, result.code, result.databases) == (True, None, ["DWH_A", "DWH_B"])
    assert probe.calls[0].config.password == STORED_PASSWORD
    assert service.store.current() == STORED


async def test_a_new_target_with_its_own_password_is_tested() -> None:
    probe = FakeProbe(["DWH_A"])
    service = _service(probe)
    result = await service.test(
        CONTEXT, SqlConnectionChange(server="other.corp.example.test", password="x")
    )
    assert result.ok and probe.calls[0].config.server == "other.corp.example.test"
    assert service.store.current() == STORED


async def test_connection_failures_become_fixed_classes() -> None:
    probe = FakeProbe(error=SqlServerError(SqlServerErrorClass.TLS_FAILED, "08001"))
    result = await _service(probe).test(CONTEXT, SqlConnectionChange())
    assert result.model_dump() == {
        "ok": False,
        "code": "sql_tls_failed",
        "message": "SQL Server ile güvenli bağlantı kurulamadı.",
        "databases": [],
    }


async def test_a_test_without_server_or_user_is_invalid() -> None:
    service = SqlConnectionService(
        settings=_settings(),
        store=SqlConnectionStore(EffectiveSqlConnection()),
        probe=FakeProbe(),
    )
    with pytest.raises(ApplicationError) as raised:
        await service.test(CONTEXT, SqlConnectionChange(password="x"))
    assert raised.value.code == "sql_connection_invalid"


# --- nonprod managed by the deployment ---------------------------------------------------------


@pytest.mark.parametrize("context", [CONTEXT, SUPER_ADMIN])
@pytest.mark.parametrize("values", [_DEPLOYED, {}, {**_DEPLOYED, "settings_encryption_key": KEY}])
async def test_a_deployment_managed_nonprod_is_closed_to_everyone(
    context: RequestContext, values: dict[str, Any]
) -> None:
    # Requirement 5: a complete deployment connection, or a missing key, leaves nothing editable.
    service = _service(environment="staging", **values)
    assert (await service.view(context)).model_dump(exclude_none=True) == {
        "environment": "nonprod",
        "editable": False,
        "configured": True,
        "managed_by": "deployment",
    }
    with pytest.raises(ApplicationError) as updated:
        await service.update(context, SqlConnectionChange(port=1))
    with pytest.raises(ApplicationError) as tested:
        await service.test(context, SqlConnectionChange())
    assert (updated.value.status_code, tested.value.status_code) == (404, 404)
    assert service.store.current() == STORED


# --- nonprod saved by the super admin ----------------------------------------------------------


async def test_the_super_admin_sees_the_saved_values_with_fixed_encryption() -> None:
    service = _stored_service()
    view = (await service.view(SUPER_ADMIN)).model_dump(exclude_none=True)
    assert view == {
        "environment": "nonprod",
        "editable": True,
        "configured": True,
        "managed_by": "super_admin",
        "server": STORED.config.server,
        "port": 1433,
        "user": STORED.config.user,
        "encrypt": True,
        "trust_server_certificate": False,
        "password_set": True,
        "allowed_databases": ["DWH_A", "DWH_B"],
    }
    assert STORED_PASSWORD not in repr(view)
    assert isinstance(service.storage, InMemoryStorage) and service.storage.refreshes == 1


async def test_other_roles_see_only_the_state_and_cannot_save_or_test() -> None:
    probe = FakeProbe(["DWH_A"])
    service = _stored_service(probe)
    assert (await service.view(CONTEXT)).model_dump(exclude_none=True) == {
        "environment": "nonprod",
        "editable": False,
        "configured": True,
        "managed_by": "super_admin",
    }
    with pytest.raises(ApplicationError) as updated:
        await service.update(CONTEXT, SqlConnectionChange(port=1))
    with pytest.raises(ApplicationError) as tested:
        await service.test(CONTEXT, SqlConnectionChange())
    assert (updated.value.status_code, tested.value.status_code) == (403, 403)
    assert probe.calls == []
    assert isinstance(service.storage, InMemoryStorage) and service.storage.saved == STORED


async def test_the_super_admin_saves_the_connection_and_the_allow_list(
    records: list[logging.LogRecord],
) -> None:
    service = _stored_service(saved=EffectiveSqlConnection())
    password = f"yeni-{uuid4().hex}"

    saved = await service.update(
        SUPER_ADMIN,
        SqlConnectionChange(
            server="sql-dwh.corp.example.test",
            port=1444,
            user="dwh_okuyucu",
            password=password,
            encrypt=True,
            trust_server_certificate=False,
            allowed_databases=[" DWH_Sales ", "dwh_sales", "DWH_Risk", ""],
        ),
    )

    assert saved.model_dump(exclude_none=True) == {
        "environment": "nonprod",
        "editable": True,
        "configured": True,
        "managed_by": "super_admin",
        "server": "sql-dwh.corp.example.test",
        "port": 1444,
        "user": "dwh_okuyucu",
        "encrypt": True,
        "trust_server_certificate": False,
        "password_set": True,
        "allowed_databases": ["DWH_Risk", "DWH_Sales"],
    }
    current = service.store.current()
    assert current.config.password == password and current.allows("dwh_risk")
    assert not current.allows("Scratch")
    (event,) = _events(records)
    assert event["changed_fields"] == "allowed_databases,password,port,server,user"
    assert event["managed_by"] == "super_admin"
    assert event["user_public_id"] == str(SUPER_ADMIN.subject)
    rendered = repr([r.__dict__ for r in records])
    for secret in (password, "sql-dwh.corp.example.test", "dwh_okuyucu", "DWH_Sales"):
        assert secret not in rendered

    kept = await service.update(SUPER_ADMIN, SqlConnectionChange(port=1433))
    assert kept.password_set is True and service.store.current().config.password == password
    removed = await service.update(SUPER_ADMIN, SqlConnectionChange(password=""))
    assert removed.password_set is False and removed.configured is False


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (SqlConnectionChange(allowed_databases=[]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["  "]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["DWH", "MASTER"]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["tempdb"]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["Model "]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["msdb"]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(allowed_databases=["DW\nH"]), "sql_allowed_databases_invalid"),
        (SqlConnectionChange(server=""), "sql_connection_invalid"),
        (SqlConnectionChange(user="  "), "sql_connection_invalid"),
        (SqlConnectionChange(server="sql;Encrypt=no"), "sql_connection_invalid"),
        (SqlConnectionChange(user="okuyucu\n"), "sql_connection_invalid"),
        (SqlConnectionChange(encrypt=False), "sql_setting_fixed"),
        (SqlConnectionChange(trust_server_certificate=True), "sql_setting_fixed"),
    ],
)
async def test_a_save_keeps_the_nonprod_guarantees(change: SqlConnectionChange, code: str) -> None:
    # Decision 5 and 6: business databases only, encryption on, certificate verified.
    service = _stored_service()
    with pytest.raises(ApplicationError) as raised:
        await service.update(SUPER_ADMIN, change)
    assert (raised.value.status_code, raised.value.code) == (422, code)
    assert isinstance(service.storage, InMemoryStorage) and service.storage.saved == STORED


async def test_a_first_save_needs_server_user_and_allow_list() -> None:
    service = _stored_service(saved=EffectiveSqlConnection())
    for change, code in (
        (SqlConnectionChange(user="u", allowed_databases=["DWH"]), "sql_connection_invalid"),
        (SqlConnectionChange(server="sql", allowed_databases=["DWH"]), "sql_connection_invalid"),
        (SqlConnectionChange(server="sql", user="u"), "sql_allowed_databases_invalid"),
    ):
        with pytest.raises(ApplicationError) as raised:
            await service.update(SUPER_ADMIN, change)
        assert raised.value.code == code


async def test_a_nonprod_test_lists_what_can_be_allowed_and_never_system_databases() -> None:
    probe = FakeProbe(["DWH_A", "DWH_B", "Scratch", "master", "TempDB"])
    service = _stored_service(probe, saved=EffectiveSqlConnection())
    form = {"server": "sql.corp.example.test", "user": "u", "password": "p"}

    before_choice = await service.test(SUPER_ADMIN, SqlConnectionChange(**form))
    chosen = await service.test(
        SUPER_ADMIN, SqlConnectionChange(**form, allowed_databases=["dwh_b"])
    )

    assert before_choice.databases == ["DWH_A", "DWH_B", "Scratch"]
    assert chosen.databases == ["DWH_B"]
    assert all(
        call.config.encrypt and not call.config.trust_server_certificate for call in probe.calls
    )
    assert isinstance(service.storage, InMemoryStorage)
    assert service.storage.saved == EffectiveSqlConnection()
    with pytest.raises(ApplicationError) as raised:
        await service.test(SUPER_ADMIN, SqlConnectionChange(**form, allowed_databases=["msdb"]))
    assert raised.value.code == "sql_allowed_databases_invalid"


def test_allowed_database_names_are_trimmed_and_unique_without_case() -> None:
    assert normalize_allowed_databases([" DWH ", "dwh", "", "Risk"], required=True) == (
        "DWH",
        "Risk",
    )
    assert normalize_allowed_databases([], required=False) == ()
    for names in ([], ["  "], ["master"], ["DWH", "MSDB"], ["a\tb"]):
        with pytest.raises(InvalidAllowedDatabases):
            normalize_allowed_databases(names, required=True)
