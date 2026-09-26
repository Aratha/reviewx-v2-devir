"""A failed summary write never stops a review; the retention job keeps running.

sql-review/PRDs/006-llm-connection Requirement 10 and 14 (Acceptance 2).
"""

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.llm import LlmCallAttempt, LlmCallTarget
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.services import llm_call_summary_service
from app.services.llm_call_summary_service import (
    LlmCallSummaryRecorder,
    RetentionRun,
    run_llm_call_retention,
)

pytestmark = pytest.mark.unit


class _BrokenSessions:
    """A session factory whose database is unreachable."""

    def __call__(self) -> Any:
        raise ConnectionRefusedError("postgres://user:parola@db/x unreachable")


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    captured: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = Handler()
    logger = logging.getLogger("app.llm")
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield captured
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


async def test_a_failed_write_is_reported_by_type_and_the_call_continues(
    records: list[logging.LogRecord],
) -> None:
    recorder = LlmCallSummaryRecorder(_BrokenSessions())  # type: ignore[arg-type]
    attempt = LlmCallAttempt(
        public_id="p-1",
        target=LlmCallTarget(tenant_id=1, object_label="x (SCRIPT)", rule_code="Kural01"),
        started_at=datetime.now(UTC),
        attempt=1,
        chat_api=LlmChatApi.OPENAI,
        model="m",
        endpoint_host="llm.local",
        streamed=True,
        outcome=LlmCallOutcome.OK,
        http_status=200,
        duration_ms=5,
        completion_tokens=3,
        prompt_tokens=None,
        response_chars=10,
    )

    await recorder.record(attempt)

    names = [record.getMessage() for record in records]
    assert names == ["llm.call", "llm_call_summary.write_failed"]
    failure = records[1].structured_fields  # type: ignore[attr-defined]
    assert failure == {
        "event": "llm_call_summary.write_failed",
        "error_type": "ConnectionRefusedError",
    }


async def test_the_retention_job_runs_at_start_and_then_on_its_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[float] = []

    async def purge(_factory: Any, *, now: Any = None) -> RetentionRun:
        runs.append(asyncio.get_running_loop().time())
        return RetentionRun("ok", 0)

    monkeypatch.setattr(llm_call_summary_service, "purge_expired_llm_call_summaries", purge)
    task = asyncio.create_task(run_llm_call_retention(object(), interval_seconds=0.05))  # type: ignore[arg-type]
    await asyncio.sleep(0.18)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(runs) >= 3
    assert llm_call_summary_service.RETENTION_INTERVAL_SECONDS <= 24 * 60 * 60
