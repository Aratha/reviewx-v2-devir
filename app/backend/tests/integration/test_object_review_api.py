"""Object review runs through the real HTTP application and PostgreSQL.

sql-review/PRDs/003-object-review Requirement 3-7, 14-18 (Acceptance 2 and 3): checks before
the stream, the event order, the pinned rule version, stored results and SQL text, object
errors, cancellation on a lost connection, the per-user rate limit and logs without SQL.
"""

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.api.integrations import get_llm_chat
from app.db.session import async_session_factory
from app.domain.llm import LlmChatRequest, LlmEndpoint
from app.domain.models.llm_call import LlmCallSummary, LlmChatApi
from app.domain.models.review import (
    ReviewRuleResult,
    ReviewRunObject,
)
from app.domain.models.rule_set import RuleSetVersion
from app.domain.models.tenant import Tenant
from app.domain.sql_server import SqlServerError, SqlServerErrorClass
from app.infrastructure.llm.http_chat import HttpLlmChat
from app.main import app
from app.schemas.reviews.contracts import SELECTION_TECHNICAL_MAX_ITEMS
from app.services.llm_call_summary_service import LlmCallSummaryRecorder
from app.services.review_run_service import (
    LIVE_RESULTS_MAX_OBJECTS,
    interrupt_stale_runs,
)
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    Writer,
    http_response,
    write_pki,
)
from tests.fakes.review_ports import ok, rule_code_of
from tests.integration.conftest import ReviewEnv, RoleSession, SuperAdmin, sse_events
from tests.integration.review_helpers import (
    objects_of,
    result_counts,
    run_of,
    runs_of,
    stream_until,
)

pytestmark = pytest.mark.integration

MARKER = f"GIZLI-{uuid4().hex}"
DEFINITION_A = "\n".join(
    [
        "CREATE PROCEDURE dbo.usp_Load",
        "AS",
        "BEGIN",
        f"    SELECT * FROM dbo.Musteri -- {MARKER}",
        "END",
    ]
)
DEFINITION_B = f"CREATE VIEW sales.vw_Satis AS SELECT a FROM b -- {MARKER}"
SELECTION_A = {"database": "DWH", "schema": "dbo", "name": "usp_Load", "type_code": "P"}
SELECTION_B = {"database": "DWH2", "schema": "sales", "name": "vw_Satis", "type_code": "V"}


def _reply(request: LlmChatRequest) -> Any:
    """The star rule fails where the reviewed text selects every column."""

    code = rule_code_of(request)
    if "Yıldız kullanma." in request.user_content and "SELECT *" in request.user_content:
        reason = f"yıldız {MARKER}"
        return ok(
            json.dumps(
                {
                    "violations": [
                        {
                            "rule_code": code,
                            "snippet": "SELECT * FROM dbo.Musteri",
                            "reason": reason,
                        }
                    ]
                }
            )
        )
    return ok('{"violations": []}')


@pytest.fixture
def all_logs() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Handler(level=logging.DEBUG)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


def _logged_text(records: list[logging.LogRecord]) -> str:
    return "\n".join(
        f"{record.getMessage()} {getattr(record, 'structured_fields', '')} {record.args}"
        for record in records
    )


async def _ready(env: ReviewEnv, *, flagged: bool = True) -> tuple[RoleSession, int, list[str]]:
    manager = await env.sessions.rule_manager()
    version, codes = await env.publish(
        manager, [("Yıldız kullanma.", flagged)], [("Şema adı yaz.", False)]
    )
    env.catalog.definitions.update(
        {("DWH", "dbo", "usp_Load"): DEFINITION_A, ("DWH2", "sales", "vw_Satis"): DEFINITION_B}
    )
    env.catalog.metadata[("DWH", "dbo", "usp_Load")] = "dbo.Musteri(Kimlik int)"
    env.llm.responder = _reply
    return await env.sessions.reviewer(), version, codes


