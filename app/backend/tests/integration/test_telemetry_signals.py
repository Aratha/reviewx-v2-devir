"""OpenTelemetry signals of real requests against PostgreSQL, captured in memory.

The Gözlemlenebilirlik sections of sql-review/PRDs/003-object-review, 004-script-review,
005-review-history-export, 006-llm-connection and application-foundation/PRDs/001-directory-login:
the named metrics with their bounded labels, one trace from the request through the review run
to each LLM attempt and PostgreSQL statement, and no SQL text, snippet, label, model reply, object
or database name, login name, password, token or endpoint address in any span or metric.
"""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.api.integrations import get_llm_chat
from app.core.telemetry import instrument_engine
from app.db.session import async_session_factory, engine
from app.domain.directory import DirectoryUnavailable
from app.domain.llm import LlmChatRequest, LlmEndpoint
from app.domain.models.llm_call import LlmChatApi
from app.infrastructure.llm.http_chat import HttpLlmChat
from app.main import app
from app.services.llm_call_summary_service import LlmCallSummaryRecorder
from app.services.review_history_service import purge_expired_review_runs
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    Writer,
    http_response,
    write_pki,
)
from tests.fakes.review_ports import ok, rule_code_of
from tests.fakes.telemetry import TelemetryCapture
from tests.integration.conftest import AuthHarness, ReviewEnv, RoleSession, sse_events

pytestmark = pytest.mark.integration

MARKER = f"GIZLI-{uuid4().hex}"
DEFINITION = "\n".join(
    ["CREATE PROCEDURE dbo.usp_TelemetryLoad", "AS", f"SELECT * FROM dbo.Musteri -- {MARKER}"]
)
SELECTION = {
    "database": "DWH_Telemetry",
    "schema": "dbo",
    "name": "usp_TelemetryLoad",
    "type_code": "P",
}
MODEL_REPLY = json.dumps(
    {"violations": [{"rule_code": "", "snippet": "SELECT *", "reason": f"yanıt {MARKER}"}]}
)
FORBIDDEN = (MARKER, "SELECT *", "Musteri", "DWH_Telemetry", "usp_TelemetryLoad", "yanıt")


def _scripted_reply(request: LlmChatRequest) -> Any:
    return ok(MODEL_REPLY.replace('"rule_code": ""', f'"rule_code": "{rule_code_of(request)}"'))


async def _reply_over_http(request: RecordedRequest, writer: Writer) -> None:
    body = json.dumps({"output": [{"type": "message", "content": MODEL_REPLY}]})
    writer.write(http_response(200, body.encode("utf-8")))
    await writer.drain()


async def _published(env: ReviewEnv) -> RoleSession:
    manager = await env.sessions.rule_manager()
    await env.publish(manager, [("Yıldız kullanma.", False)], [("Şema adı yaz.", False)])
    env.catalog.definitions[("DWH_Telemetry", "dbo", "usp_TelemetryLoad")] = DEFINITION
    env.llm.responder = _scripted_reply
    return await env.sessions.reviewer()


def _assert_nothing_forbidden(capture: TelemetryCapture, *extra: str) -> None:
    captured = capture.everything()
    for forbidden in (*FORBIDDEN, *extra):
        assert forbidden not in captured, forbidden


async def test_an_object_review_traces_request_run_llm_and_database_without_content(
    review_env: ReviewEnv, tmp_path: Path, telemetry_capture: TelemetryCapture
) -> None:
    instrument_engine(engine.sync_engine)
    reviewer = await _published(review_env)
    server = await FakeLlmServer(write_pki(tmp_path / "pki"), scenario=_reply_over_http).start()

    async def private(host: str, port: int) -> list[str]:
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
        events = sse_events((await review_env.object_review(reviewer, [SELECTION])).text)
    finally:
        await server.close()
    assert events[-1]["phase"] == "complete", events[-1]

    capture = telemetry_capture
    assert capture.value("dwhcodereview_review_runs_started_total", kind="object") == 1
    finished = "dwhcodereview_review_runs_finished_total"
    assert capture.value(finished, kind="object", status="completed") == 1
    rule_calls = "dwhcodereview_review_rule_calls_total"
    assert capture.value(rule_calls, kind="object", outcome="ok") == 2
    results = "dwhcodereview_review_rule_results_total"
    assert capture.value(results, kind="object", status="FAIL") == 2
    llm_calls = "dwhcodereview_llm_calls_total"
    assert capture.value(llm_calls, outcome="ok", chat_api="api_v1_chat") == 2
    assert capture.value("dwhcodereview_llm_inflight_calls") == 0

    (server_span,) = capture.spans("POST /api/dwhcodereview/v1/object-reviews")
    (run_span,) = capture.spans("review_run")
    llm_spans = capture.spans("llm chat")
    database_spans = [span for span in capture.spans() if span.name in {"SELECT", "INSERT"}]
    assert len(llm_spans) == 2 and database_spans
    trace_id = server_span.context.trace_id
    assert run_span.context.trace_id == trace_id
    assert all(span.context.trace_id == trace_id for span in llm_spans)
    assert {span.parent.span_id for span in llm_spans if span.parent} == {run_span.context.span_id}
    assert any(span.context.trace_id == trace_id for span in database_spans)
    assert run_span.attributes is not None
    assert run_span.attributes["dwhcodereview.review.status"] == "completed"
    _assert_nothing_forbidden(
        capture, HOST_NAME, "/api/v1/chat", reviewer.headers["Authorization"].split()[-1]
    )


