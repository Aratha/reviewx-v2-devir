"""User authentication and authorization queries."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.permission import Permission, RolePermission
from app.domain.models.role import Role, UserRole
from app.domain.models.tenant import Tenant
from app.domain.models.user import User


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    tenant_public_id: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


class UserRepository:
    """Persistence adapter used by authentication services."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_login(self, identifier: str) -> User | None:
        normalized = identifier.strip().lower()
        statement = select(User).where(
            or_(
                func.lower(User.username) == normalized,
                func.lower(User.email) == normalized,
            ),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_active_by_public_id(self, public_id: UUID) -> User | None:
        statement = select(User).where(
            User.public_id == str(public_id),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def authorization_for(self, user: User) -> AuthorizationSnapshot:
        tenant_statement = select(Tenant).where(
            Tenant.tenant_id == user.home_tenant_id,
            Tenant.is_active.is_(True),
            Tenant.is_deleted.is_(False),
        )
        tenant = (await self.session.execute(tenant_statement)).scalar_one_or_none()
        if tenant is None:
            raise LookupError("the user's home tenant is unavailable")

        role_statement = (
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(
                UserRole.user_id == user.user_id,
                UserRole.tenant_id == user.home_tenant_id,
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
            )
            .order_by(Role.code)
        )
        roles = tuple((await self.session.scalars(role_statement)).all())

        permission_statement = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
            .join(Role, Role.role_id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.role_id)
            .where(
                UserRole.user_id == user.user_id,
                UserRole.tenant_id == user.home_tenant_id,
                UserRole.is_deleted.is_(False),
                Role.is_deleted.is_(False),
                RolePermission.is_deleted.is_(False),
                Permission.is_deleted.is_(False),
            )
            .distinct()
            .order_by(Permission.code)
        )
        permissions = tuple((await self.session.scalars(permission_statement)).all())
        return AuthorizationSnapshot(
            tenant_public_id=tenant.public_id,
            roles=roles,
            permissions=permissions,
        )
