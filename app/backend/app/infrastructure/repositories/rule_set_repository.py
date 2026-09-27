"""Tenant-scoped persistence of the rule-set draft and its immutable published versions."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, union
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.rule_set import (
    RulePriorityGroup,
    RuleSetDraft,
    RuleSetDraftRule,
    RuleSetVersion,
    RuleSetVersionRule,
)
from app.domain.models.user import User
from app.domain.rule_set import Rule, RuleGroups


@dataclass(frozen=True, slots=True)
class VersionRow:
    """A published version with its rule counts and the publisher's display name."""

    version: RuleSetVersion
    critical_count: int
    normal_count: int
    published_by_name: str | None


def _groups(rows: Sequence[RuleSetDraftRule | RuleSetVersionRule]) -> RuleGroups:
    ordered = sorted(rows, key=lambda row: row.position)
    return RuleGroups(
        critical=tuple(
            Rule(row.rule_code, row.rule_text, row.requires_metadata)
            for row in ordered
            if row.priority_group == RulePriorityGroup.CRITICAL.value
        ),
        normal=tuple(
            Rule(row.rule_code, row.rule_text, row.requires_metadata)
            for row in ordered
            if row.priority_group == RulePriorityGroup.NORMAL.value
        ),
    )


class RuleSetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_draft(self, tenant_id: int) -> RuleSetDraft | None:
        statement = select(RuleSetDraft).where(
            RuleSetDraft.tenant_id == tenant_id, RuleSetDraft.is_deleted.is_(False)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def lock_draft(self, tenant_id: int, *, actor_user_id: int) -> RuleSetDraft:
        """Return the tenant draft locked for this transaction, creating it on first use."""

        await self.session.execute(
            insert(RuleSetDraft)
            .values(tenant_id=tenant_id, created_by=actor_user_id, updated_by=actor_user_id)
            .on_conflict_do_nothing(index_elements=[RuleSetDraft.tenant_id])
        )
        draft = await self.session.scalar(
            select(RuleSetDraft)
            .where(RuleSetDraft.tenant_id == tenant_id, RuleSetDraft.is_deleted.is_(False))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if draft is None:  # pragma: no cover - the insert above guarantees the row
            raise RuntimeError("rule-set draft is missing after creation")
        return draft

    async def draft_rules(self, draft: RuleSetDraft) -> RuleGroups:
        rows = await self.session.scalars(
            select(RuleSetDraftRule).where(
                RuleSetDraftRule.rule_set_draft_id == draft.rule_set_draft_id,
                RuleSetDraftRule.is_deleted.is_(False),
            )
        )
        return _groups(list(rows))

    async def used_codes(self, tenant_id: int) -> frozenset[str]:
        """Every code ever stored for the tenant: live and removed draft rules and versions."""

        draft_codes = (
            select(RuleSetDraftRule.rule_code)
            .join(RuleSetDraft)
            .where(RuleSetDraft.tenant_id == tenant_id)
        )
        version_codes = (
            select(RuleSetVersionRule.rule_code)
            .join(RuleSetVersion)
            .where(RuleSetVersion.tenant_id == tenant_id)
        )
        return frozenset(await self.session.scalars(union(draft_codes, version_codes)))

    async def replace_draft_rules(
        self, draft: RuleSetDraft, rules: RuleGroups, *, actor_user_id: int, now: datetime
    ) -> None:
        """Store the draft; rules left out are soft-deleted so their codes stay used."""

        existing = {
            row.rule_code: row
            for row in await self.session.scalars(
                select(RuleSetDraftRule).where(
                    RuleSetDraftRule.rule_set_draft_id == draft.rule_set_draft_id
                )
            )
        }
        kept = rules.codes
        for code, row in existing.items():
            if code not in kept and not row.is_deleted:
                row.is_deleted = True
                row.deleted_at = now
                row.deleted_by = actor_user_id
                row.updated_by = actor_user_id
        for group, members in rules.grouped():
            for position, rule in enumerate(members):
                stored = existing.get(rule.code)
                if stored is None:
                    self.session.add(
                        RuleSetDraftRule(
                            rule_set_draft_id=draft.rule_set_draft_id,
                            rule_code=rule.code,
                            priority_group=group.value,
                            position=position,
                            rule_text=rule.text,
                            requires_metadata=rule.requires_metadata,
                            created_by=actor_user_id,
                            updated_by=actor_user_id,
                        )
                    )
                    continue
                stored.priority_group = group.value
                stored.position = position
                stored.rule_text = rule.text
                stored.requires_metadata = rule.requires_metadata
                stored.updated_by = actor_user_id
        await self.session.flush()

    async def latest_version(self, tenant_id: int) -> RuleSetVersion | None:
        statement = (
            select(RuleSetVersion)
            .where(RuleSetVersion.tenant_id == tenant_id, RuleSetVersion.is_deleted.is_(False))
            .order_by(RuleSetVersion.number.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def version_by_number(self, tenant_id: int, number: int) -> RuleSetVersion | None:
        statement = select(RuleSetVersion).where(
            RuleSetVersion.tenant_id == tenant_id,
            RuleSetVersion.number == number,
            RuleSetVersion.is_deleted.is_(False),
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def version_rules(self, version: RuleSetVersion) -> RuleGroups:
        rows = await self.session.scalars(
            select(RuleSetVersionRule).where(
                RuleSetVersionRule.rule_set_version_id == version.rule_set_version_id,
                RuleSetVersionRule.is_deleted.is_(False),
            )
        )
        return _groups(list(rows))

    async def version_row(self, version: RuleSetVersion) -> VersionRow:
        rows, _ = await self._version_rows(
            version.tenant_id, number=version.number, offset=0, limit=1
        )
        return rows[0]

    async def list_versions(
        self, tenant_id: int, *, offset: int, limit: int
    ) -> tuple[list[VersionRow], int]:
        return await self._version_rows(tenant_id, number=None, offset=offset, limit=limit)

    async def _version_rows(
        self, tenant_id: int, *, number: int | None, offset: int, limit: int
    ) -> tuple[list[VersionRow], int]:
        counts = (
            select(
                RuleSetVersionRule.rule_set_version_id,
                func.count()
                .filter(RuleSetVersionRule.priority_group == RulePriorityGroup.CRITICAL.value)
                .label("critical_count"),
                func.count()
                .filter(RuleSetVersionRule.priority_group == RulePriorityGroup.NORMAL.value)
                .label("normal_count"),
            )
            .where(RuleSetVersionRule.is_deleted.is_(False))
            .group_by(RuleSetVersionRule.rule_set_version_id)
            .subquery()
        )
        filters = [RuleSetVersion.tenant_id == tenant_id, RuleSetVersion.is_deleted.is_(False)]
        if number is not None:
            filters.append(RuleSetVersion.number == number)
        total = await self.session.scalar(
            select(func.count()).select_from(RuleSetVersion).where(*filters)
        )
        result = await self.session.execute(
            select(
                RuleSetVersion,
                func.coalesce(counts.c.critical_count, 0),
                func.coalesce(counts.c.normal_count, 0),
                User.display_name,
            )
            .outerjoin(counts, counts.c.rule_set_version_id == RuleSetVersion.rule_set_version_id)
            .outerjoin(User, User.user_id == RuleSetVersion.published_by_user_id)
            .where(*filters)
            .order_by(RuleSetVersion.number.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = [
            VersionRow(version, int(critical), int(normal), name)
            for version, critical, normal, name in result.all()
        ]
        return rows, int(total or 0)

    async def add_version(
        self,
        *,
        tenant_id: int,
        number: int,
        rules: RuleGroups,
        digest: str,
        source: str,
        published_at: datetime,
        publisher_user_id: int | None,
    ) -> RuleSetVersion:
        version = RuleSetVersion(
            tenant_id=tenant_id,
            number=number,
            published_at=published_at,
            published_by_user_id=publisher_user_id,
            source=source,
            content_sha256=digest,
            created_by=publisher_user_id,
            updated_by=publisher_user_id,
        )
        self.session.add(version)
        await self.session.flush()
        for group, members in rules.grouped():
            for position, rule in enumerate(members):
                self.session.add(
                    RuleSetVersionRule(
                        rule_set_version_id=version.rule_set_version_id,
                        rule_code=rule.code,
                        priority_group=group.value,
                        position=position,
                        rule_text=rule.text,
                        requires_metadata=rule.requires_metadata,
                        created_by=publisher_user_id,
                        updated_by=publisher_user_id,
                    )
                )
        await self.session.flush()
        return version