async def test_a_script_review_counts_as_script_and_keeps_its_label_and_text_out(
    review_env: ReviewEnv, telemetry_capture: TelemetryCapture
) -> None:
    reviewer = await _published(review_env)
    label = f"Etiket {MARKER}"

    response = await review_env.script_review(reviewer, DEFINITION, label)

    assert sse_events(response.text)[-1]["phase"] == "complete"
    capture = telemetry_capture
    assert capture.value("dwhcodereview_review_runs_started_total", kind="script") == 1
    finished = "dwhcodereview_review_runs_finished_total"
    assert capture.value(finished, kind="script", status="completed") == 1
    assert capture.value("dwhcodereview_review_rule_calls_total", kind="script", outcome="ok") == 2
    _assert_nothing_forbidden(capture, "Etiket")


async def test_a_run_that_loses_its_llm_is_counted_as_failed(
    review_env: ReviewEnv, telemetry_capture: TelemetryCapture
) -> None:
    reviewer = await _published(review_env)
    review_env.llm.configured = False

    events = sse_events((await review_env.object_review(reviewer, [SELECTION])).text)

    assert events[-1]["phase"] == "error"
    finished = "dwhcodereview_review_runs_finished_total"
    assert telemetry_capture.value(finished, kind="object", status="failed") == 1
    (run_span,) = telemetry_capture.spans("review_run")
    assert run_span.status.description is None


async def test_exports_and_retention_record_their_metrics(
    review_env: ReviewEnv, telemetry_capture: TelemetryCapture
) -> None:
    reviewer = await _published(review_env)
    run = sse_events((await review_env.script_review(reviewer, DEFINITION, "Etiket")).text)[-1]
    base = f"{review_env.prefix}/review-runs/{run['run_id']}/exports"

    for export_format in ("csv", "sql", "csv"):
        response = await review_env.auth.client.get(
            f"{base}/{export_format}", headers=reviewer.headers
        )
        assert response.status_code == 200
    retention = await purge_expired_review_runs(async_session_factory, retention_days=90)

    capture = telemetry_capture
    assert capture.value("dwhcodereview_review_exports_total", format="csv") == 2
    assert capture.value("dwhcodereview_review_exports_total", format="sql") == 1
    assert retention.outcome == "ok"
    deleted = capture.value("dwhcodereview_review_history_retention_deleted_runs_total")
    assert deleted == retention.deleted
    assert (
        capture.value("dwhcodereview_review_history_retention_last_success_timestamp_seconds")
        > 1_700_000_000
    )
    _assert_nothing_forbidden(capture)


async def test_login_outcomes_are_counted_without_names_or_passwords(
    auth: AuthHarness, telemetry_capture: TelemetryCapture
) -> None:
    name = f"sayac{uuid4().hex[:8]}"
    _, password, _ = auth.directory.add(name, password=f"Parola-{MARKER}")
    succeeded = await auth.login(name, password)
    assert succeeded.status_code == 200
    for _ in range(5):
        assert (await auth.login(name, f"Yanlis-{MARKER}")).status_code == 401
    assert (await auth.login(name, f"Yanlis-{MARKER}")).status_code == 429
    auth.directory.failure = DirectoryUnavailable("timeout")
    assert (await auth.login(f"baska{uuid4().hex[:8]}", "some-password-value")).status_code == 503

    logins = "dwhcodereview_auth_login_attempts_total"
    assert telemetry_capture.value(logins, outcome="succeeded") == 1
    assert telemetry_capture.value(logins, outcome="invalid_credentials") == 5
    assert telemetry_capture.value(logins, outcome="rate_limited") == 1
    assert telemetry_capture.value(logins, outcome="directory_unavailable") == 1
    _assert_nothing_forbidden(
        telemetry_capture, name, password, succeeded.json()["access_token"], "baska"
    )
