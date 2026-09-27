"""SQL Server and LLM connection settings endpoints through the real HTTP application.

sql-review/PRDs/002-sql-server-connection Requirement 3, 4 and 5 and 006-llm-connection
Requirement 13 (Acceptance 1): roles, the nonprod read view, the local write and test
endpoints, and passwords or keys never appearing in responses or logs.
"""

import logging
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.integrations import (
    get_llm_connection_store,
    get_llm_resolver,
    get_sql_catalog,
    get_sql_connection_store,
)
from app.core.config import get_settings
from app.domain.models.llm_call import LlmChatApi
from app.domain.sql_server import SqlServerConnectionConfig
from app.main import app, create_application
from app.services.llm_connection_service import LlmConnectionConfig, LlmConnectionStore
from app.services.sql_connection_service import SqlConnectionStore
from tests.integration.conftest import CLIENT_ADDRESS, AuthHarness, RoleSessions

pytestmark = pytest.mark.integration

SQL_PASSWORD = f"sql-parola-{uuid4().hex}"
LLM_KEY = f"llm-anahtar-{uuid4().hex}"


class FakeProbe:
    def __init__(self) -> None:
        self.calls: list[SqlServerConnectionConfig] = []

    async def probe(self, config: SqlServerConnectionConfig) -> list[str]:
        self.calls.append(config)
        return [f"DWH_{n}" for n in range(10)]


@dataclass
class Integrations:
    sql_store: SqlConnectionStore
    llm_store: LlmConnectionStore
    probe: FakeProbe


