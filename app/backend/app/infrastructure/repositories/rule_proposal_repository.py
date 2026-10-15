"""Tenant-scoped persistence of rule proposals, publish requests and the proposal permission."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.models.rule_proposal import (
    ProposalStatus,
    PublishRequestStatus,
    RuleProposal,
    RulePublishRequest,
)
from app.domain.models.user import User


@dataclass(frozen=True, slots=True)
class ProposalRow:
    proposal: RuleProposal
    proposer_name: str
    decided_by_name: str | None


@dataclass(frozen=True, slots=True)
class PublishRequestRow:
    request: RulePublishRequest
    requester_name: str
    decided_by_name: str | None


class RuleProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Proposal permission (Requirement 1) ----------------------------------------------------

    # --- Proposals ------------------------------------------------------------------------------

    async def add_proposal(self, proposal: RuleProposal) -> RuleProposal:
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def proposal_row(self, tenant_id: int, public_id: str) -> ProposalRow | None:
        rows, _ = await self._proposal_rows(
            tenant_id, [RuleProposal.public_id == public_id], offset=0, limit=1
        )
        return rows[0] if rows else None

    async def lock_proposal(self, tenant_id: int, public_id: str) -> RuleProposal | None:
        statement = (
            select(RuleProposal)
            .where(
                RuleProposal.tenant_id == tenant_id,
                RuleProposal.public_id == public_id,
                RuleProposal.is_deleted.is_(False),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_proposals(
        self,
        tenant_id: int,
        *,
        proposer_user_id: int | None,
        status: ProposalStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ProposalRow], int]:
        filters: list[ColumnElement[bool]] = []
        if proposer_user_id is not None:
            filters.append(RuleProposal.proposer_user_id == proposer_user_id)
        if status is not None:
            filters.append(RuleProposal.status == status.value)
        return await self._proposal_rows(tenant_id, filters, offset=offset, limit=limit)

    async def _proposal_rows(
        self,
        tenant_id: int,
        extra: Sequence[ColumnElement[bool]],
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ProposalRow], int]:
        filters = [RuleProposal.tenant_id == tenant_id, RuleProposal.is_deleted.is_(False), *extra]
        total = await self.session.scalar(
            select(func.count()).select_from(RuleProposal).where(*filters)
        )
        proposer = aliased(User)
        decider = aliased(User)
        rows = await self.session.execute(
            select(RuleProposal, proposer.display_name, decider.display_name)
            .join(proposer, proposer.user_id == RuleProposal.proposer_user_id)
            .outerjoin(decider, decider.user_id == RuleProposal.decided_by_user_id)
            .where(*filters)
            .order_by(RuleProposal.created_at.desc(), RuleProposal.rule_proposal_id.desc())
            .offset(offset)
            .limit(limit)
        )
        return [ProposalRow(*row) for row in rows.all()], int(total or 0)

    # --- Publish requests -----------------------------------------------------------------------

    async def invalidate_pending_requests(
        self, tenant_id: int, *, actor_user_id: int, now: datetime
    ) -> list[str]:
        """Mark the tenant's pending publish request invalid; returns the affected public ids."""

        rows = await self.session.scalars(
            select(RulePublishRequest)
            .where(
                RulePublishRequest.tenant_id == tenant_id,
                RulePublishRequest.status == PublishRequestStatus.PENDING.value,
                RulePublishRequest.is_deleted.is_(False),
            )
            .with_for_update()
        )
        changed = []
        for row in rows:
            row.status = PublishRequestStatus.INVALID.value
            row.decided_at = now
            row.updated_by = actor_user_id
            changed.append(row.public_id)
        await self.session.flush()
        return changed

    async def add_request(self, request: RulePublishRequest) -> RulePublishRequest:
        self.session.add(request)
        await self.session.flush()
        return request

    async def lock_request(self, tenant_id: int, public_id: str) -> RulePublishRequest | None:
        statement = (
            select(RulePublishRequest)
            .where(
                RulePublishRequest.tenant_id == tenant_id,
                RulePublishRequest.public_id == public_id,
                RulePublishRequest.is_deleted.is_(False),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def request_row(self, tenant_id: int, public_id: str) -> PublishRequestRow | None:
        rows, _ = await self._request_rows(
            tenant_id, [RulePublishRequest.public_id == public_id], offset=0, limit=1
        )
        return rows[0] if rows else None

    async def list_requests(
        self,
        tenant_id: int,
        *,
        requester_user_id: int | None,
        status: PublishRequestStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[PublishRequestRow], int]:
        filters: list[ColumnElement[bool]] = []
        if requester_user_id is not None:
            filters.append(RulePublishRequest.requester_user_id == requester_user_id)
        if status is not None:
            filters.append(RulePublishRequest.status == status.value)
        return await self._request_rows(tenant_id, filters, offset=offset, limit=limit)

    async def _request_rows(
        self,
        tenant_id: int,
        extra: Sequence[ColumnElement[bool]],
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[PublishRequestRow], int]:
        filters = [
            RulePublishRequest.tenant_id == tenant_id,
            RulePublishRequest.is_deleted.is_(False),
            *extra,
        ]
        total = await self.session.scalar(
            select(func.count()).select_from(RulePublishRequest).where(*filters)
        )
        requester = aliased(User)
        decider = aliased(User)
        rows = await self.session.execute(
            select(RulePublishRequest, requester.display_name, decider.display_name)
            .join(requester, requester.user_id == RulePublishRequest.requester_user_id)
            .outerjoin(decider, decider.user_id == RulePublishRequest.decided_by_user_id)
            .where(*filters)
            .order_by(
                RulePublishRequest.created_at.desc(),
                RulePublishRequest.rule_publish_request_id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return [PublishRequestRow(*row) for row in rows.all()], int(total or 0)
