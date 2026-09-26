"""SQL Server connection settings (sql-review/PRDs/002-sql-server-connection API contract).

``router`` is registered in every environment; ``local_router`` only in the local environment,
so in nonprod the write and test endpoints do not exist (Requirement 5).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth.dependencies import CurrentContext, require_any_role
from app.api.integrations import get_sql_catalog, get_sql_connection_store
from app.api.route_classes import MethodScopedRoute
from app.core.config import Settings, get_settings
from app.domain.models.role import ROLE_RULE_MANAGER
from app.domain.sql_server import SqlConnectionProbe
from app.schemas.sql_connection.contracts import (
    SqlConnectionChange,
    SqlConnectionTestResult,
    SqlConnectionView,
)
from app.services.sql_connection_service import SqlConnectionService, SqlConnectionStore

_RESPONSES: dict[int | str, dict[str, str]] = {
    401: {"description": "Oturum yok"},
    403: {"description": "Kural yöneticisi değil"},
}


def get_sql_connection_service(
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[SqlConnectionStore, Depends(get_sql_connection_store)],
    catalog: Annotated[SqlConnectionProbe, Depends(get_sql_catalog)],
) -> SqlConnectionService:
    return SqlConnectionService(settings=settings, store=store, probe=catalog)


Service = Annotated[SqlConnectionService, Depends(get_sql_connection_service)]


def _router() -> APIRouter:
    return APIRouter(
        prefix="/sql-connection",
        tags=["sql-connection"],
        route_class=MethodScopedRoute,
        dependencies=[Depends(require_any_role(ROLE_RULE_MANAGER))],
        responses=_RESPONSES,
    )


router = _router()
local_router = _router()


@router.get("", response_model=SqlConnectionView, response_model_exclude_none=True)
async def read_sql_connection(service: Service) -> SqlConnectionView:
    """Environment and state; server, user and options only in the local environment."""

    return service.view()


@local_router.put(
    "",
    response_model=SqlConnectionView,
    response_model_exclude_none=True,
    responses={422: {"description": "Geçersiz sunucu veya kullanıcı adı"}},
)
async def update_sql_connection(
    body: SqlConnectionChange, context: CurrentContext, service: Service
) -> SqlConnectionView:
    """Change the values of this process only; nothing is written to a file (local only)."""

    return service.update(context, body)


@local_router.post(
    "/test",
    response_model=SqlConnectionTestResult,
    responses={422: {"description": "Geçersiz sunucu veya kullanıcı adı"}},
)
async def test_sql_connection(
    body: SqlConnectionChange, service: Service
) -> SqlConnectionTestResult:
    """Log in to master with the form values without saving them (local only)."""

    return await service.test(body)
