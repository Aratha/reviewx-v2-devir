"""Rule-set draft editing, publishing and published-version reading.

sql-review/PRDs/001-rule-management Requirement 1-8. Save and publish lock the tenant draft row,
so concurrent requests serialize: a stale ``base_revision`` receives 409 and two publishes of the
same draft produce one version. Rule text and draft content are never logged.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.models.rule_set import RuleSetVersion, RuleSetVersionSource
from app.domain.models.tenant import Tenant
from app.domain.rule_set import (
    PublishedRuleSet,
    Rule,
    RuleGroups,
    RuleSetValidationError,
    content_sha256,
    format_rule_code,
    next_rule_number_after,
    normalize_draft,
)
from app.infrastructure.repositories.rule_set_repository import (
    RuleSetRepository,
    VersionRow,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.rule_set.contracts import (
    RuleItem,
    RuleSetVersionDetail,
    RuleSetVersionPage,
    RuleSetVersionSummary,
    RuleSetWorkspace,
)
from app.services.request_scope import acting_user, active_tenant

logger = logging.getLogger("app.rule_set")

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


def _draft_conflict() -> ApplicationError:
    return ApplicationError(
        status.HTTP_409_CONFLICT,
        "rule_set_draft_conflict",
        "Kurallar başka biri tarafından değiştirildi; sayfayı yenileyin.",
    )


def no_published_rule_set() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "no_published_rule_set", "Henüz yayımlanmış kural yok."
    )


def _version_not_found() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "rule_set_version_not_found", "Kural sürümü bulunamadı."
    )


def _invalid(error: RuleSetValidationError) -> ApplicationError:
    return ApplicationError(status.HTTP_422_UNPROCESSABLE_CONTENT, error.code, error.message)


def _items(rules: tuple[Rule, ...]) -> list[RuleItem]:
    return [
        RuleItem(id=rule.code, text=rule.text, requires_metadata=rule.requires_metadata)
        for rule in rules
    ]


def _summary(row: VersionRow) -> RuleSetVersionSummary:
    return RuleSetVersionSummary(
        number=row.version.number,
        published_at=row.version.published_at,
        published_by_name=row.published_by_name,
        source=RuleSetVersionSource(row.version.source).value,
        critical_count=row.critical_count,
        normal_count=row.normal_count,
    )


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    version: RuleSetVersionDetail
    created: bool


class RuleSetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rules = RuleSetRepository(session)
        self.users = UserRepository(session)

    async def workspace(self, context: RequestContext) -> RuleSetWorkspace:
        tenant = await active_tenant(self.users, context)
        return await self._workspace(tenant)

    async def save_draft(
        self,
        context: RequestContext,
        *,
        base_revision: int,
        critical: list[RuleItem],
        normal: list[RuleItem],
    ) -> RuleSetWorkspace:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user(self.users, context)
        try:
            submitted = normalize_draft(
                [Rule(item.id, item.text, item.requires_metadata) for item in critical],
                [Rule(item.id, item.text, item.requires_metadata) for item in normal],
            )
        except RuleSetValidationError as error:
            raise _invalid(error) from None
        draft = await self.rules.lock_draft(tenant.tenant_id, actor_user_id=actor.user_id)
        if draft.revision != base_revision:
            raise _draft_conflict()
        current = await self.rules.draft_rules(draft)
        try:
            next_number = next_rule_number_after(
                submitted,
                current_codes=current.codes,
                used_codes=await self.rules.used_codes(tenant.tenant_id),
                next_rule_number=draft.next_rule_number,
            )
        except RuleSetValidationError as error:
            raise _invalid(error) from None
        now = datetime.now(UTC)
        await self.rules.replace_draft_rules(draft, submitted, actor_user_id=actor.user_id, now=now)
        draft.revision += 1
        draft.next_rule_number = next_number
        draft.updated_by = actor.user_id
        draft.updated_at = now
        await self.session.flush()
        log_event(
            logger,
            "rule_set.draft_saved",
            revision=draft.revision,
            critical_count=len(submitted.critical),
            normal_count=len(submitted.normal),
            user_public_id=actor.public_id,
        )
        return await self._workspace(tenant)

    async def publish(self, context: RequestContext, *, base_revision: int) -> PublishOutcome:
        tenant = await active_tenant(self.users, context)
        actor = await acting_user(self.users, context)
        draft = await self.rules.lock_draft(tenant.tenant_id, actor_user_id=actor.user_id)
        if draft.revision != base_revision:
            raise _draft_conflict()
        rules = await self.rules.draft_rules(draft)
        if rules.is_empty:
            raise ApplicationError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "rule_set_empty",
                "Hiç kural içermeyen taslak yayımlanamaz.",
            )
        digest = content_sha256(rules)
        latest = await self.rules.latest_version(tenant.tenant_id)
        created = latest is None or latest.content_sha256 != digest
        if created:
            version = await self.rules.add_version(
                tenant_id=tenant.tenant_id,
                number=1 if latest is None else latest.number + 1,
                rules=rules,
                digest=digest,
                source=RuleSetVersionSource.USER_INTERFACE.value,
                published_at=datetime.now(UTC),
                publisher_user_id=actor.user_id,
            )
        else:
            assert latest is not None
            version = latest
        log_event(
            logger,
            "rule_set.version_published",
            number=version.number,
            critical_count=len(rules.critical),
            normal_count=len(rules.normal),
            content_sha256=digest,
            created=created,
            user_public_id=actor.public_id,
        )
        return PublishOutcome(await self._detail(version), created)

    async def list_versions(
        self, context: RequestContext, *, page: int, page_size: int
    ) -> RuleSetVersionPage:
        tenant = await active_tenant(self.users, context)
        rows, total = await self.rules.list_versions(
            tenant.tenant_id, offset=(page - 1) * page_size, limit=page_size
        )
        return RuleSetVersionPage(
            items=[_summary(row) for row in rows], page=page, page_size=page_size, total=total
        )

    async def version(self, context: RequestContext, number: int) -> RuleSetVersionDetail:
        tenant = await active_tenant(self.users, context)
        version = await self.rules.version_by_number(tenant.tenant_id, number)
        if version is None:
            raise _version_not_found()
        return await self._detail(version)

    async def latest_version(self, context: RequestContext) -> RuleSetVersionDetail:
        tenant = await active_tenant(self.users, context)
        version = await self.rules.latest_version(tenant.tenant_id)
        if version is None:
            raise no_published_rule_set()
        return await self._detail(version)

    async def latest_published_rule_set(self, tenant_id: int) -> PublishedRuleSet | None:
        """The single read for review runs (Requirement 7): call once when a run starts.

        None means no version was ever published, and the review must not start.
        """

        version = await self.rules.latest_version(tenant_id)
        if version is None:
            return None
        return PublishedRuleSet(
            version_id=version.rule_set_version_id,
            number=version.number,
            rules=await self.rules.version_rules(version),
        )

    async def _workspace(self, tenant: Tenant) -> RuleSetWorkspace:
        draft = await self.rules.get_draft(tenant.tenant_id)
        rules = RuleGroups() if draft is None else await self.rules.draft_rules(draft)
        latest = await self.rules.latest_version(tenant.tenant_id)
        summary = None if latest is None else _summary(await self.rules.version_row(latest))
        differs = (
            not rules.is_empty if latest is None else latest.content_sha256 != content_sha256(rules)
        )
        return RuleSetWorkspace(
            revision=0 if draft is None else draft.revision,
            critical=_items(rules.critical),
            normal=_items(rules.normal),
            latest_version=summary,
            draft_differs=differs,
            next_rule_id=format_rule_code(1 if draft is None else draft.next_rule_number),
        )

    async def _detail(self, version: RuleSetVersion) -> RuleSetVersionDetail:
        row = await self.rules.version_row(version)
        rules = await self.rules.version_rules(version)
        return RuleSetVersionDetail(
            **_summary(row).model_dump(),
            critical=_items(rules.critical),
            normal=_items(rules.normal),
        )
