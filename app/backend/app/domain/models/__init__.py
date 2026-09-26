"""Platform persistence models; business-domain models arrive from accepted specs."""

from app.domain.models.permission import Permission, RolePermission
from app.domain.models.role import Role, UserRole
from app.domain.models.tenant import Tenant
from app.domain.models.user import User

# kt-scaffold:model-imports

__all__ = [
    "Permission",
    "Role",
    "RolePermission",
    "Tenant",
    "User",
    "UserRole",
    # kt-scaffold:model-exports
]
