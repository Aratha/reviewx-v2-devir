"""OpenTelemetry signals of app.core.telemetry against in-memory providers.

Specs: the Gözlemlenebilirlik sections of sql-review/PRDs/002-sql-server-connection,
003-object-review, 004-script-review, 005-review-history-export, 006-llm-connection and
application-foundation/PRDs/001-directory-login.
"""

import json
import logging
from io import StringIO
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core import telemetry
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.middleware.request_logging import RequestLoggingMiddleware
from tests.fakes.telemetry import TelemetryCapture

pytestmark = pytest.mark.unit

MARKER = f"GIZLI-{uuid4().hex}"


def test_no_endpoint_keeps_the_no_op_providers() -> None:
    settings = Settings(_env_file=None, otel_exporter_otlp_endpoint="")
    assert telemetry.configure_telemetry(settings) is None
    assert telemetry._signals is telemetry._NOOP
    # Every helper stays callable without a provider.
    telemetry.record_login_attempt("succeeded")
    with telemetry.sql_server_call("list_databases") as call:
        call.outcome = "ok"
    with telemetry.review_run("object", object_count=1, rule_count=1) as run:
        run.status = "completed"


def test_an_endpoint_installs_otlp_export_with_a_fixed_resource() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        otel_exporter_otlp_endpoint="http://127.0.0.1:9",
        otel_service_name="dwhcodereview-test",
    )
    export = telemetry.configure_telemetry(settings)
    assert export is not None
    try:
        assert dict(export.tracer_provider.resource.attributes) == {
            "service.name": "dwhcodereview-test",
            "service.version": telemetry.SERVICE_VERSION,
            "deployment.environment.name": "local",
        }
    finally:
        export.shutdown()
    assert telemetry._signals is telemetry._NOOP


@pytest.mark.parametrize(
    ("value", "allowed", "expected"),
    (
        ("ok", telemetry.SQL_SERVER_OUTCOMES, "ok"),
        ("sql_login_failed", telemetry.SQL_SERVER_OUTCOMES, "sql_login_failed"),
        (f"[{MARKER}] dbo.Musteri", telemetry.SQL_SERVER_OUTCOMES, "other"),
        (None, telemetry.LOGIN_OUTCOMES, "other"),
        ("", telemetry.EXPORT_FORMATS, "other"),
    ),
)
def test_label_values_outside_their_set_become_other(
    value: object, allowed: frozenset[str], expected: str
) -> None:
    assert telemetry.bounded(value, allowed) == expected


def test_sql_server_calls_record_the_prd_metrics_and_a_content_free_span(
    telemetry_capture: TelemetryCapture,
) -> None:
    with telemetry.sql_server_call("list_objects") as call:
        assert telemetry_capture.value("dwhcodereview_sql_server_inflight") == 1
        call.outcome = "ok"
    with pytest.raises(RuntimeError), telemetry.sql_server_call("fetch_definition") as call:
        call.outcome = "sql_timeout"
        raise RuntimeError(MARKER)
    with pytest.raises(RuntimeError), telemetry.sql_server_call("connection_test"):
        raise RuntimeError(MARKER)

    calls = "dwhcodereview_sql_server_calls_total"
    assert telemetry_capture.value(calls, operation="list_objects", outcome="ok") == 1
    assert telemetry_capture.value(calls, operation="fetch_definition", outcome="sql_timeout") == 1
    # An unclassified failure is counted without its text.
    assert telemetry_capture.value(calls, operation="connection_test", outcome="other") == 1
    assert telemetry_capture.value("dwhcodereview_sql_server_inflight") == 0
    durations = telemetry_capture.points("dwhcodereview_sql_server_call_duration_seconds")
    assert sorted(labels["operation"] for labels, _ in durations) == [
        "connection_test",
        "fetch_definition",
        "list_objects",
    ]

    span = telemetry_capture.spans("sql_server fetch_definition")[0]
    assert span.kind is SpanKind.CLIENT
    assert dict(span.attributes or {}) == {
        "db.system.name": "microsoft.sql_server",
        "db.operation.name": "fetch_definition",
        "dwhcodereview.outcome": "sql_timeout",
    }
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.events == ()
    assert MARKER not in telemetry_capture.everything()