@pytest.fixture
def integrations(auth: AuthHarness) -> Iterator[Integrations]:
    state = Integrations(
        SqlConnectionStore(
            SqlServerConnectionConfig(
                server="sql-dev.corp.example.test", user="gelistirici", password=SQL_PASSWORD
            )
        ),
        LlmConnectionStore(
            LlmConnectionConfig(
                chat_api=LlmChatApi.OPENAI,
                base_url="https://llm.corp.example.test/v1",
                model="test-model",
                api_key=LLM_KEY,
            )
        ),
        FakeProbe(),
    )

    async def resolver(host: str, port: int) -> list[str]:
        return {"llm.corp.example.test": ["10.14.3.99"]}.get(host, ["93.184.216.34"])

    overrides = {
        get_sql_connection_store: lambda: state.sql_store,
        get_sql_catalog: lambda: state.probe,
        get_llm_connection_store: lambda: state.llm_store,
        get_llm_resolver: lambda: resolver,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield state
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


@pytest.fixture
async def local_client(auth: AuthHarness, integrations: Integrations) -> AsyncIterator[AsyncClient]:
    """The same application built for the local environment, sharing the test overrides."""

    local_settings = auth.settings.model_copy(update={"environment": "development"})
    local_app = create_application(local_settings)
    local_app.dependency_overrides.update(app.dependency_overrides)
    local_app.dependency_overrides[get_settings] = lambda: local_settings
    transport = ASGITransport(app=local_app, client=(CLIENT_ADDRESS, 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def captured_logs() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Handler(level=logging.DEBUG)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


def _rendered(records: list[logging.LogRecord]) -> str:
    return repr([(r.getMessage(), getattr(r, "structured_fields", None), r.args) for r in records])


async def test_settings_endpoints_require_the_rule_manager(
    auth: AuthHarness, role_sessions: RoleSessions, integrations: Integrations
) -> None:
    reviewer = await role_sessions.reviewer()
    tenant_only = {auth.settings.tenant_header: reviewer.headers[auth.settings.tenant_header]}
    for path in ("/sql-connection", "/llm-connection", "/llm-calls"):
        anonymous = await auth.client.get(f"{auth.prefix}{path}", headers=tenant_only)
        forbidden = await auth.client.get(f"{auth.prefix}{path}", headers=reviewer.headers)
        assert anonymous.status_code == 401, path
        assert forbidden.status_code == 403, path
        assert forbidden.json()["detail"]["code"] == "forbidden"


async def test_nonprod_shows_only_the_state_and_has_no_write_endpoints(
    auth: AuthHarness, role_sessions: RoleSessions, integrations: Integrations
) -> None:
    manager = await role_sessions.rule_manager()

    sql = await auth.client.get(f"{auth.prefix}/sql-connection", headers=manager.headers)
    llm = await auth.client.get(f"{auth.prefix}/llm-connection", headers=manager.headers)
    writes = [
        await auth.client.put(
            f"{auth.prefix}/sql-connection", json={"port": 1}, headers=manager.headers
        ),
        await auth.client.post(
            f"{auth.prefix}/sql-connection/test", json={}, headers=manager.headers
        ),
        await auth.client.put(
            f"{auth.prefix}/llm-connection", json={"model": "x"}, headers=manager.headers
        ),
    ]

    assert sql.json() == {"environment": "nonprod", "editable": False, "configured": True}
    assert llm.json() == {
        "environment": "nonprod",
        "editable": False,
        "chat_api": "openai",
        "model": "test-model",
    }
    assert [response.status_code for response in writes] == [404, 404, 404]
    assert SQL_PASSWORD not in sql.text and LLM_KEY not in llm.text
    assert integrations.sql_store.current().port == 1433


async def test_local_sql_settings_change_in_process_and_hide_the_password(
    role_sessions: RoleSessions,
    integrations: Integrations,
    local_client: AsyncClient,
    captured_logs: list[logging.LogRecord],
) -> None:
    manager = await role_sessions.rule_manager()
    prefix = get_settings().api_prefix
    new_password = f"yeni-{uuid4().hex}"

    shown = await local_client.get(f"{prefix}/sql-connection", headers=manager.headers)
    changed = await local_client.put(
        f"{prefix}/sql-connection",
        json={"port": 14330, "password": new_password},
        headers=manager.headers,
    )
    other_server = await local_client.post(
        f"{prefix}/sql-connection/test",
        json={"server": "baska.corp.example.test"},
        headers=manager.headers,
    )
    same_server = await local_client.post(
        f"{prefix}/sql-connection/test", json={}, headers=manager.headers
    )
    free_string = await local_client.put(
        f"{prefix}/sql-connection",
        json={"connection_string": "Server=x;Trusted_Connection=yes"},
        headers=manager.headers,
    )

    assert shown.json()["password_set"] is True and "password" not in shown.json()
    assert changed.status_code == 200, changed.text
    assert changed.json()["port"] == 14330 and changed.json()["password_set"] is True
    assert integrations.sql_store.current().password == new_password
    assert other_server.json()["code"] == "password_required"
    assert same_server.json()["ok"] is True
    assert same_server.json()["databases"] == [f"DWH_{n}" for n in range(10)]
    assert [call.password for call in integrations.probe.calls] == [new_password]
    assert free_string.status_code == 422
    assert free_string.json()["detail"]["code"] == "invalid_request"
    for response in (shown, changed, other_server, same_server, free_string):
        assert SQL_PASSWORD not in response.text and new_password not in response.text
    rendered = _rendered(captured_logs)
    assert new_password not in rendered and SQL_PASSWORD not in rendered
    assert any(r.getMessage() == "sql_connection.updated" for r in captured_logs)


async def test_local_writes_still_require_the_rule_manager(
    role_sessions: RoleSessions, integrations: Integrations, local_client: AsyncClient
) -> None:
    reviewer = await role_sessions.reviewer()
    prefix = get_settings().api_prefix
    for method, path in (
        ("PUT", "/sql-connection"),
        ("POST", "/sql-connection/test"),
        ("PUT", "/llm-connection"),
    ):
        response = await local_client.request(
            method, f"{prefix}{path}", json={}, headers=reviewer.headers
        )
        assert response.status_code == 403, path
    assert integrations.probe.calls == []


async def test_local_llm_settings_change_in_process_and_hide_the_key(
    role_sessions: RoleSessions,
    integrations: Integrations,
    local_client: AsyncClient,
    captured_logs: list[logging.LogRecord],
) -> None:
    manager = await role_sessions.rule_manager()
    prefix = get_settings().api_prefix

    shown = await local_client.get(f"{prefix}/llm-connection", headers=manager.headers)
    changed = await local_client.put(
        f"{prefix}/llm-connection", json={"model": "yeni-model"}, headers=manager.headers
    )
    public = await local_client.put(
        f"{prefix}/llm-connection",
        json={"base_url": "https://public.example.com/v1"},
        headers=manager.headers,
    )
    credentials = await local_client.put(
        f"{prefix}/llm-connection",
        json={"chat_url": "https://u:p@llm.corp.example.test/v1"},
        headers=manager.headers,
    )

    assert shown.json()["api_key_set"] is True
    assert shown.json()["resolved_chat_url"] == "https://llm.corp.example.test/v1/chat/completions"
    assert changed.status_code == 200 and changed.json()["model"] == "yeni-model"
    assert integrations.llm_store.current().model == "yeni-model"
    assert public.status_code == 422
    assert public.json()["detail"]["code"] == "network_policy_denied"
    assert credentials.status_code == 422
    assert credentials.json()["detail"]["code"] == "llm_url_invalid"
    assert integrations.llm_store.current().base_url == "https://llm.corp.example.test/v1"
    for response in (shown, changed, public, credentials):
        assert LLM_KEY not in response.text
    assert LLM_KEY not in _rendered(captured_logs)
