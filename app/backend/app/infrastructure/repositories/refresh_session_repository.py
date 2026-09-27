"""Refresh-token record queries: lookup by digest, rotation and family revocation."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.refresh_session import (
    REFRESH_SESSION_RETENTION_DAYS,
    RefreshSession,
)


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, record: RefreshSession) -> None:
        self.session.add(record)
        await self.session.flush()

    async def get_by_digest_for_update(self, token_sha256: str) -> RefreshSession | None:
        statement = (
            select(RefreshSession)
            .where(RefreshSession.token_sha256 == token_sha256)
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def end_family(self, family_id: UUID, *, reason: str, now: datetime) -> int:
        result = await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def end_user_sessions(self, user_id: int, *, reason: str, now: datetime) -> int:
        result = await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def purge_ended(self, now: datetime) -> int:
        """Delete records whose end or expiry lies more than the retention period in the past."""

        horizon = now - timedelta(days=REFRESH_SESSION_RETENTION_DAYS)
        ended_at = func.coalesce(
            RefreshSession.revoked_at,
            func.least(RefreshSession.idle_expires_at, RefreshSession.absolute_expires_at),
        )
        result = await self.session.execute(delete(RefreshSession).where(ended_at < horizon))
        return int(getattr(result, "rowcount", 0) or 0)
