"""The local super admin: one creation path for the operator command and the backend start.

application-foundation/PRDs/001-directory-login Requirement 14 and Decision 13. The operator
command ``python -m app.scripts.create_super_admin`` creates or resets the account. When the
start-up password is configured, the backend start creates the named account once and never
changes an account that already carries the name, so a password the administrator changed
survives every redeploy. Neither path logs, prints or traces the password or its hash.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import log_event
from app.core.security import hash_password
from app.domain.directory import InvalidDirectoryName, validate_local_account_name
from app.domain.models.role import SUPER_ADMIN_ROLE, UserRole
from app.domain.models.tenant import PLATFORM_TENANT_CODE, Tenant
from app.domain.models.user import User
from app.domain.models.user_change import UserChange, UserChangeField
from app.infrastructure.repositories.user_repository import UserRepository

logger = logging.getLogger("app.auth")

RejectionReason = Literal[
    "invalid_email", "invalid_username", "password_policy", "identity_conflict"
]
SessionFactory = Callable[[], AsyncSession]

BOOTSTRAP_FIRST_RETRY_SECONDS = 2.0
BOOTSTRAP_MAX_RETRY_SECONDS = 60.0


class SuperAdminRejected(ValueError):
    """The identity or password cannot become the super admin; the message carries no secret."""

    def __init__(self, reason: RejectionReason, message: str) -> None:
        super().__init__(message)
        self.reason: RejectionReason = reason


@dataclass(frozen=True, slots=True)
class SuperAdminResult:
    user_public_id: UUID
    tenant_public_id: UUID
    created: bool
    is_super_admin: bool


class BootstrapOutcome(StrEnum):
    """Result of the start-up creation; the ``outcome`` field of ``auth.super_admin.bootstrap``."""

    NOT_CONFIGURED = "not_configured"
    CREATED = "created"
    EXISTS = "exists"
    REJECTED = "rejected"


async def ensure_super_admin(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    tenant_code: str = PLATFORM_TENANT_CODE,
    tenant_name: str = "Platform",
    upn_suffix: str = "",
    reset_existing: bool = True,
) -> SuperAdminResult:
    """Create the super admin, or reset it when ``reset_existing``; owns and ends the transaction.

    Without ``reset_existing`` an account that already carries the name is left exactly as it is;
    its password, role and status are neither checked nor changed.
    """

    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise SuperAdminRejected("invalid_email", "email must be a valid address")
    try:
        # The super admin is a local account: its name never carries the directory UPN suffix.
        normalized_username = validate_local_account_name(username, upn_suffix)
    except InvalidDirectoryName as exc:
        raise SuperAdminRejected("invalid_username", str(exc)) from None

    users = UserRepository(session)
    # Every creation path serializes here, so backend replicas starting together see the account
    # the first one created instead of racing on the unique name.
    await users.lock_super_admin_creation()
    user = await users.get_by_username(normalized_username)
    if user is not None and not reset_existing:
        roles = await users.role_codes(user)
        tenant_public_id = await users.get_tenant_public_id(user.home_tenant_id)
        result = SuperAdminResult(
            user_public_id=UUID(user.public_id),
            tenant_public_id=UUID(tenant_public_id),
            created=False,
            is_super_admin=SUPER_ADMIN_ROLE in roles,
        )
        await session.rollback()
        return result

    try:
        password_hash = hash_password(
            password, context=(normalized_username, normalized_email.partition("@")[0])
        )
    except ValueError as exc:
        # The policy messages name the rule, never the password.
        raise SuperAdminRejected("password_policy", str(exc)) from None

    role = await users.get_role_record(SUPER_ADMIN_ROLE)
    if role is None:
        raise RuntimeError("super_admin role is missing; run Alembic migrations first")
    role.is_deleted = False
    role.deleted_at = None
    role.deleted_by = None

    tenant = await users.get_tenant_record(tenant_code)
    if tenant is None:
        tenant = await users.add_tenant(Tenant(code=tenant_code, name=tenant_name))
    else:
        tenant.name = tenant_name
        tenant.is_deleted = False
        tenant.deleted_at = None
        tenant.deleted_by = None
        tenant.is_active = True

    created = user is None
    if user is None:
        email_owner = await users.find_email_owner(normalized_email, include_deleted=False)
        if email_owner is not None:
            raise SuperAdminRejected(
                "identity_conflict", "email is already assigned to another user"
            )
        user = await users.add_user(
            User(
                home_tenant_id=tenant.tenant_id,
                username=normalized_username,
                email=normalized_email,
                display_name="Super Admin",
                password_hash=password_hash,
                is_active=True,
            )
        )
    else:
        email_owner = await users.find_email_owner(
            normalized_email, excluding_user_id=user.user_id, include_deleted=True
        )
        if email_owner is not None:
            raise SuperAdminRejected(
                "identity_conflict", "email is already assigned to another user"
            )
        user.home_tenant_id = tenant.tenant_id
        user.email = normalized_email
        user.password_hash = password_hash
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        user.deleted_by = None

    assignment = await users.get_role_assignment(
        user_id=user.user_id, role_id=role.role_id, tenant_id=tenant.tenant_id
    )
    if assignment is None:
        await users.add_role_assignment(
            UserRole(
                user_id=user.user_id,
                role_id=role.role_id,
                tenant_id=tenant.tenant_id,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
        )
    else:
        assignment.is_deleted = False
        assignment.deleted_at = None
        assignment.deleted_by = None

    if created:
        # Requirement 14: the new account's role is recorded like every other role change; no
        # person made it, so the account itself is the actor.
        await users.add_change(
            UserChange(
                tenant_id=tenant.tenant_id,
                actor_user_id=user.user_id,
                target_user_id=user.user_id,
                changed_field=UserChangeField.ROLE.value,
                old_value=None,
                new_value=SUPER_ADMIN_ROLE,
                created_by=user.user_id,
                updated_by=user.user_id,
            )
        )

    tenant.created_by = tenant.created_by or user.user_id
    tenant.updated_by = user.user_id
    role.created_by = role.created_by or user.user_id
    role.updated_by = user.user_id
    user.created_by = user.created_by or user.user_id
    user.updated_by = user.user_id
    await session.commit()
    return SuperAdminResult(
        user_public_id=UUID(user.public_id),
        tenant_public_id=UUID(tenant.public_id),
        created=created,
        is_super_admin=True,
    )


async def bootstrap_super_admin(
    session_factory: SessionFactory, settings: Settings
) -> BootstrapOutcome:
    """One start-up attempt; database errors propagate so the caller can retry."""

    password = settings.bootstrap_super_admin_password
    username = settings.bootstrap_super_admin_username
    if password is None or not username.strip():
        log_event(
            logger, "auth.super_admin.bootstrap", outcome=BootstrapOutcome.NOT_CONFIGURED.value
        )
        return BootstrapOutcome.NOT_CONFIGURED
    try:
        async with session_factory() as session:
            result = await ensure_super_admin(
                session,
                email=settings.bootstrap_super_admin_email,
                username=username,
                password=password.get_secret_value(),
                upn_suffix=settings.directory_upn_suffix,
                reset_existing=False,
            )
    except SuperAdminRejected as rejected:
        log_event(
            logger,
            "auth.super_admin.bootstrap",
            outcome=BootstrapOutcome.REJECTED.value,
            reason=rejected.reason,
        )
        return BootstrapOutcome.REJECTED
    outcome = BootstrapOutcome.CREATED if result.created else BootstrapOutcome.EXISTS
    log_event(
        logger,
        "auth.super_admin.bootstrap",
        outcome=outcome.value,
        user_public_id=str(result.user_public_id),
        super_admin=result.is_super_admin,
    )
    return outcome


async def run_super_admin_bootstrap(
    session_factory: SessionFactory,
    settings: Settings,
    *,
    first_retry_seconds: float = BOOTSTRAP_FIRST_RETRY_SECONDS,
    max_retry_seconds: float = BOOTSTRAP_MAX_RETRY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BootstrapOutcome:
    """Background task of the backend start: retry until the database and schema answer.

    On a first installation the migration job may still be creating the schema while the backend
    starts; the start neither waits for this task nor fails because of it.
    """

    delay = first_retry_seconds
    attempt = 1
    while True:
        try:
            return await bootstrap_super_admin(session_factory, settings)
        except Exception as error:  # noqa: BLE001 - reported with its type only
            # The message of a database error may quote statement parameters; only the type is
            # written.
            log_event(
                logger,
                "auth.super_admin.bootstrap_retry",
                attempt=attempt,
                error_type=type(error).__name__,
                retry_in_seconds=round(delay),
            )
        await sleep(delay)
        delay = min(delay * 2, max_retry_seconds)
        attempt += 1
