"""Login, session refresh, logout and current-user service.

application-foundation/PRDs/001-directory-login Requirement 1-4, 6-9 and 11: local password
login for local accounts, login-only directory authentication for everyone else, a 15-minute
access token and a rotating server-side refresh session.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.login_throttle import LoginRateLimiter
from app.core.request_context import RequestContext
from app.core.security import (
    create_access_token,
    login_name_digest,
    new_refresh_token,
    refresh_token_digest,
    verify_password,
)
from app.core.telemetry import record_login_attempt
from app.domain.directory import (
    DirectoryAccount,
    DirectoryCredentialsRejected,
    DirectoryLoginPort,
    DirectoryUnavailable,
    InvalidDirectoryName,
    normalize_login_name,
    normalize_upn,
)
from app.domain.models.refresh_session import RefreshSession, RefreshSessionEndReason
from app.domain.models.role import DEFAULT_DIRECTORY_ROLE, application_role_of
from app.domain.models.tenant import PLATFORM_TENANT_CODE
from app.domain.models.user import AccountType, User
from app.infrastructure.repositories.refresh_session_repository import (
    RefreshSessionRepository,
)
from app.infrastructure.repositories.user_repository import (
    AuthorizationSnapshot,
    UserRepository,
)
from app.schemas.auth.response import (
    ApplicationRoleValue,
    AuthenticatedUser,
    LoginResponse,
)

logger = logging.getLogger("app.auth")

_BEARER = {"WWW-Authenticate": "Bearer"}


def invalid_credentials() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "invalid_credentials",
        "Kullanıcı adı veya parola hatalı.",
        headers=_BEARER,
    )


def user_inactive() -> ApplicationError:
    return ApplicationError(
        status.HTTP_403_FORBIDDEN,
        "user_inactive",
        "Hesabınız pasif durumda. Uygulama yöneticisine başvurun.",
    )


def identity_conflict() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "identity_conflict",
        "Bu hesap başka bir kullanıcı kaydıyla çakışıyor. Uygulama yöneticisine başvurun.",
    )


def session_expired() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "session_expired",
        "Oturumunuzun süresi doldu. Lütfen yeniden giriş yapın.",
    )


def session_revoked() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "session_revoked",
        "Oturumunuz kapatıldı. Lütfen yeniden giriş yapın.",
    )


class _LoginFailed(Exception):
    """An authentication failure with its log reason class and client-facing error."""

    def __init__(self, reason: str, error: ApplicationError) -> None:
        super().__init__(reason)
        self.reason = reason
        self.error = error


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A login or refresh result: the response body and the refresh cookie value."""

    response: LoginResponse
    refresh_token: str
    refresh_expires_at: datetime


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings,
        directory: DirectoryLoginPort | None,
        rate_limiter: LoginRateLimiter,
    ) -> None:
        self.session = session
        self.settings = settings
        self.directory = directory
        self.rate_limiter = rate_limiter
        self.users = UserRepository(session)
        self.sessions = RefreshSessionRepository(session)

    async def login(self, username: str, password: str, client_address: str) -> IssuedSession:
        name = normalize_login_name(username)
        name_digest = login_name_digest(name)
        blocked = self.rate_limiter.blocked(name, client_address)
        if blocked is not None:
            limit, retry_after = blocked
            log_event(logger, "auth.login.rate_limited", name_digest=name_digest, limit=limit)
            record_login_attempt("rate_limited")
            raise ApplicationError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                "Çok fazla hatalı giriş denemesi yapıldı. Lütfen daha sonra yeniden deneyin.",
                headers={"Retry-After": str(retry_after)},
            )
        try:
            user = await self._authenticate(name, username, password)
        except _LoginFailed as failure:
            self.rate_limiter.record_failure(name, client_address)
            log_event(logger, "auth.login.failed", reason=failure.reason, name_digest=name_digest)
            record_login_attempt(failure.reason)
            raise failure.error from None
        self.rate_limiter.record_success(name, client_address)
        now = datetime.now(UTC)
        await self.users.touch_login(user, now)
        await self.sessions.purge_ended(now)
        issued = await self._issue(user, family_id=uuid4(), absolute_expires_at=None, now=now)
        log_event(
            logger,
            "auth.login.succeeded",
            user_public_id=user.public_id,
            account_type=user.account_type,
        )
        record_login_attempt("succeeded")
        return issued

    async def refresh(self, refresh_token: str | None) -> IssuedSession:
        if not refresh_token:
            raise session_expired()
        record = await self.sessions.get_by_digest_for_update(refresh_token_digest(refresh_token))
        if record is None:
            raise session_expired()
        now = datetime.now(UTC)
        if record.revoked_at is not None:
            if record.revoke_reason == RefreshSessionEndReason.ROTATED.value:
                await self.sessions.end_family(
                    record.family_id,
                    reason=RefreshSessionEndReason.REUSE_DETECTED.value,
                    now=now,
                )
                user = await self.users.get_by_id(record.user_id)
                # The revocation must survive the 401 below, which rolls the request back.
                await self.session.commit()
                log_event(
                    logger,
                    "auth.session.reuse_detected",
                    user_public_id=user.public_id if user is not None else None,
                    session_family=str(record.family_id),
                )
            raise session_revoked()
        if now >= record.idle_expires_at or now >= record.absolute_expires_at:
            raise session_expired()
        user = await self.users.get_by_id(record.user_id)
        if user is None or user.is_deleted or not user.is_active:
            await self.sessions.end_family(
                record.family_id,
                reason=RefreshSessionEndReason.AUTHORIZATION_CHANGED.value,
                now=now,
            )
            await self.session.commit()
            raise session_revoked()
        record.revoked_at = now
        record.revoke_reason = RefreshSessionEndReason.ROTATED.value
        record.last_used_at = now
        record.updated_by = user.user_id
        return await self._issue(
            user,
            family_id=record.family_id,
            absolute_expires_at=record.absolute_expires_at,
            now=now,
        )

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        record = await self.sessions.get_by_digest_for_update(refresh_token_digest(refresh_token))
        if record is None:
            return
        await self.sessions.end_family(
            record.family_id, reason=RefreshSessionEndReason.LOGOUT.value, now=datetime.now(UTC)
        )
        user = await self.users.get_by_id(record.user_id)
        log_event(
            logger,
            "auth.logout",
            user_public_id=user.public_id if user is not None else None,
        )

    async def current_user(self, context: RequestContext) -> AuthenticatedUser:
        if context.subject is None or context.tenant_id is None:
            raise not_authenticated()
        user = await self.users.get_active_by_public_id(context.subject)
        if user is None:
            raise not_authenticated()
        authorization = await self._authorization(user)
        response = _authenticated_user(user, authorization)
        return response.model_copy(update={"tenant_id": context.tenant_id})

    async def _authenticate(self, name: str, raw_name: str, password: str) -> User:
        local = await self.users.get_local_by_username(name)
        if local is not None:
            return await self._authenticate_local(local, password)
        if self.directory is None:
            # Spend the same hash work as a real local account before refusing the name.
            verify_password(password, None)
            raise _LoginFailed("invalid_credentials", invalid_credentials())
        return await self._authenticate_directory(self.directory, raw_name, password)

    async def _authenticate_local(self, user: User, password: str) -> User:
        if not verify_password(password, user.password_hash):
            raise _LoginFailed("invalid_credentials", invalid_credentials())
        if self.settings.local_login_super_admin_only:
            authorization = await self._authorization(user)
            if not authorization.is_super_admin:
                raise _LoginFailed("invalid_credentials", invalid_credentials())
        if not user.is_active:
            raise _LoginFailed("user_inactive", user_inactive())
        return user

    async def _authenticate_directory(
        self, directory: DirectoryLoginPort, raw_name: str, password: str
    ) -> User:
        try:
            upn = normalize_upn(raw_name, self.settings.directory_upn_suffix)
        except InvalidDirectoryName:
            raise _LoginFailed("invalid_credentials", invalid_credentials()) from None
        if not password:
            # An empty password would be an anonymous LDAP bind; it never reaches the directory.
            raise _LoginFailed("invalid_credentials", invalid_credentials())
        try:
            account = await directory.authenticate(upn, password)
        except DirectoryCredentialsRejected as rejected:
            reason = "account_disabled" if rejected.account_disabled else "invalid_credentials"
            raise _LoginFailed(reason, invalid_credentials()) from None
        except DirectoryUnavailable as unavailable:
            log_event(logger, "auth.directory.unavailable", reason=unavailable.reason)
            record_login_attempt("directory_unavailable")
            raise ApplicationError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "directory_unavailable",
                "Kurum dizinine şu anda ulaşılamıyor. Lütfen daha sonra yeniden deneyin.",
            ) from None
        if not account.enabled:
            raise _LoginFailed("account_disabled", invalid_credentials())
        if not account.is_human:
            raise _LoginFailed("invalid_credentials", invalid_credentials())
        return await self._directory_user(account)

    async def _directory_user(self, account: DirectoryAccount) -> User:
        email = (account.mail or account.user_principal_name).strip().casefold()
        display_name = (account.display_name or account.user_principal_name).strip()[:255]
        user = await self.users.get_by_directory_guid(account.object_guid, for_update=True)
        if user is not None:
            if user.is_deleted or not user.is_active:
                raise _LoginFailed("user_inactive", user_inactive())
            if await self.users.find_identity_conflict(
                email=email, username=user.username, excluding_user_id=user.user_id
            ):
                raise _LoginFailed("identity_conflict", identity_conflict())
            user.display_name = display_name
            user.email = email
            user.updated_by = user.user_id
            return user
        if await self.users.find_identity_conflict(
            email=email, username=account.user_principal_name
        ):
            raise _LoginFailed("identity_conflict", identity_conflict())
        return await self._create_directory_user(account, email=email, display_name=display_name)

    async def _create_directory_user(
        self, account: DirectoryAccount, *, email: str, display_name: str
    ) -> User:
        tenant = await self.users.get_tenant_by_code(PLATFORM_TENANT_CODE)
        role = await self.users.get_role(DEFAULT_DIRECTORY_ROLE)
        if tenant is None or role is None:
            raise RuntimeError("the platform tenant and roles are missing; run the migrations")
        try:
            async with self.session.begin_nested():
                user = await self.users.add_user(
                    User(
                        home_tenant_id=tenant.tenant_id,
                        username=account.user_principal_name,
                        email=email,
                        display_name=display_name,
                        account_type=AccountType.DIRECTORY.value,
                        directory_object_guid=account.object_guid,
                    )
                )
                user.created_by = user.user_id
                user.updated_by = user.user_id
                await self.users.set_application_role(
                    user, role, actor_user_id=user.user_id, now=datetime.now(UTC)
                )
        except IntegrityError:
            # A concurrent first login or an identity collision the lookups did not see.
            raise _LoginFailed("identity_conflict", identity_conflict()) from None
        log_event(logger, "auth.user.created", user_public_id=user.public_id, role=role.code)
        return user

    async def _authorization(self, user: User) -> AuthorizationSnapshot:
        try:
            return await self.users.authorization_for(user)
        except LookupError:
            raise ApplicationError(
                status.HTTP_403_FORBIDDEN,
                "tenant_unavailable",
                "Hesabınızın bağlı olduğu kiracı kullanılamıyor.",
            ) from None

    async def _issue(
        self,
        user: User,
        *,
        family_id: UUID,
        absolute_expires_at: datetime | None,
        now: datetime,
    ) -> IssuedSession:
        authorization = await self._authorization(user)
        absolute = absolute_expires_at or now + timedelta(
            hours=self.settings.refresh_session_absolute_hours
        )
        idle = min(now + timedelta(minutes=self.settings.refresh_session_idle_minutes), absolute)
        token = new_refresh_token()
        tenant = await self.users.get_tenant_by_public_id(UUID(authorization.tenant_public_id))
        if tenant is None:  # pragma: no cover - authorization_for already verified the tenant
            raise RuntimeError("tenant disappeared during login")
        await self.sessions.add(
            RefreshSession(
                tenant_id=tenant.tenant_id,
                user_id=user.user_id,
                family_id=family_id,
                token_sha256=refresh_token_digest(token),
                idle_expires_at=idle,
                absolute_expires_at=absolute,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
        )
        access_token = create_access_token(
            subject=UUID(user.public_id),
            username=user.username,
            tenant_id=UUID(authorization.tenant_public_id),
            roles=list(authorization.roles),
            permissions=list(authorization.permissions),
            is_super_admin=authorization.is_super_admin,
        )
        return IssuedSession(
            response=LoginResponse(
                access_token=access_token,
                expires_in=self.settings.access_token_expire_minutes * 60,
                user=_authenticated_user(user, authorization),
            ),
            refresh_token=token,
            refresh_expires_at=absolute,
        )


def not_authenticated() -> ApplicationError:
    return ApplicationError(
        status.HTTP_401_UNAUTHORIZED,
        "not_authenticated",
        "Oturum açmanız gerekiyor.",
        headers=_BEARER,
    )


def _authenticated_user(user: User, authorization: AuthorizationSnapshot) -> AuthenticatedUser:
    return AuthenticatedUser(
        public_id=UUID(user.public_id),
        username=user.username,
        display_name=user.display_name,
        tenant_id=UUID(authorization.tenant_public_id),
        account_type=AccountType(user.account_type).value,
        role=cast(ApplicationRoleValue | None, application_role_of(authorization.roles)),
        roles=list(authorization.roles),
        permissions=list(authorization.permissions),
        is_super_admin=authorization.is_super_admin,
    )
