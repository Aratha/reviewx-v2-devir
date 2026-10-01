"""Persistence of the SQL Server connection a tenant saved (sql-review 002-sql-server-connection)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.sql_connection import SqlConnectionSetting
from app.domain.models.tenant import Tenant


class SqlConnectionSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_tenant_code(self, code: str) -> tuple[SqlConnectionSetting, str] | None:
        """The saved connection of an active tenant with the tenant's public identifier."""

        statement = (
            select(SqlConnectionSetting, Tenant.public_id)
            .join(Tenant, Tenant.tenant_id == SqlConnectionSetting.tenant_id)
            .where(
                Tenant.code == code,
                Tenant.is_active.is_(True),
                Tenant.is_deleted.is_(False),
                SqlConnectionSetting.is_deleted.is_(False),
            )
        )
        row = (await self.session.execute(statement)).first()
        return None if row is None else (row[0], row[1])

    async def lock(self, tenant_id: int) -> SqlConnectionSetting | None:
        """The tenant's saved connection locked for this transaction; None before the first save."""

        statement = (
            select(SqlConnectionSetting)
            .where(
                SqlConnectionSetting.tenant_id == tenant_id,
                SqlConnectionSetting.is_deleted.is_(False),
            )
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def add(self, setting: SqlConnectionSetting) -> None:
        self.session.add(setting)
        await self.session.flush()