async def test_a_run_streams_events_in_order_and_stores_results_with_the_sql(
    review_env: ReviewEnv, all_logs: list[logging.LogRecord]
) -> None:
    reviewer, version, codes = await _ready(review_env)

    response = await review_env.object_review(reviewer, [SELECTION_A, SELECTION_B])

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache"
    events = sse_events(response.text)
    started, complete = events[0], events[-1]
    assert started["phase"] == "run_started"
    assert started["rule_version"] == version and started["objects_total"] == 2
    assert complete["phase"] == "complete" and complete["run_id"] == started["run_id"]
    for index, selection in enumerate((SELECTION_A, SELECTION_B)):
        phases = [
            event["phase"]
            for event in events
            if event.get("object_index") == index and event["phase"] != "llm_stream"
        ]
        assert phases[:6] == [
            "object_start",
            "definition_fetch",
            "sql_ready",
            "metadata_fetch",
            "metadata_ready",
            "rules_batch_start",
        ]
        assert phases[-1] == "object_done"
        assert sorted(phases[6:-1]) == ["rule_done"] * 2 + ["rule_start"] * 2
        object_event = next(event for event in events if event.get("object_index") == index)
        assert object_event["database"] == selection["database"]
        assert object_event["type_code"] == selection["type_code"]
        assert object_event["kind"] == "object"
    assert all("SELECT" not in json.dumps(event) for event in events[:-1])

    results = complete["results"]
    assert [r["database"] for r in results] == ["DWH", "DWH2"]
    first = results[0]
    assert first["object_type"] == "PROCEDURE" and first["source_sql"] == DEFINITION_A
    assert [r["rule_id"] for r in first["rule_results"]] == codes
    assert [r["status"] for r in first["rule_results"]] == ["FAIL", "PASS"]
    assert [r["status"] for r in results[1]["rule_results"]] == ["PASS", "PASS"]
    (finding,) = first["findings"]
    assert finding["rule_id"] == codes[0] and finding["line_reference"] == "Satır 4"
    assert finding["severity"] == "HIGH" and finding["false_positive"] is False
    assert first["rule_results"][1]["severity"] is None

    run = await run_of(started["run_id"])
    assert run.status == "completed" and run.kind == "object" and run.object_count == 2
    async with async_session_factory() as session:
        pinned = await session.scalar(
            select(RuleSetVersion.number).where(
                RuleSetVersion.rule_set_version_id == run.rule_set_version_id
            )
        )
    assert pinned == version
    stored = await objects_of(run)
    assert [item.source_sql for item in stored] == [DEFINITION_A, DEFINITION_B]
    stored_results, stored_findings = await result_counts(run)
    assert stored_results == 4
    assert stored_findings == sum(len(r["findings"]) for r in results)
    ids = {r["id"] for obj in results for r in obj["rule_results"]}
    async with async_session_factory() as session:
        stored_ids = set(
            await session.scalars(
                select(ReviewRuleResult.public_id)
                .join(ReviewRunObject)
                .where(ReviewRunObject.review_run_id == run.review_run_id)
            )
        )
    assert ids == stored_ids

    logged = _logged_text(all_logs)
    assert MARKER not in logged
    assert "SELECT *" not in logged
    completed = [
        record.structured_fields  # type: ignore[attr-defined]
        for record in all_logs
        if record.getMessage() == "review_run.completed"
    ]
    assert completed and completed[0]["run_id"] == run.public_id
    assert completed[0]["rule_count"] == 2 and completed[0]["object_count"] == 2


async def test_metadata_goes_only_to_the_flagged_rule(review_env: ReviewEnv) -> None:
    reviewer, _, codes = await _ready(review_env)
    response = await review_env.object_review(reviewer, [SELECTION_A])
    assert response.status_code == 200
    prompts = {
        rule_code_of(call.request): call.request.user_content for call in review_env.llm.calls
    }
    assert "dbo.Musteri(Kimlik int)" in prompts[codes[0]]
    assert "KATALOG METADATASI" not in prompts[codes[1]]
    assert review_env.catalog.calls.count(("fetch_object_metadata", "DWH", "dbo", "usp_Load")) == 1


