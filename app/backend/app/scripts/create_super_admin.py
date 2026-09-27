"""Create or reset the application-level super administrator idempotently."""

import argparse
import asyncio
import getpass
import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.base  # noqa: F401  # populate mapper metadata before any write
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import async_session_factory
from app.domain.directory import InvalidDirectoryName, validate_local_account_name
from app.domain.models.role import SUPER_ADMIN_ROLE, Role, UserRole
from app.domain.models.tenant import Tenant
from app.domain.models.user import User


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    user_public_id: UUID
    tenant_public_id: UUID
    created: bool


async def ensure_super_admin(
    session: AsyncSession,
    *,
    email: str,
    username: str,
    password: str,
    tenant_code: str = "platform",
    tenant_name: str = "Platform",
    upn_suffix: str = "",
) -> BootstrapResult:
    """Create or reset the super admin and ensure its system-role assignment."""

    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise ValueError("email must be a valid address")
    try:
        # The super admin is a local account: its name never carries the directory UPN suffix.
        normalized_username = validate_local_account_name(username, upn_suffix)
    except InvalidDirectoryName as exc:
        raise ValueError(str(exc)) from None
    password_hash = hash_password(
        password, context=(normalized_username, normalized_email.partition("@")[0])
    )

    role = (
        await session.execute(select(Role).where(Role.code == SUPER_ADMIN_ROLE))
    ).scalar_one_or_none()
    if role is None:
        raise RuntimeError("super_admin role is missing; run Alembic migrations first")
    role.is_deleted = False
    role.deleted_at = None
    role.deleted_by = None

    tenant = (
        await session.execute(select(Tenant).where(Tenant.code == tenant_code))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(code=tenant_code, name=tenant_name)
        session.add(tenant)
        await session.flush()
    else:
        tenant.name = tenant_name
        tenant.is_deleted = False
        tenant.deleted_at = None
        tenant.deleted_by = None
        tenant.is_active = True

    user = (
        await session.execute(select(User).where(User.username == normalized_username))
    ).scalar_one_or_none()
    created = user is None
    if user is None:
        email_owner = (
            await session.execute(
                select(User).where(User.email == normalized_email, User.is_deleted.is_(False))
            )
        ).scalar_one_or_none()
        if email_owner is not None:
            raise ValueError("email is already assigned to another user")
        user = User(
            home_tenant_id=tenant.tenant_id,
            username=normalized_username,
            email=normalized_email,
            display_name="Super Admin",
            password_hash=password_hash,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    else:
        email_owner = (
            await session.execute(
                select(User).where(
                    User.email == normalized_email,
                    User.user_id != user.user_id,
                )
            )
        ).scalar_one_or_none()
        if email_owner is not None:
            raise ValueError("email is already assigned to another user")
        user.home_tenant_id = tenant.tenant_id
        user.email = normalized_email
        user.password_hash = password_hash
        user.is_active = True
        user.is_deleted = False
        user.deleted_at = None
        user.deleted_by = None

    assignment = (
        await session.execute(
            select(UserRole).where(
                UserRole.user_id == user.user_id,
                UserRole.role_id == role.role_id,
                UserRole.tenant_id == tenant.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        assignment = UserRole(
            user_id=user.user_id,
            role_id=role.role_id,
            tenant_id=tenant.tenant_id,
            created_by=user.user_id,
            updated_by=user.user_id,
        )
        session.add(assignment)
    else:
        assignment.is_deleted = False
        assignment.deleted_at = None
        assignment.deleted_by = None

    tenant.created_by = tenant.created_by or user.user_id
    tenant.updated_by = user.user_id
    role.created_by = role.created_by or user.user_id
    role.updated_by = user.user_id
    user.created_by = user.created_by or user.user_id
    user.updated_by = user.user_id
    await session.commit()
    return BootstrapResult(
        user_public_id=UUID(user.public_id),
        tenant_public_id=UUID(tenant.public_id),
        created=created,
    )


def _password_from_operator(use_stdin: bool) -> str:
    settings = get_settings()
    if settings.bootstrap_super_admin_password is not None:
        return settings.bootstrap_super_admin_password.get_secret_value()
    if use_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise ValueError("password input was empty")
        return password
    first = getpass.getpass("Super-admin password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


async def _run(args: argparse.Namespace) -> BootstrapResult:
    settings = get_settings()
    async with async_session_factory() as session:
        return await ensure_super_admin(
            session,
            email=args.email or settings.bootstrap_super_admin_email,
            username=args.username or settings.bootstrap_super_admin_username,
            password=_password_from_operator(args.password_stdin),
            tenant_code=args.tenant_code,
            tenant_name=args.tenant_name,
            upn_suffix=settings.directory_upn_suffix,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset the application super admin")
    parser.add_argument("--email")
    parser.add_argument("--username")
    parser.add_argument("--tenant-code", default="platform")
    parser.add_argument("--tenant-name", default="Platform")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read one password line from standard input instead of prompting",
    )
    result = asyncio.run(_run(parser.parse_args()))
    action = "created" if result.created else "updated"
    print(
        f"super admin {action}: user={result.user_public_id} " f"tenant={result.tenant_public_id}"
    )


if __name__ == "__main__":
    main()
