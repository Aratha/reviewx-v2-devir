"""Super-admin user list, role and activation contracts."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, StrictBool

from app.schemas.auth.response import AccountTypeValue, ApplicationRoleValue


class UserSummary(BaseModel):
    public_id: UUID
    username: str
    display_name: str
    email: str
    account_type: AccountTypeValue
    role: ApplicationRoleValue | None
    is_super_admin: bool
    is_active: bool
    last_login_at: datetime | None


class UserPage(BaseModel):
    items: list[UserSummary]
    page: int
    size: int
    total: int


class RoleChange(BaseModel):
    role: ApplicationRoleValue


class ActiveChange(BaseModel):
    active: StrictBool
