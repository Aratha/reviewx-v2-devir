"""Start-up refusal of unsafe integration settings and environment-dependent routes.

sql-review/PRDs/002-sql-server-connection Requirement 1 and 5 (Decision 5, 6, 10) and
006-llm-connection Requirement 1, 2 and 13 (Acceptance 1).
"""

import os
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import UnsafeIntegrationSettings, create_application
from app.services.startup_checks import integration_setting_errors

pytestmark = pytest.mark.unit

_KEPT_VARIABLES = {"DWHCODEREVIEW_JWT_PRIVATE_KEY", "DWHCODEREVIEW_DATABASE_URL"}
NONPROD_OK: dict[str, Any] = {
    "environment": "staging",
    "mssql_server": "sql-dwh.corp.example.test",
    "mssql_user": "dwh_okuyucu",
    "mssql_password": "yalniz-test-parolasi",
    "mssql_allowed_databases": "DWH_Sales,DWH_Risk",
    "mssql_encrypt": True,
    "mssql_trust_server_certificate": False,
    "llm_chat_api": "openai",
    "llm_base_url": "https://llm.corp.example.test/inference/model/v1",
    "llm_model": "/data/models--Test",
}


@pytest.fixture(autouse=True)
def _defaults_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("DWHCODEREVIEW_") and name not in _KEPT_VARIABLES:
            monkeypatch.delenv(name)


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_complete_nonprod_settings_start() -> None:
    assert integration_setting_errors(_settings(**NONPROD_OK)) == []


def test_empty_local_settings_start_unconfigured() -> None:
    assert integration_setting_errors(_settings(environment="development")) == []


@pytest.mark.parametrize(
    ("change", "setting"),
    [
        ({"mssql_server": ""}, "DWHCODEREVIEW_MSSQL_SERVER"),
        ({"mssql_user": ""}, "DWHCODEREVIEW_MSSQL_USER"),
        ({"mssql_password": ""}, "DWHCODEREVIEW_MSSQL_PASSWORD"),
        ({"mssql_allowed_databases": ""}, "DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES"),
        ({"mssql_allowed_databases": "DWH_Sales,MASTER"}, "DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES"),
        ({"mssql_allowed_databases": "tempdb"}, "DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES"),
        ({"mssql_encrypt": False}, "DWHCODEREVIEW_MSSQL_ENCRYPT"),
        ({"mssql_trust_server_certificate": True}, "DWHCODEREVIEW_MSSQL_TRUST_SERVER_CERTIFICATE"),
        ({"llm_base_url": ""}, "DWHCODEREVIEW_LLM_BASE_URL"),
        ({"llm_base_url": "http://llm.corp.example.test/v1"}, "DWHCODEREVIEW_LLM_BASE_URL"),
        ({"llm_chat_url": "http://llm.corp.example.test/chat"}, "DWHCODEREVIEW_LLM_CHAT_URL"),
        ({"llm_model": " "}, "DWHCODEREVIEW_LLM_MODEL"),
        ({"environment": "unknown-value", "mssql_encrypt": False}, "DWHCODEREVIEW_MSSQL_ENCRYPT"),
    ],
)
def test_unsafe_nonprod_settings_stop_start_up(change: dict[str, Any], setting: str) -> None:
    errors = integration_setting_errors(_settings(**{**NONPROD_OK, **change}))
    assert setting in errors


@pytest.mark.parametrize(
    ("change", "setting"),
    [
        ({"mssql_server": "sql;Encrypt=no"}, "DWHCODEREVIEW_MSSQL_SERVER"),
        ({"mssql_user": "okuyucu\n"}, "DWHCODEREVIEW_MSSQL_USER"),
        ({"llm_base_url": "http://user:pass@llm.local/v1"}, "DWHCODEREVIEW_LLM_BASE_URL"),
        ({"llm_chat_url": "https://llm.local/v1#x"}, "DWHCODEREVIEW_LLM_CHAT_URL"),
        ({"llm_base_url": "ftp://llm.local/v1"}, "DWHCODEREVIEW_LLM_BASE_URL"),
        ({"llm_ca_bundle": "/nonexistent/ca.pem"}, "DWHCODEREVIEW_LLM_CA_BUNDLE"),
    ],
)
def test_malformed_values_stop_start_up_in_every_environment(
    change: dict[str, Any], setting: str
) -> None:
    assert setting in integration_setting_errors(_settings(environment="development", **change))
    assert setting in integration_setting_errors(_settings(**{**NONPROD_OK, **change}))


def test_http_is_accepted_only_locally() -> None:
    url = {"llm_base_url": "http://127.0.0.1:1234/v1"}
    assert integration_setting_errors(_settings(environment="development", **url)) == []


async def test_the_process_refuses_to_start_with_unsafe_settings() -> None:
    application = create_application(_settings(**{**NONPROD_OK, "mssql_encrypt": False}))
    with pytest.raises(UnsafeIntegrationSettings) as raised:
        async with application.router.lifespan_context(application):
            pass  # pragma: no cover - start-up must not reach the body
    assert "DWHCODEREVIEW_MSSQL_ENCRYPT" in str(raised.value)
    assert NONPROD_OK["mssql_password"] not in str(raised.value)


def _routes(application: Any) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in application.openapi()["paths"].items()
        for method in operations
    }


def test_write_and_test_endpoints_exist_only_locally() -> None:
    prefix = _settings().api_prefix
    local_only = {
        ("PUT", f"{prefix}/sql-connection"),
        ("POST", f"{prefix}/sql-connection/test"),
        ("PUT", f"{prefix}/llm-connection"),
    }
    readable = {
        ("GET", f"{prefix}/sql-connection"),
        ("GET", f"{prefix}/llm-connection"),
        ("GET", f"{prefix}/llm-calls"),
    }
    local = _routes(create_application(_settings(environment="development")))
    for environment in ("staging", "unknown-value"):
        nonprod = _routes(
            create_application(_settings(**{**NONPROD_OK, "environment": environment}))
        )
        assert not local_only & nonprod
        assert readable <= nonprod
    assert local_only | readable <= local


async def test_nonprod_write_requests_find_no_route() -> None:
    settings = _settings(**NONPROD_OK)
    application = create_application(settings)
    headers = {settings.tenant_header: "00000000-0000-4000-8000-000000000010"}
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://t") as client:
        for method, path in (
            ("PUT", "/sql-connection"),
            ("POST", "/sql-connection/test"),
            ("PUT", "/llm-connection"),
        ):
            response = await client.request(
                method, f"{settings.api_prefix}{path}", json={}, headers=headers
            )
            assert response.status_code == 404, path
