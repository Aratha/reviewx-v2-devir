"""Process-wide wiring of the SQL connection objects from the typed settings.

sql-review/PRDs/002-sql-server-connection Requirement 5 and 11 (Acceptance 1): which mode builds a
PostgreSQL-backed storage, and that the catalog adapter reads the store of the same process.
"""

import base64
import os
from collections.abc import Iterator
from typing import Any

import pytest

from app.api import integrations
from app.core.config import Settings
from app.domain.sql_server import SqlServerConnectionConfig
from app.services.sql_connection_service import StoredSqlConnection

pytestmark = pytest.mark.unit

_KEPT_VARIABLES = {"DWHCODEREVIEW_JWT_PRIVATE_KEY", "DWHCODEREVIEW_DATABASE_URL"}
_KEY = base64.b64encode(os.urandom(32)).decode()
_DEPLOYED = {
    "mssql_server": "sql.corp.example.test",
    "mssql_user": "okuyucu",
    "mssql_password": "yalniz-test-parolasi",
}
_CACHED = (
    integrations.get_sql_connection_store,
    integrations.get_sql_connection_storage,
    integrations.get_sql_catalog_adapter,
)


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for name in list(os.environ):
        if name.startswith("DWHCODEREVIEW_") and name not in _KEPT_VARIABLES:
            monkeypatch.delenv(name)

    def clear() -> None:
        if integrations.get_sql_catalog_adapter.cache_info().currsize:
            integrations.get_sql_catalog_adapter().close()
        for cached in _CACHED:
            cached.cache_clear()

    def use(**values: Any) -> None:
        settings = Settings(_env_file=None, **values)
        monkeypatch.setattr(integrations, "get_settings", lambda: settings)

    clear()
    try:
        yield use
    finally:
        clear()


@pytest.mark.parametrize(
    "values",
    [
        {"environment": "development", "settings_encryption_key": _KEY},
        {"environment": "staging", **_DEPLOYED, "settings_encryption_key": _KEY},
        {"environment": "staging"},
    ],
    ids=["local", "deployment-connection", "no-key"],
)
def test_nothing_is_stored_locally_or_when_the_deployment_manages_the_connection(
    wire: Any, values: dict[str, Any]
) -> None:
    wire(**values)
    assert integrations.get_sql_connection_storage() is None


def test_a_deployment_connection_is_in_force_from_the_start(wire: Any) -> None:
    wire(environment="staging", **_DEPLOYED)
    current = integrations.get_sql_connection_store().current()
    assert current.configured and current.server == "sql.corp.example.test"
    catalog = integrations.get_sql_catalog_adapter()
    assert catalog.is_allowed("AnyDatabase") and not catalog.is_allowed("master")


def test_a_stored_nonprod_reads_through_the_store_of_the_same_process(wire: Any) -> None:
    wire(environment="staging", mssql_user="okuyucu", settings_encryption_key=_KEY)

    storage = integrations.get_sql_connection_storage()
    store = integrations.get_sql_connection_store()
    catalog = integrations.get_sql_catalog_adapter()

    assert isinstance(storage, StoredSqlConnection)
    assert store.current() == SqlServerConnectionConfig()
    # What the storage puts into the store is what the catalog uses on its next call.
    assert storage._store is store
    saved = SqlServerConnectionConfig(server="sql", user="u", password="p")
    store.replace(saved)
    assert catalog._configured() is saved