def test_llm_attempts_record_the_prd_metrics_and_span_attributes(
    telemetry_capture: TelemetryCapture,
) -> None:
    with telemetry.llm_attempt(model="qwen-test", chat_api="openai", attempt=1) as call:
        assert telemetry_capture.value("dwhcodereview_llm_inflight_calls") == 1
        call.outcome, call.http_status, call.completion_tokens = "timeout", None, None
    with telemetry.llm_attempt(model="qwen-test", chat_api="openai", attempt=2) as call:
        call.outcome, call.http_status, call.completion_tokens = "ok", 200, 42

    calls = "dwhcodereview_llm_calls_total"
    assert telemetry_capture.value(calls, outcome="timeout", chat_api="openai") == 1
    assert telemetry_capture.value(calls, outcome="ok", chat_api="openai") == 1
    assert telemetry_capture.value("dwhcodereview_llm_retries_total") == 1
    assert telemetry_capture.value("dwhcodereview_llm_completion_tokens_total") == 42
    assert telemetry_capture.value("dwhcodereview_llm_inflight_calls") == 0
    durations = telemetry_capture.points("dwhcodereview_llm_call_duration_seconds")
    assert sorted(labels["outcome"] for labels, _ in durations) == ["ok", "timeout"]

    first, second = telemetry_capture.spans("llm chat")
    assert dict(first.attributes or {}) == {
        "gen_ai.request.model": "qwen-test",
        "dwhcodereview.llm.attempt": 1,
        "dwhcodereview.llm.outcome": "timeout",
    }
    assert first.status.status_code is StatusCode.ERROR
    assert dict(second.attributes or {}) == {
        "gen_ai.request.model": "qwen-test",
        "dwhcodereview.llm.attempt": 2,
        "dwhcodereview.llm.outcome": "ok",
        "http.response.status_code": 200,
    }
    assert second.status.status_code is StatusCode.UNSET


def test_review_runs_record_started_finished_duration_and_rule_counts(
    telemetry_capture: TelemetryCapture,
) -> None:
    telemetry.record_review_run_started("object")
    with telemetry.review_run("object", object_count=3, rule_count=10) as run:
        telemetry.record_rule_call("object", ok=True)
        telemetry.record_rule_call("object", ok=False)
        telemetry.record_rule_results("object", ["PASS", "FAIL", "FAIL", "UNKNOWN"])
        run.status = "completed"
    with (
        pytest.raises(RuntimeError),
        telemetry.review_run("script", object_count=1, rule_count=10),
    ):
        raise RuntimeError(MARKER)

    assert telemetry_capture.value("dwhcodereview_review_runs_started_total", kind="object") == 1
    finished = "dwhcodereview_review_runs_finished_total"
    assert telemetry_capture.value(finished, kind="object", status="completed") == 1
    assert telemetry_capture.value(finished, kind="script", status="other") == 1
    assert len(telemetry_capture.points("dwhcodereview_review_run_duration_seconds")) == 2
    rule_calls = "dwhcodereview_review_rule_calls_total"
    assert telemetry_capture.value(rule_calls, kind="object", outcome="ok") == 1
    assert telemetry_capture.value(rule_calls, kind="object", outcome="failed") == 1
    results = "dwhcodereview_review_rule_results_total"
    assert telemetry_capture.value(results, kind="object", status="FAIL") == 2
    assert telemetry_capture.value(results, kind="object", status="PASS") == 1
    assert telemetry_capture.value(results, kind="object", status="UNKNOWN") == 1

    completed, failed = telemetry_capture.spans("review_run")
    assert dict(completed.attributes or {}) == {
        "dwhcodereview.review.kind": "object",
        "dwhcodereview.review.object_count": 3,
        "dwhcodereview.review.rule_count": 10,
        "dwhcodereview.review.status": "completed",
    }
    assert failed.status.status_code is StatusCode.ERROR
    assert MARKER not in telemetry_capture.everything()


