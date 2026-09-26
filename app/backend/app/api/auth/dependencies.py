"""FastAPI authentication, permission, super-admin and same-origin guards."""

from typing import Annotated

from fastapi import Depends, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.middleware.tenant_context import get_request_context_dependency

bearer_scheme = HTTPBearer(auto_error=False)


def _not_authenticated() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "not_authenticated",
        "Oturum açmanız gerekiyor.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> ApplicationError:
    return ApplicationError(status.HTTP_403_FORBIDDEN, "forbidden", "Bu işlem için yetkiniz yok.")


async def get_current_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    context: Annotated[RequestContext, Depends(get_request_context_dependency)],
) -> RequestContext:
    # Only a verified bearer token authenticates; X-API-Key or X-Admin-Key carry no meaning.
    if credentials is None or not context.is_authenticated:
        raise _not_authenticated()
    return context


CurrentContext = Annotated[RequestContext, Depends(get_current_context)]


class PermissionChecker:
    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(self, context: CurrentContext) -> None:
        if not context.has_permission(self.permission):
            raise _forbidden()


def require_permission(permission: str) -> PermissionChecker:
    return PermissionChecker(permission)


class RoleChecker:
    """Allow a caller holding any of the roles; the super admin passes every role check."""

    def __init__(self, roles: tuple[str, ...]) -> None:
        self.roles = roles

    async def __call__(self, context: CurrentContext) -> None:
        if not any(context.has_role(role) for role in self.roles):
            raise _forbidden()


def require_any_role(*roles: str) -> RoleChecker:
    return RoleChecker(roles)


class SuperAdminChecker:
    async def __call__(self, context: CurrentContext) -> None:
        if not context.is_super_admin:
            raise _forbidden()


def require_super_admin() -> SuperAdminChecker:
    return SuperAdminChecker()


async def require_same_origin(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """CSRF guard for the cookie-authenticated session endpoints (Origin must match exactly)."""

    if request.headers.get("origin") != settings.public_origin:
        raise ApplicationError(
            status.HTTP_403_FORBIDDEN,
            "origin_not_allowed",
            "İstek uygulama adresinden gelmediği için reddedildi.",
        )
