"""Access logs name the full route template, including every router prefix."""

import logging
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.middleware.request_logging import RequestLoggingMiddleware

pytestmark = pytest.mark.unit


@pytest.fixture
def routes() -> Iterator[list[str]]:
    recorded: list[str] = []

    class RouteHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage() == "request.completed":
                recorded.append(record.structured_fields["http_route"])

    request_logger = logging.getLogger("app.http")
    original_level = request_logger.level
    handler = RouteHandler()
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    try:
        yield recorded
    finally:
        request_logger.removeHandler(handler)
        request_logger.setLevel(original_level)


def _application() -> FastAPI:
    items = APIRouter()

    @items.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @items.post("/login")
    async def login() -> dict[str, str]:
        return {}

    group = APIRouter(prefix="/group")
    group.include_router(items)
    api = APIRouter(prefix="/api/v1")
    api.include_router(group)
    # The same router under a second prefix keeps its own template.
    api.include_router(items, prefix="/other")
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(api)

    @application.get("/direct")
    async def direct() -> dict[str, str]:
        return {}

    return application


async def _request(application: FastAPI, method: str, path: str) -> int:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.request(method, path)).status_code


async def test_nested_router_prefixes_are_part_of_the_route(routes: list[str]) -> None:
    assert await _request(_application(), "POST", "/api/v1/group/login") == 200

    assert routes == ["/api/v1/group/login"]


async def test_path_parameters_stay_templated(routes: list[str]) -> None:
    application = _application()
    assert await _request(application, "GET", "/api/v1/group/items/41") == 200
    assert await _request(application, "GET", "/api/v1/other/items/42") == 200

    assert routes == ["/api/v1/group/items/{item_id}", "/api/v1/other/items/{item_id}"]


async def test_wrong_method_and_unknown_paths_keep_a_bounded_route(routes: list[str]) -> None:
    application = _application()
    assert await _request(application, "GET", "/api/v1/group/login") == 405
    assert await _request(application, "GET", "/direct") == 200
    assert await _request(application, "GET", "/api/v1/group/unknown-secret-value") == 404

    assert routes == ["/api/v1/group/login", "/direct", "unmatched"]


async def test_application_auth_routes_carry_the_auth_prefix(routes: list[str]) -> None:
    prefix = get_settings().api_prefix
    assert await _request(app, "POST", f"{prefix}/auth/login") == 422

    assert routes == [f"{prefix}/auth/login"]
