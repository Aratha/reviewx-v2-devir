"""Login, session refresh, logout and current-user endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext, require_same_origin
from app.core.client_address import resolve_client_address
from app.core.config import Settings, get_settings
from app.core.login_throttle import LoginRateLimiter, login_rate_limiter
from app.db.session import get_db
from app.domain.directory import DirectoryLoginPort
from app.infrastructure.directory.ldap_login_client import LdapsLoginClient
from app.schemas.auth.request import LoginRequest
from app.schemas.auth.response import AuthenticatedUser, LoginResponse
from app.services.auth_service import AuthService, IssuedSession

router = APIRouter()

REFRESH_COOKIE_NAME = "dwhcodereview_refresh"


def get_directory_login(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DirectoryLoginPort | None:
    if not settings.directory_enabled:
        return None
    return LdapsLoginClient(
        host=settings.directory_host,
        port=settings.directory_port,
        base_dn=settings.directory_base_dn,
        ca_bundle_path=settings.directory_ca_bundle_path,
        connect_timeout_seconds=settings.directory_connect_timeout_seconds,
        read_timeout_seconds=settings.directory_read_timeout_seconds,
        tls_legacy_compatibility=settings.directory_tls_legacy_compatibility,
    )


def get_login_rate_limiter() -> LoginRateLimiter:
    return login_rate_limiter


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    directory: Annotated[DirectoryLoginPort | None, Depends(get_directory_login)],
    rate_limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
) -> AuthService:
    return AuthService(session, settings=settings, directory=directory, rate_limiter=rate_limiter)


Service = Annotated[AuthService, Depends(get_auth_service)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)]


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/auth"


def _set_refresh_cookie(response: Response, issued: IssuedSession, settings: Settings) -> None:
    max_age = int((issued.refresh_expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        issued.refresh_token,
        max_age=max(max_age, 0),
        path=_cookie_path(settings),
        secure=True,
        httponly=True,
        samesite="strict",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    """Authenticate a local or directory account; issue an access token and a refresh cookie."""

    client_address = resolve_client_address(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        settings.trusted_proxy_networks,
    )
    issued = await service.login(body.username, body.password.get_secret_value(), client_address)
    _set_refresh_cookie(response, issued, settings)
    return issued.response


@router.post(
    "/refresh",
    response_model=LoginResponse,
    dependencies=[Depends(require_same_origin)],
)
async def refresh(
    response: Response,
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: RefreshCookie = None,
) -> LoginResponse:
    """Rotate the refresh cookie and return a new access token with the current role."""

    issued = await service.refresh(refresh_token)
    _set_refresh_cookie(response, issued, settings)
    return issued.response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
async def logout(
    service: Service,
    settings: Annotated[Settings, Depends(get_settings)],
    refresh_token: RefreshCookie = None,
) -> Response:
    """End the refresh session on the server and delete the cookie; works without a token."""

    await service.logout(refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=_cookie_path(settings),
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/me", response_model=AuthenticatedUser)
async def me(context: CurrentContext, service: Service) -> AuthenticatedUser:
    """Return the active user, display name, current role and account type."""

    return await service.current_user(context)
