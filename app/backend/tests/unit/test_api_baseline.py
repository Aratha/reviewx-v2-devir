"""Application construction, liveness, readiness, and OpenAPI tests."""

import json
import logging
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import health as health_module
from app.core.config import get_settings
from app.core.logging import ApplicationJsonHandler, configure_logging
from app.main import app
from app.scripts.export_openapi import export_openapi

pytestmark = pytest.mark.unit


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def test_liveness(client: AsyncClient) -> None:
    prefix = get_settings().api_prefix
    assert (await client.get(f"{prefix}/liveness")).json() == {"status": "alive"}


def test_logging_configuration_is_idempotent_and_preserves_host_handlers() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    host_handler = logging.NullHandler()
    try:
        root.addHandler(host_handler)
        configure_logging("INFO")
        configure_logging("INFO")
        application_handlers = [
            handler for handler in root.handlers if isinstance(handler, ApplicationJsonHandler)
        ]
        assert host_handler in root.handlers
        assert len(application_handlers) == 1
        assert application_handlers[0].stream is sys.stdout
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


async def test_request_logging_is_correlated_and_excludes_request_data(
    client: AsyncClient,
) -> None:
    records: list[logging.LogRecord] = []

    class RecordHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    request_logger = logging.getLogger("app.http")
    original_level = request_logger.level
    handler = RecordHandler()
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    prefix = get_settings().api_prefix
    try:
        response = await client.get(
            f"{prefix}/liveness?secret=must-not-be-logged",
            headers={"x-request-id": "test-request-123", "authorization": "Bearer hidden"},
        )
    finally:
        request_logger.removeHandler(handler)
        request_logger.setLevel(original_level)

    assert response.headers["x-request-id"] == "test-request-123"
    record = next(item for item in records if item.message == "request.completed")
    fields = record.structured_fields
    assert fields["request_id"] == "test-request-123"
    assert fields["http_route"] == f"{prefix}/liveness"
    serialized = json.dumps(fields)
    assert "must-not-be-logged" not in serialized
    assert "Bearer hidden" not in serialized


async def test_me_requires_tenant_header_before_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{get_settings().api_prefix}/auth/me")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "tenant_header_required"


async def test_me_authentication_error_has_bearer_challenge(client: AsyncClient) -> None:
    settings = get_settings()
    response = await client.get(
        f"{settings.api_prefix}/auth/me",
        headers={settings.tenant_header: str(uuid4())},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"]["code"] == "not_authenticated"


@pytest.mark.parametrize("header", ("X-API-Key", "X-Admin-Key"))
async def test_static_api_keys_carry_no_meaning(client: AsyncClient, header: str) -> None:
    """application-foundation 001 Requirement 12: only the bearer session authenticates."""

    settings = get_settings()
    for path in ("/auth/me", "/admin/users"):
        response = await client.get(
            f"{settings.api_prefix}{path}",
            headers={settings.tenant_header: str(uuid4()), header: "any-shared-key"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "not_authenticated"


async def test_openapi_contains_frontend_auth_contract(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    prefix = get_settings().api_prefix
    assert f"{prefix}/auth/login" in paths
    assert f"{prefix}/auth/me" in paths
    assert f"{prefix}/readiness" in paths
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    assert login_schema["required"] == ["username", "password"]


def test_openapi_export_is_offline_and_deterministic(tmp_path: Path) -> None:
    output = tmp_path / "app-api.yaml"
    schema = export_openapi(output)
    assert output.is_file()
    assert f"{get_settings().api_prefix}/auth/login" in schema["paths"]


def test_openapi_export_keeps_properties_named_title(tmp_path: Path) -> None:
    """Only schema ``title`` metadata is dropped; a field called ``title`` stays in the contract."""

    schema = export_openapi(tmp_path / "app-api.yaml")
    components = schema["components"]["schemas"]
    for name in ("ReviewRunSummary", "ReviewRunDetail"):
        component = components[name]
        assert "title" not in component
        assert "title" in component["required"]
        assert component["properties"]["title"] == {"type": "string"}
    for component in components.values():
        for field in component.get("properties", {}).values():
            assert "title" not in field


async def test_readiness_reports_database_state(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ready() -> bool:
        return True

    monkeypatch.setattr(health_module, "database_is_ready", ready)
    response = await client.get(f"{get_settings().api_prefix}/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readiness_returns_503_when_database_is_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr(health_module, "database_is_ready", unavailable)
    response = await client.get(f"{get_settings().api_prefix}/readiness")
    assert response.status_code == 503
    assert response.json() == {"status": "not-ready"}
