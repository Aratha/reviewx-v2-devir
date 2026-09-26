"""Login and current-user endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import CurrentContext
from app.core.login_throttle import login_throttle
from app.db.session import get_db
from app.schemas.auth.request import LoginRequest
from app.schemas.auth.response import AuthenticatedUser, LoginResponse
from app.services.auth_service import AuthService

router = APIRouter()


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AuthService:
    return AuthService(session)


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> LoginResponse:
    """Authenticate by username or email and issue a signed access token."""

    key = (body.username.strip().casefold(), request.client.host if request.client else "")
    retry_after = login_throttle.retry_after(key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        response = await service.authenticate(body.username, body.password.get_secret_value())
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_throttle.record_failure(key)
        raise
    login_throttle.reset(key)
    return response


@router.get("/me", response_model=AuthenticatedUser)
async def me(
    context: CurrentContext,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthenticatedUser:
    """Return the active user and tenant after authoritative token validation."""

    return await service.current_user(context)
