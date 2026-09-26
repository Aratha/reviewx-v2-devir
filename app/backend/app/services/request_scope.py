"""Resolve the active tenant and the acting user of an authenticated request."""

from fastapi import status

from app.core.errors import ApplicationError
from app.core.request_context import RequestContext
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.infrastructure.repositories.user_repository import UserRepository
from app.services.auth_service import not_authenticated


async def active_tenant(users: UserRepository, context: RequestContext) -> Tenant:
    """The tenant selected by the request header, already matched against the token."""

    if context.tenant_id is None:
        raise not_authenticated()
    tenant = await users.get_tenant_by_public_id(context.tenant_id)
    if tenant is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "tenant_not_found", "Kiracı bulunamadı.")
    return tenant


async def acting_user(users: UserRepository, context: RequestContext) -> User:
    """The caller re-read from the database; an inactive or missing account is not signed in."""

    if context.subject is None:
        raise not_authenticated()
    actor = await users.get_active_by_public_id(context.subject)
    if actor is None:
        raise not_authenticated()
    return actor
