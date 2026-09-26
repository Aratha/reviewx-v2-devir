"""FastAPI authentication, permission, and super-admin guards."""

from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.request_context import RequestContext
from app.middleware.tenant_context import get_request_context_dependency

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
    context: Annotated[RequestContext, Depends(get_request_context_dependency)],
) -> RequestContext:
    if credentials is None or not context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return context


CurrentContext = Annotated[RequestContext, Depends(get_current_context)]


class PermissionChecker:
    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def __call__(self, context: CurrentContext) -> None:
        if not context.has_permission(self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.permission}",
            )


def require_permission(permission: str) -> PermissionChecker:
    return PermissionChecker(permission)


class SuperAdminChecker:
    async def __call__(self, context: CurrentContext) -> None:
        if not context.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super-admin access required",
            )


def require_super_admin() -> SuperAdminChecker:
    return SuperAdminChecker()
