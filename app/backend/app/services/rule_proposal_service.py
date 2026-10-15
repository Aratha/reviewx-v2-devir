"""Rule and group proposals and publish requests; every reviewer and rule manager proposes.

sql-review/PRDs/009-rule-proposals Requirement 1-7. Every approval locks the tenant draft row
first, the same lock a direct publish takes, so two approvals never publish the same version
number; an approved proposal is added to the latest published content, published and written to
the draft in one transaction (Decision 2). Texts, summaries, group names and reasons never reach
the log.
"""

import logging
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.models.mixins import new_public_id
from app.domain.models.rule_proposal import (
    PROPOSAL_REASON_MAX_LENGTH,
    ProposalStatus,
    RuleProposal,
    RuleProposalKind,
)
from app.domain.models.rule_set import RulePriorityGroup
from app.domain.models.tenant import Tenant
from app.domain.models.user import User
from app.domain.rule_proposal import (
    ProposalConflictError,
    ProposedGroup,
    ProposedRule,
    validate_group_proposal,
    validate_rule_proposal,
    with_group_proposal,
    with_rule_proposal,
)
from app.domain.rule_set import (
    RuleGroups,
    RuleSetValidationError,
    fold_group_name,
    format_rule_code,
)
from app.infrastructure.repositories.rule_proposal_repository import (
    ProposalRow,
    RuleProposalRepository,
)
from app.infrastructure.repositories.rule_set_repository import RuleSetRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.rule_proposals.contracts import (
    ProposalScopeValue,
    RuleProposalCapabilities,
    RuleProposalCreate,
    RuleProposalDetail,
    RuleProposalItem,
    RuleProposalPage,
)
from app.services.request_scope import acting_user, active_tenant
from app.services.rule_set_service import RuleSetService

logger = logging.getLogger("app.rule_proposals")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _unprocessable(code: str, message: str) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, code, message)


def _decision_forbidden() -> ApplicationError:
    return ApplicationError(status.HTTP_403_FORBIDDEN, "forbidden", "Bu işlem için yetkiniz yok.")


def _proposal_not_found() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "rule_proposal_not_found", "Kural önerisi bulunamadı."
    )


def _proposal_not_pending() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "proposal_not_pending",
        "Öneri artık beklemiyor; sayfayı yenileyin.",
    )


def _reason(value: str) -> str:
    trimmed = value.strip()
    if not 1 <= len(trimmed) <= PROPOSAL_REASON_MAX_LENGTH:
        raise _unprocessable("rejection_reason_invalid", "Ret gerekçesi 1-500 karakter olmalıdır.")
    return trimmed


def _proposal_item(row: ProposalRow, actor: User) -> dict[str, object]:
    proposal = row.proposal
    return {
        "id": proposal.public_id,
        "kind": proposal.kind,
        "status": proposal.status,
        "proposer_name": row.proposer_name,
        "created_at": proposal.created_at,
        "summary": proposal.summary,
        "group_name": proposal.group_name,
        "decided_by_name": row.decided_by_name,
        "decided_at": proposal.decided_at,
        "rejection_reason": proposal.rejection_reason,
        "published_version_number": proposal.published_version_number,
        "new_rule_id": proposal.new_rule_code,
        "owned": proposal.proposer_user_id == actor.user_id,
    }


def _proposal_detail(row: ProposalRow, actor: User) -> RuleProposalDetail:
    proposal = row.proposal
    return RuleProposalDetail.model_validate(
        {
            **_proposal_item(row, actor),
            "text": proposal.rule_text,
            "priority": proposal.priority_group,
            "requires_metadata": proposal.requires_metadata,
            "rule_group_ids": list(proposal.rule_group_ids),
            "group_description": proposal.group_description,
            "rule_codes": list(proposal.rule_codes),
            "rationale": proposal.rationale,
        }
    )


class RuleProposalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.proposals = RuleProposalRepository(session)
        self.rules = RuleSetRepository(session)
        self.users = UserRepository(session)
        self.rule_sets = RuleSetService(session)

    async def _scope(self, context: RequestContext) -> tuple[Tenant, User]:
        return await active_tenant(self.users, context), await acting_user(self.users, context)

    async def _latest_rules(self, tenant_id: int) -> tuple[int | None, RuleGroups]:
        latest = await self.rules.latest_version(tenant_id)
        if latest is None:
            return None, RuleGroups()
        return latest.number, await self.rules.version_rules(latest)

    # --- Capabilities (Requirement 1, 7) -------------------------------------------------------

    async def capabilities(self, context: RequestContext) -> RuleProposalCapabilities:
        # Decision 9: every reviewer and rule manager proposes; only the super admin decides.
        await self._scope(context)
        return RuleProposalCapabilities(can_propose=True, can_decide=context.is_super_admin)

    # --- Proposals (Requirement 2-5) -----------------------------------------------------------

    async def create_proposal(
        self, context: RequestContext, body: RuleProposalCreate
    ) -> RuleProposalDetail:
        tenant, actor = await self._scope(context)
        _, latest = await self._latest_rules(tenant.tenant_id)
        try:
            if body.kind == RuleProposalKind.RULE.value:
                proposal = self._new_rule_proposal(body, latest)
            else:
                proposal = await self._new_group_proposal(tenant, body, latest)
        except RuleSetValidationError as error:
            raise _unprocessable(error.code, error.message) from None
        proposal.tenant_id = tenant.tenant_id
        proposal.proposer_user_id = actor.user_id
        proposal.rationale = body.rationale.strip()
        proposal.created_by = actor.user_id
        proposal.updated_by = actor.user_id
        await self.proposals.add_proposal(proposal)
        log_event(
            logger,
            "rule_proposal.created",
            proposal_public_id=proposal.public_id,
            kind=proposal.kind,
            user_public_id=actor.public_id,
        )
        return await self._detail(tenant, actor, proposal.public_id)

    def _new_rule_proposal(self, body: RuleProposalCreate, latest: RuleGroups) -> RuleProposal:
        valid = validate_rule_proposal(
            summary=body.summary,
            text=body.text,
            priority=RulePriorityGroup(body.priority),
            requires_metadata=body.requires_metadata,
            rule_group_ids=body.rule_group_ids,
        )
        known = {group.public_id for group in latest.rule_groups}
        if not set(valid.rule_group_ids) <= known:
            raise RuleSetValidationError(
                "rule_group_unknown", "Seçilen kural grubu yayımlanmış sürümde yok."
            )
        return RuleProposal(
            public_id=new_public_id(),
            kind=RuleProposalKind.RULE.value,
            summary=valid.summary,
            rule_text=valid.text,
            priority_group=valid.priority.value,
            requires_metadata=valid.requires_metadata,
            rule_group_ids=list(valid.rule_group_ids),
        )

    async def _new_group_proposal(
        self, tenant: Tenant, body: RuleProposalCreate, latest: RuleGroups
    ) -> RuleProposal:
        valid = validate_group_proposal(body.group_name, body.group_description, body.rule_codes)
        if not set(valid.rule_codes) <= latest.codes:
            raise RuleSetValidationError("rule_unknown", "Seçilen kural yayımlanmış sürümde yok.")
        draft = await self.rules.get_draft(tenant.tenant_id)
        draft_groups = () if draft is None else (await self.rules.draft_rules(draft)).rule_groups
        folded = fold_group_name(valid.name)
        if any(fold_group_name(g.name) == folded for g in (*latest.rule_groups, *draft_groups)):
            raise RuleSetValidationError(
                "rule_group_name_duplicate", "Aynı adla bir kural grubu zaten var."
            )
        return RuleProposal(
            public_id=new_public_id(),
            kind=RuleProposalKind.GROUP.value,
            group_name=valid.name,
            group_description=valid.description,
            rule_codes=list(valid.rule_codes),
        )

    async def list_proposals(
        self,
        context: RequestContext,
        *,
        scope: ProposalScopeValue,
        page: int,
        page_size: int,
    ) -> RuleProposalPage:
        tenant, actor = await self._scope(context)
        if scope != "mine" and not context.is_super_admin:
            raise _decision_forbidden()
        rows, total = await self.proposals.list_proposals(
            tenant.tenant_id,
            proposer_user_id=actor.user_id if scope == "mine" else None,
            status=ProposalStatus.PENDING if scope == "pending" else None,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return RuleProposalPage(
            items=[RuleProposalItem.model_validate(_proposal_item(row, actor)) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def proposal(self, context: RequestContext, proposal_id: str) -> RuleProposalDetail:
        tenant, actor = await self._scope(context)
        return await self._detail(tenant, actor, proposal_id, context=context)

    async def _detail(
        self,
        tenant: Tenant,
        actor: User,
        proposal_id: str,
        *,
        context: RequestContext | None = None,
    ) -> RuleProposalDetail:
        row = await self.proposals.proposal_row(tenant.tenant_id, proposal_id)
        if row is None:
            raise _proposal_not_found()
        visible = row.proposal.proposer_user_id == actor.user_id or (
            context is None or context.is_super_admin
        )
        if not visible:
            raise _proposal_not_found()
        return _proposal_detail(row, actor)

    async def withdraw(self, context: RequestContext, proposal_id: str) -> RuleProposalDetail:
        tenant, actor = await self._scope(context)
        proposal = await self.proposals.lock_proposal(tenant.tenant_id, proposal_id)
        if proposal is None or proposal.proposer_user_id != actor.user_id:
            raise _proposal_not_found()
        if proposal.status != ProposalStatus.PENDING.value:
            raise _proposal_not_pending()
        proposal.status = ProposalStatus.WITHDRAWN.value
        proposal.decided_at = datetime.now(UTC)
        proposal.updated_by = actor.user_id
        await self.session.flush()
        log_event(
            logger,
            "rule_proposal.withdrawn",
            proposal_public_id=proposal.public_id,
            kind=proposal.kind,
            user_public_id=actor.public_id,
        )
        return await self._detail(tenant, actor, proposal_id)

    async def approve(self, context: RequestContext, proposal_id: str) -> RuleProposalDetail:
        """Publish the proposal on the latest version and write it to the draft (Decision 2)."""

        tenant, actor = await self._scope(context)
        draft = await self.rules.lock_draft(tenant.tenant_id, actor_user_id=actor.user_id)
        proposal = await self.proposals.lock_proposal(tenant.tenant_id, proposal_id)
        if proposal is None:
            raise _proposal_not_found()
        if proposal.status != ProposalStatus.PENDING.value:
            raise _proposal_not_pending()
        _, latest = await self._latest_rules(tenant.tenant_id)
        current = await self.rules.draft_rules(draft)
        code: str | None = None
        group_id: str | None = None
        try:
            if proposal.kind == RuleProposalKind.RULE.value:
                rule = ProposedRule(
                    proposal.summary,
                    proposal.rule_text,
                    RulePriorityGroup(proposal.priority_group or RulePriorityGroup.NORMAL.value),
                    proposal.requires_metadata,
                    tuple(str(value) for value in proposal.rule_group_ids),
                )
                code = format_rule_code(draft.next_rule_number)
                published = with_rule_proposal(latest, rule, code)
                drafted = with_rule_proposal(current, rule, code, strict=False)
            else:
                group = ProposedGroup(
                    proposal.group_name,
                    proposal.group_description,
                    tuple(str(value) for value in proposal.rule_codes),
                )
                group_id = new_public_id()
                published = with_group_proposal(latest, group, group_id)
                drafted = with_group_proposal(current, group, group_id, strict=False)
        except ProposalConflictError as error:
            raise ApplicationError(status.HTTP_409_CONFLICT, error.code, error.message) from None
        version, _ = await self.rule_sets.publish_rules(tenant.tenant_id, actor, published)
        now = datetime.now(UTC)
        await self.rules.replace_draft_rules(draft, drafted, actor_user_id=actor.user_id, now=now)
        draft.revision += 1
        if code is not None:
            draft.next_rule_number += 1
        draft.updated_by = actor.user_id
        draft.updated_at = now
        proposal.status = ProposalStatus.APPROVED.value
        proposal.decided_by_user_id = actor.user_id
        proposal.decided_at = now
        proposal.published_version_number = version.number
        proposal.new_rule_code = code
        proposal.new_rule_group_public_id = group_id
        proposal.updated_by = actor.user_id
        await self.session.flush()
        log_event(
            logger,
            "rule_proposal.approved",
            proposal_public_id=proposal.public_id,
            kind=proposal.kind,
            number=version.number,
            user_public_id=actor.public_id,
        )
        return await self._detail(tenant, actor, proposal_id)

    async def reject(
        self, context: RequestContext, proposal_id: str, reason: str
    ) -> RuleProposalDetail:
        tenant, actor = await self._scope(context)
        text = _reason(reason)
        proposal = await self.proposals.lock_proposal(tenant.tenant_id, proposal_id)
        if proposal is None:
            raise _proposal_not_found()
        if proposal.status != ProposalStatus.PENDING.value:
            raise _proposal_not_pending()
        proposal.status = ProposalStatus.REJECTED.value
        proposal.decided_by_user_id = actor.user_id
        proposal.decided_at = datetime.now(UTC)
        proposal.rejection_reason = text
        proposal.updated_by = actor.user_id
        await self.session.flush()
        log_event(
            logger,
            "rule_proposal.rejected",
            proposal_public_id=proposal.public_id,
            kind=proposal.kind,
            user_public_id=actor.public_id,
        )
        return await self._detail(tenant, actor, proposal_id)
