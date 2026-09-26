"""Alembic, bootstrap, login, /me, and super-admin tenant switching."""

import logging
import secrets
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.domain.models.tenant import Tenant
from app.main import app
from app.scripts.create_super_admin import ensure_super_admin

pytestmark = pytest.mark.integration


def test_alembic_upgrade_keeps_application_logging(migrated_database: None) -> None:
    assert logging.getLogger("app.http").disabled is False


@pytest.mark.asyncio
async def test_super_admin_authentication_flow(migrated_database: None) -> None:
    suffix = uuid4().hex[:10]
    username = f"admin-{suffix}"
    email = f"admin-{suffix}@example.test"
    # Test-process credentials; nothing committed is a usable password.
    initial_password = secrets.token_urlsafe(24)
    password = secrets.token_urlsafe(24)
    tenant_code = f"platform-{suffix}"

    async with async_session_factory() as session:
        first = await ensure_super_admin(
            session,
            email=email,
            username=username,
            password=initial_password,
            tenant_code=tenant_code,
            tenant_name="Integration Platform",
        )
    async with async_session_factory() as session:
        second = await ensure_super_admin(
            session,
            email=email,
            username=username,
            password=password,
            tenant_code=tenant_code,
            tenant_name="Integration Platform",
        )
        other_tenant = Tenant(code=f"other-{suffix}", name="Other Tenant")
        session.add(other_tenant)
        await session.commit()

    assert first.created is True
    assert second.created is False
    assert first.user_public_id == second.user_public_id

    settings = get_settings()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200, login.text
        payload = login.json()
        assert set(payload) == {"access_token", "token_type", "user"}
        assert set(payload["user"]) == {
            "public_id",
            "username",
            "tenant_id",
            "roles",
            "permissions",
            "is_super_admin",
        }
        assert payload["user"]["is_super_admin"] is True
        assert payload["user"]["tenant_id"] == str(first.tenant_public_id)

        headers = {
            "Authorization": f"Bearer {payload['access_token']}",
            settings.tenant_header: str(first.tenant_public_id),
        }
        profile = await client.get(f"{settings.api_prefix}/auth/me", headers=headers)
        assert profile.status_code == 200, profile.text
        assert set(profile.json()) == set(payload["user"])
        assert profile.json()["public_id"] == str(first.user_public_id)

        switched_headers = {
            "Authorization": f"Bearer {payload['access_token']}",
            settings.tenant_header: str(other_tenant.public_id),
        }
        switched = await client.get(f"{settings.api_prefix}/auth/me", headers=switched_headers)
        assert switched.status_code == 200, switched.text
        assert switched.json()["tenant_id"] == str(other_tenant.public_id)

        rejected = await client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": username, "password": initial_password},
        )
        assert rejected.status_code == 401
        assert rejected.headers["WWW-Authenticate"] == "Bearer"

        unknown = await client.post(
            f"{settings.api_prefix}/auth/login",
            json={"username": f"missing-{suffix}", "password": password},
        )
        assert unknown.status_code == 401
        assert unknown.json() == rejected.json()
