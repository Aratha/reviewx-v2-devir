"""Authentication responses containing public identifiers only."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AuthenticatedUser(BaseModel):
    public_id: UUID
    username: str
    tenant_id: UUID
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    is_super_admin: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: AuthenticatedUser