async def test_no_metadata_is_fetched_when_no_rule_is_flagged(review_env: ReviewEnv) -> None:
    reviewer, _, _ = await _ready(review_env, flagged=False)
    events = sse_events((await review_env.object_review(reviewer, [SELECTION_A])).text)
    assert "metadata_fetch" not in [event["phase"] for event in events]
    assert not [call for call in review_env.catalog.calls if call[0] == "fetch_object_metadata"]


async def test_object_errors_are_stable_codes_and_other_objects_continue(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.catalog.definitions[("DWH", "dbo", "usp_Load")] = None
    review_env.catalog.errors[("DWH2", "sales", "vw_Satis")] = SqlServerError(
        SqlServerErrorClass.TIMEOUT, "HYT00"
    )
    review_env.catalog.definitions[("DWH", "dbo", "usp_Ok")] = DEFINITION_A
    selections = [
        SELECTION_A,
        SELECTION_B,
        {"database": "DWH", "schema": "dbo", "name": "usp_Ok", "type_code": "P"},
    ]

    events = sse_events((await review_env.object_review(reviewer, selections)).text)

    errors = [event for event in events if event["phase"] == "object_error"]
    assert [(e["object_index"], e["code"], e["message"]) for e in errors] == [
        (0, "object_not_found", "Tanım alınamadı (nesne yok veya yetki yok)."),
        (1, "sql_timeout", "SQL Server zamanında yanıt vermedi."),
    ] or sorted((e["object_index"], e["code"]) for e in errors) == [
        (0, "object_not_found"),
        (1, "sql_timeout"),
    ]
    results = events[-1]["results"]
    assert [r["error_code"] for r in results] == ["object_not_found", "sql_timeout", None]
    assert results[2]["rule_results"] and results[0]["source_sql"] is None
    run = await run_of(events[0]["run_id"])
    stored = await objects_of(run)
    assert [item.error_code for item in stored] == ["object_not_found", "sql_timeout", None]
    assert [item.source_sql is None for item in stored] == [True, True, False]


async def test_a_failed_metadata_fetch_keeps_the_review_with_a_note(review_env: ReviewEnv) -> None:
    reviewer, _, codes = await _ready(review_env)
    review_env.catalog.metadata_errors[("DWH", "dbo", "usp_Load")] = SqlServerError(
        SqlServerErrorClass.QUERY_FAILED
    )
    events = sse_events((await review_env.object_review(reviewer, [SELECTION_A])).text)
    assert events[-1]["phase"] == "complete"
    prompt = next(
        call.request.user_content
        for call in review_env.llm.calls
        if rule_code_of(call.request) == codes[0]
    )
    assert "özeti alınamadı; yalnızca SQL metnine güven" in prompt


async def test_text_above_the_limit_is_cut_with_a_warning(review_env: ReviewEnv) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.auth.use_settings(review_max_sql_chars=40)
    events = sse_events((await review_env.object_review(reviewer, [SELECTION_A])).text)
    result = events[-1]["results"][0]
    assert result["source_sql"] == DEFINITION_A[:40]
    assert result["parse_warning"].startswith("Metnin yalnız ilk 40 karakteri incelendi.")
    sql_ready = next(event for event in events if event["phase"] == "sql_ready")
    assert sql_ready["sql_length"] == len(DEFINITION_A)
    stored = await objects_of(await run_of(events[0]["run_id"]))
    assert stored[0].source_sql == DEFINITION_A[:40]


async def test_the_run_limit_bounds_llm_calls_acrossobjects_of(review_env: ReviewEnv) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.llm.run_limit = 2
    selections = [
        {"database": "DWH", "schema": "dbo", "name": f"usp_{n}", "type_code": "P"} for n in range(5)
    ]
    for n in range(5):
        review_env.catalog.definitions[("DWH", "dbo", f"usp_{n}")] = DEFINITION_A
    response = await review_env.object_review(reviewer, selections)
    assert sse_events(response.text)[-1]["phase"] == "complete"
    assert len(review_env.llm.calls) == 10
    assert review_env.llm.peak <= 2
    assert review_env.llm.runs_opened == 1


async def test_checks_before_the_stream_answer_json_and_create_no_run(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env)
    # No product limit on the selection (Decision 3). Only the technical transport bound of
    # the request remains, and it answers like any other malformed request.
    beyond_transport = [
        {"database": "DWH", "schema": "dbo", "name": f"p{n}", "type_code": "P"}
        for n in range(SELECTION_TECHNICAL_MAX_ITEMS + 1)
    ]
    cases = [
        ({"selections": []}, 422, "selection_empty"),
        ({"selections": beyond_transport}, 422, "invalid_request"),
        ({"selections": [SELECTION_A | {"type_code": "U"}]}, 422, "object_type_invalid"),
        ({"selections": [SELECTION_A | {"database": ""}]}, 422, "invalid_request"),
        ({"selections": [SELECTION_A | {"database": "msdb"}]}, 403, "database_not_allowed"),
    ]
    for body, status_code, code in cases:
        response = await review_env.auth.client.post(
            f"{review_env.prefix}/object-reviews", json=body, headers=reviewer.headers
        )
        assert response.status_code == status_code, (body, response.text)
        assert response.headers["content-type"] == "application/json"
        assert response.json()["detail"]["code"] == code
    tenant_only = {
        review_env.auth.settings.tenant_header: reviewer.headers[
            review_env.auth.settings.tenant_header
        ]
    }
    anonymous = await review_env.auth.client.post(
        f"{review_env.prefix}/object-reviews",
        json={"selections": [SELECTION_A]},
        headers=tenant_only,
    )
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"]["code"] == "not_authenticated"
    assert await runs_of(reviewer.public_id) == []
    assert review_env.catalog.calls == []
    assert review_env.llm.calls == []


def _selections(count: int) -> list[dict[str, str]]:
    return [
        {"database": "DWH", "schema": "dbo", "name": f"usp_{n:04d}", "type_code": "P"}
        for n in range(count)
    ]


def _define(env: ReviewEnv, count: int) -> None:
    for n in range(count):
        env.catalog.definitions[("DWH", "dbo", f"usp_{n:04d}")] = DEFINITION_A


def _peak_objects_in_flight(events: list[dict[str, Any]]) -> int:
    """The highest number of objects between their first event and their last one."""

    current = peak = 0
    for event in events:
        if event["phase"] == "object_start":
            current += 1
            peak = max(peak, current)
        elif event["phase"] in ("object_done", "object_error"):
            current -= 1
    return peak


async def test_more_than_fifty_objects_are_reviewed_and_stored(review_env: ReviewEnv) -> None:
    # Decision 3 (owner decision 2026-10-02): a run has no object limit.
    reviewer, _, codes = await _ready(review_env, flagged=False)
    _define(review_env, 51)

    events = sse_events((await review_env.object_review(reviewer, _selections(51))).text)

    assert events[0]["objects_total"] == 51 and events[-1]["phase"] == "complete"
    run = await run_of(events[0]["run_id"])
    assert (run.status, run.object_count) == ("completed", 51)
    assert await result_counts(run) == (51 * len(codes), 51)
    stored = await objects_of(run)
    assert [item.position for item in stored] == list(range(51))
    assert all(item.source_sql == DEFINITION_A for item in stored)


async def test_the_complete_event_carries_results_only_for_a_run_that_fits_one_page(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env, flagged=False)
    _define(review_env, LIVE_RESULTS_MAX_OBJECTS + 1)

    small = sse_events(
        (await review_env.object_review(reviewer, _selections(LIVE_RESULTS_MAX_OBJECTS))).text
    )[-1]
    large = sse_events(
        (await review_env.object_review(reviewer, _selections(LIVE_RESULTS_MAX_OBJECTS + 1))).text
    )[-1]

    assert small["results_omitted"] is False
    assert len(small["results"]) == LIVE_RESULTS_MAX_OBJECTS
    # A larger run is read from the stored run, page by page (005 Requirement 3).
    assert large == {
        "phase": "complete",
        "run_id": large["run_id"],
        "results": [],
        "results_omitted": True,
    }
    assert DEFINITION_A not in json.dumps(large)


async def test_a_thousand_objects_complete_with_a_bounded_number_in_flight(
    review_env: ReviewEnv,
) -> None:
    # Requirement 3 and 5: the run is safe at large sizes. Objects are started only as earlier
    # ones finish, so definitions are never fetched and held for the whole selection at once.
    reviewer, _, codes = await _ready(review_env, flagged=False)
    count = 1_000
    bound = review_env.auth.settings.llm_max_concurrent_calls
    _define(review_env, count)

    response = await review_env.object_review(reviewer, _selections(count))
    events = sse_events(response.text)

    assert events[0]["objects_total"] == count and events[-1]["phase"] == "complete"
    assert _peak_objects_in_flight(events) == bound
    assert review_env.catalog.peak <= bound
    assert review_env.llm.peak <= review_env.llm.run_limit
    assert len(review_env.llm.calls) == count * len(codes)
    starts = [event["object_index"] for event in events if event["phase"] == "object_start"]
    assert starts == list(range(count))  # objects start in the selection order
    for index in (0, count // 2, count - 1):
        phases = [
            event["phase"]
            for event in events
            if event.get("object_index") == index and event["phase"] != "llm_stream"
        ]
        assert phases[:4] == ["object_start", "definition_fetch", "sql_ready", "rules_batch_start"]
        assert phases[-1] == "object_done"
    run = await run_of(events[0]["run_id"])
    assert (run.status, run.object_count) == ("completed", count)
    results, findings = await result_counts(run)
    assert (results, findings) == (count * len(codes), count)
    async with async_session_factory() as session:
        positions = list(
            await session.scalars(
                select(ReviewRunObject.position)
                .join(ReviewRuleResult)
                .where(ReviewRunObject.review_run_id == run.review_run_id)
                .group_by(ReviewRunObject.position)
                .order_by(ReviewRunObject.position)
            )
        )
        without_sql = await session.scalar(
            select(func.count())
            .select_from(ReviewRunObject)
            .where(
                ReviewRunObject.review_run_id == run.review_run_id,
                ReviewRunObject.source_sql.is_(None),
            )
        )
    assert positions == list(range(count)) and without_sql == 0


async def test_definitions_are_fetched_only_for_the_objects_in_flight(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env, flagged=False)
    count = 200
    bound = review_env.auth.settings.llm_max_concurrent_calls
    _define(review_env, count)
    review_env.llm.gate = asyncio.Event()

    request = asyncio.create_task(review_env.object_review(reviewer, _selections(count)))
    await review_env.llm.started.wait()
    for _ in range(50):
        await asyncio.sleep(0.01)
    fetched_while_waiting = [
        call for call in review_env.catalog.calls if call[0] == "fetch_definition"
    ]
    review_env.llm.gate.set()
    events = sse_events((await request).text)

    # With every LLM slot busy, only the objects in flight have their SQL text in memory.
    assert len(fetched_while_waiting) == bound
    assert [call[3] for call in fetched_while_waiting] == [f"usp_{n:04d}" for n in range(bound)]
    assert events[-1]["phase"] == "complete"
    assert sum(1 for call in review_env.catalog.calls if call[0] == "fetch_definition") == count


async def test_a_reader_that_falls_behind_holds_the_run_back(review_env: ReviewEnv) -> None:
    # The event queue is bounded: a slow connection slows the run down instead of letting the
    # events of thousands of objects pile up in memory.
    reviewer, _, _ = await _ready(review_env, flagged=False)
    count = 600
    _define(review_env, count)
    pause = asyncio.Event()
    fetched: list[int] = []

    async def resume_later() -> None:
        for _ in range(60):
            await asyncio.sleep(0.01)
        fetched.append(sum(1 for call in review_env.catalog.calls if call[0] == "fetch_definition"))
        pause.set()

    resumer = asyncio.create_task(resume_later())
    events, _ = await stream_until(
        review_env,
        reviewer,
        "/object-reviews",
        {"selections": _selections(count)},
        lambda event: False,
        pause=pause,
        timeout=60,
    )
    await resumer

    assert 0 < fetched[0] < count // 4
    assert events[-1]["phase"] == "complete"
    assert [event["object_index"] for event in events if event["phase"] == "object_start"] == list(
        range(count)
    )


async def test_a_lost_connection_cancels_a_large_run_without_reading_the_rest(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env, flagged=False)
    count = 500
    bound = review_env.auth.settings.llm_max_concurrent_calls
    _define(review_env, count)
    review_env.llm.gate = asyncio.Event()

    events, _ = await stream_until(
        review_env,
        reviewer,
        "/object-reviews",
        {"selections": _selections(count)},
        lambda event: event["phase"] == "rule_start",
    )
    run_id = events[0]["run_id"]
    for _ in range(200):
        run = await run_of(run_id)
        if run.status != "running":
            break
        await asyncio.sleep(0.025)
    await review_env.settle()
    review_env.llm.gate.set()
    await asyncio.sleep(0.05)

    assert run.status == "cancelled" and await result_counts(run) == (0, 0)
    assert sum(1 for call in review_env.catalog.calls if call[0] == "fetch_definition") <= bound
    assert all(call.cancelled for call in review_env.llm.calls)
    assert all(item.source_sql is None for item in await objects_of(run))


async def test_no_published_rule_set_is_a_conflict(
    review_env: ReviewEnv, super_admin: SuperAdmin
) -> None:
    async with async_session_factory() as session:
        tenant = Tenant(code=f"t-{uuid4().hex[:10]}", name="Kuralsız kurum")
        session.add(tenant)
        await session.commit()
        other = str(tenant.public_id)
    login = await review_env.auth.login(super_admin.username, super_admin.password)
    headers = review_env.auth.auth_headers(login.json())
    headers[review_env.auth.settings.tenant_header] = other
    review_env.catalog.definitions[("DWH", "dbo", "usp_Load")] = DEFINITION_A

    response = await review_env.auth.client.post(
        f"{review_env.prefix}/object-reviews", json={"selections": [SELECTION_A]}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_published_rule_set"
    script = await review_env.auth.client.post(
        f"{review_env.prefix}/script-reviews", json={"sql": "SELECT 1"}, headers=headers
    )
    assert script.status_code == 409


async def test_an_unconfigured_llm_refuses_before_the_stream(review_env: ReviewEnv) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.llm_store.replace(
        review_env.llm_store.current().__class__(chat_api=LlmChatApi.OPENAI)
    )
    response = await review_env.object_review(reviewer, [SELECTION_A])
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"
    assert await runs_of(reviewer.public_id) == []


async def test_an_llm_that_disappears_mid_run_fails_the_run_safely(review_env: ReviewEnv) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.llm.configured = False
    events = sse_events((await review_env.object_review(reviewer, [SELECTION_A])).text)
    assert events[-1] == {
        "phase": "error",
        "code": "llm_not_configured",
        "message": "LLM bağlantısı yapılandırılmamış.",
    }
    run = await run_of(events[0]["run_id"])
    assert run.status == "failed" and run.error_code == "llm_not_configured"
    assert run.finished_at is not None
    assert await result_counts(run) == (0, 0)


async def test_starts_are_limited_per_user_and_shared_with_script_reviews(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.auth.use_settings(
        review_rate_limit_max_requests=2, review_rate_limit_window_seconds=60
    )
    first = await review_env.object_review(reviewer, [SELECTION_A])
    second = await review_env.script_review(reviewer, "SELECT 1")
    third = await review_env.object_review(reviewer, [SELECTION_A])
    fourth = await review_env.script_review(reviewer, "SELECT 1")

    assert [first.status_code, second.status_code] == [200, 200]
    for refused in (third, fourth):
        assert refused.status_code == 429
        assert refused.json()["detail"]["code"] == "rate_limited"
        assert 1 <= int(refused.headers["retry-after"]) <= 60
    colleague = await review_env.sessions.reviewer()
    assert (await review_env.object_review(colleague, [SELECTION_A])).status_code == 200
    assert len(await runs_of(reviewer.public_id)) == 2


async def test_a_lost_connection_cancels_the_run_within_five_seconds(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.llm.gate = asyncio.Event()

    events, dropped_at = await stream_until(
        review_env,
        reviewer,
        "/object-reviews",
        {"selections": [SELECTION_A, SELECTION_B]},
        lambda event: event["phase"] == "rule_start",
    )
    calls_at_drop = len(review_env.llm.calls)
    run_id = events[0]["run_id"]
    for _ in range(200):
        run = await run_of(run_id)
        if run.status != "running":
            break
        await asyncio.sleep(0.025)
    stopped_after = time.monotonic() - dropped_at

    assert run.status == "cancelled" and run.finished_at is not None
    assert stopped_after < 5
    await review_env.settle()
    review_env.llm.gate.set()
    await asyncio.sleep(0.05)
    assert len(review_env.llm.calls) == calls_at_drop
    assert all(call.cancelled for call in review_env.llm.calls)
    assert await result_counts(run) == (0, 0)
    assert all(item.source_sql is None for item in await objects_of(run))
    assert "complete" not in [event["phase"] for event in events]


async def test_runs_left_running_are_interrupted_when_the_process_starts(
    review_env: ReviewEnv,
) -> None:
    reviewer, _, _ = await _ready(review_env)
    review_env.llm.gate = asyncio.Event()
    events, _ = await stream_until(
        review_env,
        reviewer,
        "/object-reviews",
        {"selections": [SELECTION_A]},
        lambda event: event["phase"] == "run_started",
    )
    await review_env.settle()
    async with async_session_factory() as session:
        await session.execute(
            text(
                "UPDATE review_run SET status = 'running', finished_at = NULL "
                "WHERE public_id = :p"
            ),
            {"p": events[0]["run_id"]},
        )
        await session.commit()

    assert await interrupt_stale_runs(async_session_factory) >= 1
    run = await run_of(events[0]["run_id"])
    assert (run.status, run.error_code, run.error_message) == (
        "interrupted",
        "review_interrupted",
        "İnceleme yarıda kesildi.",
    )


async def _llm_reply(request: RecordedRequest, writer: Writer) -> None:
    body = json.dumps({"output": [{"type": "message", "content": '{"violations": []}'}]})
    writer.write(http_response(200, body.encode("utf-8")))
    await writer.drain()


async def test_llm_call_summaries_belong_to_the_run_through_the_real_adapter(
    review_env: ReviewEnv, tmp_path: Path
) -> None:
    reviewer, _, codes = await _ready(review_env)
    review_env.auth.use_settings(review_two_part_threshold_chars=len(DEFINITION_A) - 1)
    server = await FakeLlmServer(write_pki(tmp_path / "pki"), scenario=_llm_reply).start()

    async def private(host: str, port: int) -> list[str]:
        assert host == HOST_NAME
        return ["127.0.0.1"]

    endpoint = LlmEndpoint(LlmChatApi.API_V1_CHAT, server.url("/api/v1/chat"), "test-model")
    chat = HttpLlmChat(
        endpoint=lambda: endpoint,
        recorder=LlmCallSummaryRecorder(async_session_factory),
        ca_bundle=str(server.pki.ca_path),
        read_timeout_seconds=60,
        request_retries=0,
        run_max_concurrent_calls=2,
        process_max_concurrent_calls=4,
        user_agent="test",
        resolver=private,
    )
    app.dependency_overrides[get_llm_chat] = lambda: chat
    try:
        events = sse_events((await review_env.object_review(reviewer, [SELECTION_A])).text)
    finally:
        await server.close()
    assert events[-1]["phase"] == "complete"
    run = await run_of(events[0]["run_id"])
    async with async_session_factory() as session:
        summaries = list(
            await session.scalars(
                select(LlmCallSummary).where(LlmCallSummary.review_run_id == run.review_run_id)
            )
        )
    assert len(summaries) == 4
    assert {s.object_label for s in summaries} == {"[DWH] dbo.usp_Load (PROCEDURE)"}
    assert sorted((s.rule_code, s.part_index) for s in summaries) == sorted(
        (code, part) for code in codes for part in (1, 2)
    )
    assert server.peak <= 2
    # Line 4 holds the marker: only the second part of each rule carries it.
    assert sum(MARKER in request.json()["input"] for request in server.requests) == 2
    assert datetime.now(UTC) >= run.finished_at  # type: ignore[operator]
