"""Review history, false-positive marks, deletion, retention and exports.

sql-review/PRDs/005-review-history-export. A reviewer sees and changes only their own runs; the
rule manager also reads every run of the tenant but changes none (Decision 1). A run the caller
may not see answers 404 as if it did not exist. SQL text is returned only by the SQL export;
descriptions, snippets and SQL never reach a log line.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.domain.models.review import (
    ReviewFinding,
    ReviewRuleResult,
    ReviewRunKind,
    ReviewRunObject,
    ReviewRunStatus,
)
from app.domain.models.role import ROLE_RULE_MANAGER
from app.domain.models.user import User
from app.domain.review import SCRIPT_DEFAULT_LABEL
from app.infrastructure.repositories.review_repository import (
    ReviewRepository,
    RunResults,
    RunRow,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.review_runs.contracts import (
    DeletedRuns,
    FalsePositiveState,
    ReviewRunDetail,
    ReviewRunPage,
    ReviewRunSummary,
)
from app.schemas.reviews.contracts import FindingItem, ObjectResultItem, RuleResultItem
from app.services.request_scope import acting_user, active_tenant
from app.services.review_export import (
    ExportFinding,
    ExportObject,
    ExportRuleResult,
    build_results_csv,
    build_sql_export,
)

logger = logging.getLogger("app.review_history")

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
# Several runs a day keep the "at least once a day" promise across restarts.
RETENTION_INTERVAL_SECONDS = 6 * 60 * 60


def _not_found() -> ApplicationError:
    return ApplicationError(
        status.HTTP_404_NOT_FOUND, "review_run_not_found", "İnceleme koşumu bulunamadı."
    )


def _not_owner() -> ApplicationError:
    return ApplicationError(
        status.HTTP_403_FORBIDDEN,
        "review_run_not_owner",
        "Yalnız koşumu başlatan kişi bu işlemi yapabilir.",
    )


@dataclass(frozen=True, slots=True)
class ExportFile:
    filename: str
    media_type: str
    content: str


def _database_label(objects: list[ReviewRunObject]) -> str:
    databases = list(dict.fromkeys(item.database_name or "" for item in objects))
    if len(databases) == 1:
        return databases[0]
    return f"{len(databases)} veritabanı ({', '.join(databases)})"


def run_title(
    kind: str, status_value: str, label: str | None, objects: list[ReviewRunObject]
) -> tuple[str, str | None]:
    """Title and subtitle in the previous application's history format."""

    if kind == ReviewRunKind.SCRIPT.value:
        return label or SCRIPT_DEFAULT_LABEL, None
    targets = [
        f"[{item.database_name or ''}] {item.schema_name}.{item.object_name} ({item.type_code})"
        for item in objects
    ]
    database = _database_label(objects)
    if status_value == ReviewRunStatus.FAILED.value:
        return f"{database} · hata", ", ".join(targets[:4])
    subtitle = (
        ", ".join(targets) if len(targets) <= 3 else f"{', '.join(targets[:3])} +{len(targets) - 3}"
    )
    return f"{database} · {len(objects)} nesne", subtitle


def _summary_fields(row: RunRow, objects: list[ReviewRunObject], actor: User) -> dict[str, object]:
    run = row.run
    title, subtitle = run_title(run.kind, run.status, run.label, objects)
    return {
        "id": run.public_id,
        "kind": run.kind,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "title": title,
        "subtitle": subtitle,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "rule_version": row.rule_version,
        "object_count": run.object_count,
        "finding_count": row.finding_count,
        "owner_display_name": row.owner_display_name,
        "owned": run.owner_user_id == actor.user_id,
    }


def _rule_result_item(result: ReviewRuleResult) -> RuleResultItem:
    return RuleResultItem.model_validate(
        {
            "id": result.public_id,
            "rule_id": result.rule_code,
            "tier": result.priority_group,
            "status": result.status,
            "severity": result.severity,
            "decision_basis": result.decision_basis,
            "description": result.explanation or "",
            "line_reference": result.line_reference or "",
            "code_snippet": result.code_snippet or "",
            "false_positive": result.false_positive,
        }
    )


def _finding_item(finding: ReviewFinding) -> FindingItem:
    return FindingItem.model_validate(
        {
            "id": finding.public_id,
            "rule_id": finding.rule_code,
            "severity": finding.severity,
            "description": finding.description,
            "line_reference": finding.line_reference or "",
            "code_snippet": finding.code_snippet or "",
            "false_positive": finding.false_positive,
        }
    )


def _object_results(results: RunResults) -> list[ObjectResultItem]:
    items: list[ObjectResultItem] = []
    for item in results.objects:
        rule_results = results.rule_results.get(item.review_run_object_id, [])
        items.append(
            ObjectResultItem(
                database=item.database_name or "",
                schema=item.schema_name,
                name=item.object_name,
                object_type=item.object_type,
                type_code=item.type_code,
                error_code=item.error_code,
                error_message=item.error_message,
                parse_warning=item.parse_warning,
                rule_results=[_rule_result_item(result) for result in rule_results],
                findings=[
                    _finding_item(finding)
                    for result in rule_results
                    for finding in results.findings.get(result.review_rule_result_id, [])
                ],
            )
        )
    return items


