"""Rule proposal and publish request endpoints (sql-review 009-rule-proposals).

Every endpoint checks the caller on the server: any reviewer or rule manager proposes (Decision 9),
decisions need the super admin, publish requests need the rule manager role.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import dependencies
from app.api.auth.dependencies import CurrentContext, require_any_role
from app.api.validation import envelope_validation_route
from app.db.session import get_db
from app.domain.models.role import ROLE_REVIEWER
from app.schemas.rule_proposals.contracts import (
    DecisionReason,
    ProposalScopeValue,
    RuleProposalCapabilities,
    RuleProposalCreate,
    RuleProposalDetail,
    RuleProposalPage,
)
from app.services.rule_proposal_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    RuleProposalService,
)

_ERRORS: dict[int | str, dict[str, str]] = {
    401: {"description": "Oturum yok"},
    403: {"description": "Yetki yok"},
}
_ROUTE = envelope_validation_route(status.HTTP_422_UNPROCESSABLE_CONTENT)

proposals_router = APIRouter(
    prefix="/rule-proposals", tags=["rule-proposals"], route_class=_ROUTE, responses=_ERRORS
)
AnyReviewRole = [Depends(require_any_role(ROLE_REVIEWER))]
SuperAdmin = [Depends(dependencies.require_super_admin())]
ProposalId = Annotated[str, Path(min_length=1, max_length=64)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]


def get_rule_proposal_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RuleProposalService:
    return RuleProposalService(session)


Service = Annotated[RuleProposalService, Depends(get_rule_proposal_service)]


# --- Proposals ------------------------------------------------------------------------------------


@proposals_router.get(
    "/capabilities", response_model=RuleProposalCapabilities, dependencies=AnyReviewRole
)
async def read_capabilities(context: CurrentContext, service: Service) -> RuleProposalCapabilities:
    """Whether the caller may propose and decide; the menu uses it (Requirement 7)."""

    return await service.capabilities(context)


@proposals_router.get("", response_model=RuleProposalPage, dependencies=AnyReviewRole)
async def list_proposals(
    context: CurrentContext,
    service: Service,
    scope: ProposalScopeValue = "mine",
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
) -> RuleProposalPage:
    """The caller's proposals; ``pending`` and ``all`` are the super admin's."""

    return await service.list_proposals(context, scope=scope, page=page, page_size=page_size)


@proposals_router.post(
    "",
    response_model=RuleProposalDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=AnyReviewRole,
)
async def create_proposal(
    body: RuleProposalCreate, context: CurrentContext, service: Service
) -> RuleProposalDetail:
    """Propose a new rule or a new group of published rules (Requirement 2, 3)."""

    return await service.create_proposal(context, body)


@proposals_router.get(
    "/{proposal_id}", response_model=RuleProposalDetail, dependencies=AnyReviewRole
)
async def read_proposal(
    proposal_id: ProposalId, context: CurrentContext, service: Service
) -> RuleProposalDetail:
    """One proposal; only its proposer and the super admin see it."""

    return await service.proposal(context, proposal_id)


@proposals_router.post(
    "/{proposal_id}/withdraw", response_model=RuleProposalDetail, dependencies=AnyReviewRole
)
async def withdraw_proposal(
    proposal_id: ProposalId, context: CurrentContext, service: Service
) -> RuleProposalDetail:
    """The proposer withdraws a pending proposal (Requirement 4)."""

    return await service.withdraw(context, proposal_id)


@proposals_router.post(
    "/{proposal_id}/approve", response_model=RuleProposalDetail, dependencies=SuperAdmin
)
async def approve_proposal(
    proposal_id: ProposalId, context: CurrentContext, service: Service
) -> RuleProposalDetail:
    """Publish the proposal as a new version and write it to the draft (Requirement 5)."""

    return await service.approve(context, proposal_id)


@proposals_router.post(
    "/{proposal_id}/reject", response_model=RuleProposalDetail, dependencies=SuperAdmin
)
async def reject_proposal(
    proposal_id: ProposalId, body: DecisionReason, context: CurrentContext, service: Service
) -> RuleProposalDetail:
    """Reject a pending proposal with a reason its proposer sees (Requirement 5)."""

    return await service.reject(context, proposal_id, body.reason)
