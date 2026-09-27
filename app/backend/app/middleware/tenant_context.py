"""Verified JWT and active-tenant context without a database round trip."""

from contextvars import ContextVar, Token
from uuid import UUID

from fastapi import Request
from jwt import InvalidTokenError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.errors import error_body
from app.core.request_context import RequestContext
from app.core.security import TokenClaims, decode_access_token

_request_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def get_request_context() -> RequestContext | None:
    return _request_context.get()


async def get_request_context_dependency() -> RequestContext:
    context = get_request_context()
    if context is None:
        raise RuntimeError("request context middleware is not installed")
    return context


def tenant_is_allowed(claims: TokenClaims, active_tenant_id: UUID) -> bool:
    """Super admins may select any tenant; ordinary users stay in their home tenant."""

    return claims.is_super_admin or claims.tenant_id == active_tenant_id


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Require an active tenant and project trusted token claims into a context variable."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        settings = get_settings()
        self.tenant_header = settings.tenant_header
        api_prefix = settings.api_prefix
        self.excluded_paths = {
            "/docs",
            "/openapi.json",
            "/redoc",
            f"{api_prefix}/liveness",
            f"{api_prefix}/readiness",
            f"{api_prefix}/auth/login",
            # Cookie-authenticated; the session record, not a header, selects the tenant.
            f"{api_prefix}/auth/refresh",
            f"{api_prefix}/auth/logout",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.excluded_paths:
            return await self._with_context(RequestContext(), request, call_next)

        raw_tenant_id = request.headers.get(self.tenant_header)
        if raw_tenant_id is None:
            return JSONResponse(
                status_code=400,
                content=error_body("tenant_header_required", "Etkin kiracı başlığı gerekli."),
            )
        try:
            active_tenant_id = UUID(raw_tenant_id)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=error_body("tenant_invalid", "Etkin kiracı başlığı geçersiz."),
            )

        token = _bearer_token(request)
        if token is None:
            return await self._with_context(
                RequestContext(tenant_id=active_tenant_id), request, call_next
            )

        try:
            claims = decode_access_token(token)
        except InvalidTokenError:
            return await self._with_context(
                RequestContext(tenant_id=active_tenant_id, token_invalid=True), request, call_next
            )

        if not tenant_is_allowed(claims, active_tenant_id):
            return JSONResponse(
                status_code=403,
                content=error_body("tenant_forbidden", "Bu kiracıya erişim yetkiniz yok."),
            )

        context = RequestContext(
            tenant_id=active_tenant_id,
            subject=claims.sub,
            username=claims.username,
            home_tenant_id=claims.tenant_id,
            roles=frozenset(claims.roles),
            permissions=frozenset(claims.permissions),
            is_super_admin=claims.is_super_admin,
        )
        return await self._with_context(context, request, call_next)

    @staticmethod
    async def _with_context(
        context: RequestContext,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        reset_token: Token[RequestContext | None] = _request_context.set(context)
        try:
            return await call_next(request)
        finally:
            _request_context.reset(reset_token)


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
