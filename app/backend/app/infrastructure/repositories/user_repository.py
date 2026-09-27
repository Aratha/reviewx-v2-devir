"""User, tenant, role-assignment and change-history persistence queries."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.permission import Permission, RolePermission
from app.domain.models.role import APPLICATION_ROLES, SUPER_ADMIN_ROLE, Role, UserRole
from app.domain.models.tenant import Tenant
from app.domain.models.user import AccountType, User
from app.domain.models.user_change import UserChange


@dataclass(frozen=True, slots=True)
class AuthorizationSnapshot:
    tenant_public_id: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]

    @property
    def is_super_admin(self) -> bool:
        return SUPER_ADMIN_ROLE in self.roles


@dataclass(frozen=True, slots=True)
class UserListRow:
    user: User
    roles: tuple[str, ...]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository:
    """Persistence adapter used by the authentication and user-administration services."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_local_by_username(self, normalized_name: str) -> User | None:
        statement = select(User).where(
            func.lower(User.username) == normalized_name,
            User.account_type == AccountType.LOCAL.value,
            User.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_directory_guid(
        self, object_guid: UUID, *, for_update: bool = False
    ) -> User | None:
        statement = select(User).where(User.directory_object_guid == object_guid)
        if for_update:
            statement = statement.with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def find_identity_conflict(
        self, *, email: str, username: str, excluding_user_id: int | None = None
    ) -> User | None:
        statement = select(User).where(
            or_(func.lower(User.email) == email, func.lower(User.username) == username)
        )
        if excluding_user_id is not None:
            statement = statement.where(User.user_id != excluding_user_id)
        return (await self.session.execute(statement.limit(1))).scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_active_by_public_id(self, public_id: UUID) -> User | None:
        statement = select(User).where(
            User.public_id == str(public_id),
            User.is_active.is_(True),
            User.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_in_tenant_for_update(self, public_id: UUID, tenant_id: int) -> User | None:
        statement = (
            select(User)
            .where(
                User.public_id == str(public_id),
                User.home_tenant_id == tenant_id,
                User.is_deleted.is_(False),
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_tenant_by_code(self, code: str) -> Tenant | None:
        statement = select(Tenant).where(
            Tenant.code == code, Tenant.is_active.is_(True), Tenant.is_deleted.is_(False)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_tenant_by_public_id(self, public_id: UUID) -> Tenant | None:
        statement = select(Tenant).where(
            Tenant.public_id == str(public_id),
            Tenant.is_active.is_(True),
            Tenant.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_role(self, code: str) -> Role | None:
        statement = select(Role).where(Role.code == code, Role.is_deleted.is_(False))
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def role_codes(self, user: User) -> tuple[str, ...]:
        statement = (
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
        return tuple((await self.session.scalars(statement)).all())

    async def set_application_role(
        self, user: User, role: Role, *, actor_user_id: int | None, now: datetime
    ) -> None:
        """Make ``role`` the user's only active application role in its home tenant."""

        statement = (
            select(UserRole)
            .join(Role, Role.role_id == UserRole.role_id)
            .where(
                UserRole.user_id == user.user_id,
                UserRole.tenant_id == user.home_tenant_id,
                Role.code.in_(APPLICATION_ROLES),
            )
            .with_for_update(of=UserRole)
        )
        assignments = (await self.session.scalars(statement)).all()
        target = None
        for assignment in assignments:
            if assignment.role_id == role.role_id:
                target = assignment
            elif not assignment.is_deleted:
                assignment.is_deleted = True
                assignment.deleted_at = now
                assignment.deleted_by = actor_user_id
                assignment.updated_by = actor_user_id
        if target is None:
            self.session.add(
                UserRole(
                    user_id=user.user_id,
                    role_id=role.role_id,
                    tenant_id=user.home_tenant_id,
                    created_by=actor_user_id,
                    updated_by=actor_user_id,
                )
            )
        elif target.is_deleted:
            target.is_deleted = False
            target.deleted_at = None
            target.deleted_by = None
            target.updated_by = actor_user_id
        await self.session.flush()

    async def list_users(
        self, *, tenant_id: int, query: str | None, offset: int, limit: int
    ) -> tuple[list[UserListRow], int]:
        conditions = [User.home_tenant_id == tenant_id, User.is_deleted.is_(False)]
        if query:
            pattern = f"%{_escape_like(query.casefold())}%"
            conditions.append(
                or_(
                    func.lower(User.username).like(pattern, escape="\\"),
                    func.lower(User.display_name).like(pattern, escape="\\"),
                    func.lower(User.email).like(pattern, escape="\\"),
                )
            )
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(User).where(*conditions)
                )
            ).scalar_one()
        )
        users = (
            await self.session.scalars(
                select(User)
                .where(*conditions)
                .order_by(User.username, User.user_id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        roles_by_user: dict[int, list[str]] = {user.user_id: [] for user in users}
        if users:
            rows = await self.session.execute(
                select(UserRole.user_id, Role.code)
                .join(Role, Role.role_id == UserRole.role_id)
                .where(
                    UserRole.user_id.in_(list(roles_by_user)),
                    UserRole.tenant_id == tenant_id,
                    UserRole.is_deleted.is_(False),
                    Role.is_deleted.is_(False),
                )
                .order_by(Role.code)
            )
            for user_id, code in rows.all():
                roles_by_user[user_id].append(code)
        return [
            UserListRow(user=user, roles=tuple(roles_by_user[user.user_id])) for user in users
        ], total

    async def add_change(self, change: UserChange) -> None:
        self.session.add(change)
        await self.session.flush()

    async def touch_login(self, user: User, when: datetime) -> None:
        user.last_login_at = when
        await self.session.flush()

    async def authorization_for(self, user: User) -> AuthorizationSnapshot:
        tenant_statement = select(Tenant).where(
            Tenant.tenant_id == user.home_tenant_id,
            Tenant.is_active.is_(True),
            Tenant.is_deleted.is_(False),
        )
        tenant = (await self.session.execute(tenant_statement)).scalar_one_or_none()
        if tenant is None:
            raise LookupError("the user's home tenant is unavailable")

        roles = await self.role_codes(user)
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
