"""LLM call summaries: recording, the rule manager's read API and the 90-day retention job.

sql-review/PRDs/006-llm-connection Requirement 10-12 and 14. Every attempt produces exactly one
``llm.call`` log event and one summary row with metadata only. A failed write never stops a
review; it logs ``llm_call_summary.write_failed`` with the error type. The retention job runs
inside the backend process, at least daily; an advisory lock lets one copy delete at a time.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ApplicationError
from app.core.logging import log_event
from app.core.request_context import RequestContext
from app.core.telemetry import record_llm_call_summary_write_failure
from app.domain.llm import LlmCallAttempt
from app.domain.models.llm_call import LLM_CALL_SUMMARY_RETENTION_DAYS, LlmCallSummary
from app.infrastructure.repositories.llm_call_summary_repository import (
    LlmCallSummaryRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.schemas.llm.contracts import (
    ChatApiValue,
    LlmCallOutcomeValue,
    LlmCallSummaryItem,
    LlmCallSummaryPage,
)
from app.services.request_scope import active_tenant

logger = logging.getLogger("app.llm")

DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 500
# Several runs a day keep the "at least once a day" promise across restarts.
RETENTION_INTERVAL_SECONDS = 6 * 60 * 60


class LlmCallSummaryRecorder:
    """LlmCallRecorder writing each attempt in its own short transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, attempt: LlmCallAttempt) -> None:
        target = attempt.target
        log_event(
            logger,
            "llm.call",
            public_id=attempt.public_id,
            started_at=attempt.started_at.isoformat(),
            review_run_id=target.review_run_public_id,
            object_label=target.object_label,
            rule_id=target.rule_code,
            part_index=target.part_index,
            attempt=attempt.attempt,
            chat_api=attempt.chat_api.value,
            model=attempt.model,
            endpoint_host=attempt.endpoint_host,
            streamed=attempt.streamed,
            outcome=attempt.outcome.value,
            http_status=attempt.http_status,
            duration_ms=attempt.duration_ms,
            completion_tokens=attempt.completion_tokens,
            prompt_tokens=attempt.prompt_tokens,
            response_chars=attempt.response_chars,
        )
        try:
            async with self._session_factory() as session:
                await LlmCallSummaryRepository(session).add(attempt)
                await session.commit()
        except Exception as error:  # noqa: BLE001 - Requirement 10: the review continues
            log_event(logger, "llm_call_summary.write_failed", error_type=type(error).__name__)
            record_llm_call_summary_write_failure()


def _item(summary: LlmCallSummary, review_run_public_id: str | None) -> LlmCallSummaryItem:
    return LlmCallSummaryItem(
        public_id=summary.public_id,
        started_at=summary.started_at,
        review_run_id=review_run_public_id,
        object_label=summary.object_label,
        rule_id=summary.rule_code,
        part_index=summary.part_index,
        attempt=summary.attempt,
        chat_api=cast(ChatApiValue, summary.chat_api),
        model=summary.model,
        endpoint_host=summary.endpoint_host,
        streamed=summary.streamed,
        outcome=cast(LlmCallOutcomeValue, summary.outcome),
        http_status=summary.http_status,
        duration_ms=summary.duration_ms,
        completion_tokens=summary.completion_tokens,
        prompt_tokens=summary.prompt_tokens,
        response_chars=summary.response_chars,
    )


class LlmCallSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.summaries = LlmCallSummaryRepository(session)
        self.users = UserRepository(session)

    async def list_recent(self, context: RequestContext, *, limit: int) -> LlmCallSummaryPage:
        tenant = await active_tenant(self.users, context)
        rows, total = await self.summaries.list_recent(tenant.tenant_id, limit=limit)
        return LlmCallSummaryPage(
            items=[_item(summary, run) for summary, run in rows], limit=limit, total=total
        )

    async def get(self, context: RequestContext, public_id: str) -> LlmCallSummaryItem:
        tenant = await active_tenant(self.users, context)
        row = await self.summaries.get(tenant.tenant_id, public_id)
        if row is None:
            raise ApplicationError(
                status.HTTP_404_NOT_FOUND, "llm_call_not_found", "LLM çağrı özeti bulunamadı."
            )
        return _item(*row)


@dataclass(frozen=True, slots=True)
class RetentionRun:
    outcome: str
    deleted: int


async def purge_expired_llm_call_summaries(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> RetentionRun:
    """Delete summaries started more than 90 days ago; 'skipped' when another copy runs."""

    started = time.monotonic()
    cutoff = (now or datetime.now(UTC)) - timedelta(days=LLM_CALL_SUMMARY_RETENTION_DAYS)
    run = RetentionRun("failed", 0)
    try:
        async with session_factory() as session, session.begin():
            summaries = LlmCallSummaryRepository(session)
            if await summaries.try_retention_lock():
                run = RetentionRun("ok", await summaries.delete_started_before(cutoff))
            else:
                run = RetentionRun("skipped", 0)
    except Exception as error:  # noqa: BLE001 - the job reports and retries on its next run
        log_event(
            logger,
            "llm_call_summary.retention_run",
            outcome="failed",
            deleted=0,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_type=type(error).__name__,
        )
        return run
    log_event(
        logger,
        "llm_call_summary.retention_run",
        outcome=run.outcome,
        deleted=run.deleted,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return run


async def run_llm_call_retention(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: float = RETENTION_INTERVAL_SECONDS,
) -> None:
    """Background task of the backend process: purge now, then every interval until cancelled."""

    while True:
        await purge_expired_llm_call_summaries(session_factory)
        await asyncio.sleep(interval_seconds)
