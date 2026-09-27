"""Immutable request-scoped authentication and tenant state."""

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Verified JWT claims projected into the active tenant selected by the request."""

    tenant_id: UUID | None = None
    subject: UUID | None = None
    username: str | None = None
    home_tenant_id: UUID | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_super_admin: bool = False
    token_invalid: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.subject is not None and not self.token_invalid

    def has_permission(self, permission: str) -> bool:
        return self.is_super_admin or permission in self.permissions

    def has_role(self, role: str) -> bool:
        return self.is_super_admin or role in self.roles