def test_exports_retention_login_and_summary_failures(
    telemetry_capture: TelemetryCapture,
) -> None:
    telemetry.record_review_export("csv")
    telemetry.record_review_export("sql")
    telemetry.record_review_export("xlsx")
    telemetry.record_review_history_retention(outcome="ok", deleted=4)
    telemetry.record_review_history_retention(outcome="failed", deleted=0)
    telemetry.record_login_attempt("succeeded")
    telemetry.record_login_attempt("invalid_credentials")
    telemetry.record_login_attempt(MARKER)
    telemetry.record_llm_call_summary_write_failure()

    exports = "dwhcodereview_review_exports_total"
    assert telemetry_capture.value(exports, format="csv") == 1
    assert telemetry_capture.value(exports, format="sql") == 1
    assert telemetry_capture.value(exports, format="other") == 1
    assert telemetry_capture.value("dwhcodereview_review_history_retention_deleted_runs_total") == 4
    last_success = telemetry_capture.value(
        "dwhcodereview_review_history_retention_last_success_timestamp_seconds"
    )
    assert last_success > 1_700_000_000
    logins = "dwhcodereview_auth_login_attempts_total"
    assert telemetry_capture.value(logins, outcome="succeeded") == 1
    assert telemetry_capture.value(logins, outcome="invalid_credentials") == 1
    assert telemetry_capture.value(logins, outcome="other") == 1
    assert telemetry_capture.value("dwhcodereview_llm_call_summary_write_failures_total") == 1
    assert MARKER not in telemetry_capture.everything()


@pytest.mark.parametrize(
    ("statement", "operation"),
    (
        ("SELECT 1", "SELECT"),
        ("  insert into review_run (label) values ($1)", "INSERT"),
        ("-- note\n/* hint */ UPDATE app_user SET x = 1", "UPDATE"),
        ("SELECT pg_try_advisory_xact_lock(1)", "SELECT"),
        (f"VACUUM {MARKER}", "other"),
        ("", "other"),
    ),
)
def test_statement_operation_keeps_only_the_keyword(statement: str, operation: str) -> None:
    assert telemetry.statement_operation(statement) == operation


def test_database_spans_carry_the_operation_but_never_the_statement(
    telemetry_capture: TelemetryCapture,
) -> None:
    engine = create_engine("sqlite://")
    telemetry.instrument_engine(engine)
    telemetry.instrument_engine(engine)  # idempotent
    with engine.connect() as connection:
        connection.execute(text(f"SELECT '{MARKER}'"))
        with pytest.raises(OperationalError):
            connection.execute(text(f"SELECT * FROM missing_{MARKER.replace('-', '_')}"))
    engine.dispose()

    spans = telemetry_capture.spans("SELECT")
    assert len(spans) == 2
    assert all(span.kind is SpanKind.CLIENT for span in spans)
    assert dict(spans[0].attributes or {}) == {
        "db.system.name": "postgresql",
        "db.operation.name": "SELECT",
    }
    assert spans[1].status.status_code is StatusCode.ERROR
    assert spans[1].status.description is None
    assert MARKER not in telemetry_capture.everything()
    assert MARKER.replace("-", "_") not in telemetry_capture.everything()


def _application() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @application.get("/broken")
    async def broken() -> None:
        raise RuntimeError(MARKER)

    return application


def test_server_spans_name_the_route_template_and_logs_carry_the_trace(
    telemetry_capture: TelemetryCapture,
) -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    http_logger = logging.getLogger("app.http")
    http_logger.addHandler(handler)
    http_logger.setLevel(logging.INFO)
    try:
        with TestClient(_application(), raise_server_exceptions=False) as client:
            assert client.get(f"/items/{MARKER}?q={MARKER}").status_code == 200
            assert client.get("/broken", headers={"authorization": MARKER}).status_code == 500
    finally:
        http_logger.removeHandler(handler)

    ok_span = telemetry_capture.spans("GET /items/{item_id}")[0]
    assert ok_span.kind is SpanKind.SERVER
    assert dict(ok_span.attributes or {}) == {
        "http.request.method": "GET",
        "http.route": "/items/{item_id}",
        "http.response.status_code": 200,
    }
    failed_span = telemetry_capture.spans("GET /broken")[0]
    assert failed_span.status.status_code is StatusCode.ERROR
    assert failed_span.status.description is None
    assert MARKER not in telemetry_capture.everything()

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    completed = [line for line in lines if line["message"] == "request.completed"]
    assert completed[0]["trace_id"] == format(ok_span.context.trace_id, "032x")
    assert completed[0]["span_id"] == format(ok_span.context.span_id, "016x")


def test_logs_outside_a_span_carry_no_trace_fields() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "plain", None, None)
    payload = json.loads(JsonFormatter().format(record))
    assert "trace_id" not in payload
    assert "span_id" not in payload
