"""Stateless login and current-user application service."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import RequestContext
from app.core.security import create_access_token, verify_password
from app.domain.models.role import SUPER_ADMIN_ROLE
from app.infrastructure.repositories.user_repository import (
    AuthorizationSnapshot,
    UserRepository,
)
from app.schemas.auth.response import AuthenticatedUser, LoginResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = UserRepository(session)

    async def authenticate(self, username: str, password: str) -> LoginResponse:
        user = await self.repository.get_for_login(username)
        password_hash = user.password_hash if user is not None else None
        if not verify_password(password, password_hash) or user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            authorization = await self.repository.authorization_for(user)
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User tenant is unavailable",
            ) from exc

        is_super_admin = SUPER_ADMIN_ROLE in authorization.roles
        token = create_access_token(
            subject=UUID(user.public_id),
            username=user.username,
            tenant_id=_tenant_id(authorization),
            roles=list(authorization.roles),
            permissions=list(authorization.permissions),
            is_super_admin=is_super_admin,
        )
        return LoginResponse(
            access_token=token,
            user=self._response_user(UUID(user.public_id), user.username, authorization),
        )

    async def current_user(self, context: RequestContext) -> AuthenticatedUser:
        if context.subject is None or context.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
            )

        user = await self.repository.get_active_by_public_id(context.subject)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User is unavailable",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            authorization = await self.repository.authorization_for(user)
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User tenant is unavailable",
            ) from exc
        return AuthenticatedUser(
            public_id=UUID(user.public_id),
            username=user.username,
            tenant_id=context.tenant_id,
            roles=list(authorization.roles),
            permissions=list(authorization.permissions),
            is_super_admin=SUPER_ADMIN_ROLE in authorization.roles,
        )

    @staticmethod
    def _response_user(
        public_id: UUID,
        username: str,
        authorization: AuthorizationSnapshot,
    ) -> AuthenticatedUser:
        tenant_id = _tenant_id(authorization)
        return AuthenticatedUser(
            public_id=public_id,
            username=username,
            tenant_id=tenant_id,
            roles=list(authorization.roles),
            permissions=list(authorization.permissions),
            is_super_admin=SUPER_ADMIN_ROLE in authorization.roles,
        )


def _tenant_id(snapshot: AuthorizationSnapshot) -> UUID:
    return UUID(snapshot.tenant_public_id)