def _export_objects(results: RunResults) -> list[ExportObject]:
    objects: list[ExportObject] = []
    for item in results.objects:
        rule_results = results.rule_results.get(item.review_run_object_id, [])
        objects.append(
            ExportObject(
                database=item.database_name or "",
                schema=item.schema_name,
                name=item.object_name,
                object_type=item.object_type,
                error=item.error_message or "",
                parse_warning=item.parse_warning or "",
                rule_results=[
                    ExportRuleResult(
                        rule_id=result.rule_code,
                        tier=result.priority_group,
                        status=result.status,
                        severity=result.severity or "",
                        description=result.explanation or "",
                        line_reference=result.line_reference or "",
                        code_snippet=result.code_snippet or "",
                        false_positive=result.false_positive,
                    )
                    for result in rule_results
                ],
                findings=[
                    ExportFinding(
                        rule_id=finding.rule_code,
                        severity=finding.severity,
                        description=finding.description,
                        line_reference=finding.line_reference or "",
                        code_snippet=finding.code_snippet or "",
                        false_positive=finding.false_positive,
                    )
                    for result in rule_results
                    for finding in results.findings.get(result.review_rule_result_id, [])
                ],
                source_sql=item.source_sql or "",
            )
        )
    return objects


def _timestamp_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _iso_ms(moment: datetime) -> str:
    """JavaScript ``toISOString``: UTC with milliseconds and a trailing Z."""

    return (
        moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
    )


class ReviewHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reviews = ReviewRepository(session)
        self.users = UserRepository(session)

    async def _caller(self, context: RequestContext) -> tuple[int, User]:
        tenant = await active_tenant(self.users, context)
        return tenant.tenant_id, await acting_user(self.users, context)

    async def _visible(self, context: RequestContext, run_id: str) -> tuple[RunRow, User]:
        tenant_id, actor = await self._caller(context)
        row = await self.reviews.get_run(tenant_id, run_id)
        if row is None or (
            row.run.owner_user_id != actor.user_id and not context.has_role(ROLE_RULE_MANAGER)
        ):
            raise _not_found()
        return row, actor

    async def _owned(self, context: RequestContext, run_id: str) -> tuple[RunRow, User]:
        row, actor = await self._visible(context, run_id)
        if row.run.owner_user_id != actor.user_id:
            raise _not_owner()
        return row, actor

    async def list_runs(
        self, context: RequestContext, *, scope: str, page: int, page_size: int
    ) -> ReviewRunPage:
        tenant_id, actor = await self._caller(context)
        if scope == "all" and not context.has_role(ROLE_RULE_MANAGER):
            raise ApplicationError(
                status.HTTP_403_FORBIDDEN,
                "review_scope_forbidden",
                "Tüm koşumları yalnız kural yöneticisi görebilir.",
            )
        rows, total = await self.reviews.list_runs(
            tenant_id,
            owner_user_id=None if scope == "all" else actor.user_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        objects = await self.reviews.objects_of_runs([row.run.review_run_id for row in rows])
        return ReviewRunPage(
            items=[
                ReviewRunSummary.model_validate(
                    _summary_fields(row, objects[row.run.review_run_id], actor)
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def detail(self, context: RequestContext, run_id: str) -> ReviewRunDetail:
        row, actor = await self._visible(context, run_id)
        results = await self.reviews.results_of_run(row.run.review_run_id)
        completed = row.run.status == ReviewRunStatus.COMPLETED.value
        return ReviewRunDetail.model_validate(
            {
                **_summary_fields(row, results.objects, actor),
                "label": row.run.label,
                "results": _object_results(results) if completed else [],
            }
        )

    async def set_finding_false_positive(
        self, context: RequestContext, run_id: str, finding_id: str, value: bool
    ) -> FalsePositiveState:
        row, actor = await self._owned(context, run_id)
        finding = await self.reviews.finding_of_run(row.run.review_run_id, finding_id)
        if finding is None:
            raise ApplicationError(
                status.HTTP_404_NOT_FOUND, "review_finding_not_found", "Bulgu bulunamadı."
            )
        self._mark(finding, value, actor)
        await self.session.flush()
        return FalsePositiveState(
            id=finding.public_id,
            false_positive=finding.false_positive,
            changed_at=finding.false_positive_changed_at,
        )

    async def set_rule_result_false_positive(
        self, context: RequestContext, run_id: str, rule_result_id: str, value: bool
    ) -> FalsePositiveState:
        row, actor = await self._owned(context, run_id)
        found = await self.reviews.rule_result_of_run(row.run.review_run_id, rule_result_id)
        if found is None:
            raise ApplicationError(
                status.HTTP_404_NOT_FOUND,
                "review_rule_result_not_found",
                "Kural sonucu bulunamadı.",
            )
        result, finding_count = found
        if result.status != "FAIL" or finding_count:
            raise ApplicationError(
                status.HTTP_409_CONFLICT,
                "false_positive_not_applicable",
                "Yalnız bulgusu olmayan başarısız kural sonucu işaretlenebilir.",
            )
        self._mark(result, value, actor)
        await self.session.flush()
        return FalsePositiveState(
            id=result.public_id,
            false_positive=result.false_positive,
            changed_at=result.false_positive_changed_at,
        )

    @staticmethod
    def _mark(target: ReviewFinding | ReviewRuleResult, value: bool, actor: User) -> None:
        # Requirement 4: sending the current value again changes nothing.
        if target.false_positive == value:
            return
        target.false_positive = value
        target.false_positive_changed_by = actor.user_id
        target.false_positive_changed_at = datetime.now(UTC)
        target.updated_by = actor.user_id

    async def delete_run(self, context: RequestContext, run_id: str) -> None:
        row, actor = await self._owned(context, run_id)
        run = await self.reviews.lock_run(row.run.review_run_id)
        if run is None:
            raise _not_found()
        if run.status == ReviewRunStatus.RUNNING.value:
            raise ApplicationError(
                status.HTTP_409_CONFLICT,
                "review_run_in_progress",
                "Süren bir inceleme silinemez.",
            )
        await self.reviews.delete_run(run.review_run_id)
        log_event(
            logger,
            "review_history.deleted",
            run_id=row.run.public_id,
            count=1,
            user_public_id=actor.public_id,
        )

    async def delete_own_runs(self, context: RequestContext) -> DeletedRuns:
        tenant_id, actor = await self._caller(context)
        count = await self.reviews.delete_finished_runs_of_owner(tenant_id, actor.user_id)
        log_event(
            logger,
            "review_history.deleted",
            run_id=None,
            count=count,
            user_public_id=actor.public_id,
        )
        return DeletedRuns(deleted_count=count)

    async def _export_source(
        self, context: RequestContext, run_id: str
    ) -> tuple[RunRow, RunResults]:
        row, _ = await self._visible(context, run_id)
        return row, await self.reviews.results_of_run(row.run.review_run_id)

    async def export_csv(self, context: RequestContext, run_id: str) -> ExportFile:
        row, results = await self._export_source(context, run_id)
        now = datetime.now(UTC)
        completed = row.run.status == ReviewRunStatus.COMPLETED.value
        objects = _export_objects(results) if completed else []
        database = (
            _database_label(results.objects) if row.run.kind == ReviewRunKind.OBJECT.value else ""
        )
        content = build_results_csv(
            objects,
            generated_at=_iso_ms(now),
            database=database,
            review_error=None if objects else row.run.error_message,
        )
        log_event(
            logger,
            "review_history.exported",
            run_id=row.run.public_id,
            format="csv",
            rows=content.count("\r\n"),
        )
        return ExportFile(f"sql-review-{_timestamp_ms(now)}.csv", "text/csv", content)

    async def export_sql(self, context: RequestContext, run_id: str) -> ExportFile:
        row, results = await self._export_source(context, run_id)
        completed = row.run.status == ReviewRunStatus.COMPLETED.value
        content = (
            build_sql_export(
                _export_objects(results), script=row.run.kind == ReviewRunKind.SCRIPT.value
            )
            if completed
            else None
        )
        if content is None:
            raise ApplicationError(
                status.HTTP_409_CONFLICT,
                "sql_text_unavailable",
                "Bu koşum için saklanmış SQL metni yok.",
            )
        log_event(
            logger,
            "review_history.exported",
            run_id=row.run.public_id,
            format="sql",
            objects=sum(1 for item in results.objects if item.source_sql),
        )
        now = datetime.now(UTC)
        return ExportFile(f"sql-review-source-{_timestamp_ms(now)}.sql", "application/sql", content)


@dataclass(frozen=True, slots=True)
class RetentionRun:
    outcome: str
    deleted: int


async def purge_expired_review_runs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int,
    now: datetime | None = None,
) -> RetentionRun:
    """Requirement 6: delete runs finished before the retention window; 'skipped' if locked."""

    started = time.monotonic()
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    run = RetentionRun("failed", 0)
    try:
        async with session_factory() as session, session.begin():
            reviews = ReviewRepository(session)
            if await reviews.try_retention_lock():
                run = RetentionRun("ok", await reviews.delete_finished_before(cutoff))
            else:
                run = RetentionRun("skipped", 0)
    except Exception as error:  # noqa: BLE001 - the job reports and retries on its next run
        log_event(
            logger,
            "review_history.retention_run",
            outcome="failed",
            deleted=0,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=type(error).__name__,
        )
        return run
    log_event(
        logger,
        "review_history.retention_run",
        outcome=run.outcome,
        deleted=run.deleted,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return run


async def run_review_history_retention(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    retention_days: int,
    interval_seconds: float = RETENTION_INTERVAL_SECONDS,
) -> None:
    """Background task of the backend process: purge now, then every interval until cancelled."""

    while True:
        await purge_expired_review_runs(session_factory, retention_days=retention_days)
        await asyncio.sleep(interval_seconds)
