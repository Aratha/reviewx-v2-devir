"""OpenTelemetry traces and metrics of the backend process.

The signals, their names and their labels are owned by the "Gözlemlenebilirlik" sections of
sql-review/PRDs/002-sql-server-connection, 003-object-review, 004-script-review,
005-review-history-export, 006-llm-connection and application-foundation/PRDs/001-directory-login.
Every label value is reduced to a fixed set and anything else becomes ``other``. Callers pass only
classes, counts and durations: no SQL text, snippet, label, model reply, URL, password, token, login
name, object or database name reaches a span, attribute or metric. Exceptions are never recorded on
spans, because their text can carry an address or a driver message.

Export is configured only through the typed ``DWHCODEREVIEW_OTEL_*`` settings. With an empty
endpoint the no-op providers stay installed, so every helper here is safe to call unconditionally.
"""

import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.core.config import Settings
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.domain.models.review import ReviewRunKind, ReviewRunStatus, RuleResultStatus
from app.domain.sql_server import SqlServerErrorClass

SCOPE = "dwhcodereview"
SERVICE_VERSION = "0.1.0"
OTHER = "other"

# Fixed label sets; a value outside its set is exported as "other" and never verbatim.
SQL_SERVER_OPERATIONS = frozenset(
    {"list_databases", "list_objects", "fetch_definition", "dependency_metadata", "connection_test"}
)
SQL_SERVER_OUTCOMES = frozenset({"ok", *(item.value for item in SqlServerErrorClass)})
LLM_OUTCOMES = frozenset(item.value for item in LlmCallOutcome)
LLM_CHAT_APIS = frozenset(item.value for item in LlmChatApi)
REVIEW_KINDS = frozenset(item.value for item in ReviewRunKind)
REVIEW_FINISHED_STATUSES = frozenset(
    item.value for item in ReviewRunStatus if item is not ReviewRunStatus.RUNNING
)
RULE_CALL_OUTCOMES = frozenset({"ok", "failed"})
RULE_RESULT_STATUSES = frozenset(item.value for item in RuleResultStatus)
EXPORT_FORMATS = frozenset({"csv", "sql"})
LOGIN_OUTCOMES = frozenset(
    {
        "succeeded",
        "invalid_credentials",
        "account_disabled",
        "user_inactive",
        "identity_conflict",
        "rate_limited",
        "directory_unavailable",
    }
)
HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
DB_OPERATIONS = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "WITH",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        "CREATE",
        "ALTER",
        "DROP",
        "TRUNCATE",
        "LOCK",
        "SET",
        "SHOW",
    }
)

_SQL_SERVER_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300)
# A call may read for up to 900 s and a retried rule for longer (006-llm-connection Requirement 6).
_LLM_BUCKETS = (0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600, 900, 1800, 2700)
_REVIEW_RUN_BUCKETS = (1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 14400)

_SPAN_ID_ATTRIBUTE = "_dwhcodereview_span"
# An unreachable collector delays the flush at shutdown by at most this long per signal.
_EXPORT_TIMEOUT_SECONDS = 5


def bounded(value: object, allowed: frozenset[str]) -> str:
    """The value itself when it belongs to ``allowed``; otherwise ``other``."""

    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) and raw in allowed else OTHER


class _Instruments:
    """Every metric of the PRDs, created from one meter."""

    def __init__(self, meter: metrics.Meter) -> None:
        # sql-review/PRDs/002-sql-server-connection
        self.sql_server_calls = meter.create_counter(
            "dwhcodereview_sql_server_calls_total",
            unit="{call}",
            description="SQL Server catalog calls by operation and outcome class",
        )
        self.sql_server_call_duration = meter.create_histogram(
            "dwhcodereview_sql_server_call_duration_seconds",
            unit="s",
            description="Duration of SQL Server catalog calls by operation",
            explicit_bucket_boundaries_advisory=_SQL_SERVER_BUCKETS,
        )
        self.sql_server_inflight = meter.create_up_down_counter(
            "dwhcodereview_sql_server_inflight",
            unit="{call}",
            description="SQL Server calls waiting for or running on the driver thread pool",
        )
        # sql-review/PRDs/006-llm-connection
        self.llm_calls = meter.create_counter(
            "dwhcodereview_llm_calls_total",
            unit="{call}",
            description="LLM call attempts by outcome class and request format",
        )
        self.llm_call_duration = meter.create_histogram(
            "dwhcodereview_llm_call_duration_seconds",
            unit="s",
            description="Duration of LLM call attempts by outcome class",
            explicit_bucket_boundaries_advisory=_LLM_BUCKETS,
        )
        self.llm_inflight_calls = meter.create_up_down_counter(
            "dwhcodereview_llm_inflight_calls",
            unit="{call}",
            description="LLM call attempts in progress",
        )
        self.llm_completion_tokens = meter.create_counter(
            "dwhcodereview_llm_completion_tokens_total",
            unit="{token}",
            description="Completion tokens reported by the LLM endpoint",
        )
        self.llm_retries = meter.create_counter(
            "dwhcodereview_llm_retries_total",
            unit="{retry}",
            description="LLM call attempts after a timeout",
        )
        self.llm_call_summary_write_failures = meter.create_counter(
            "dwhcodereview_llm_call_summary_write_failures_total",
            unit="{failure}",
            description="LLM call summaries that could not be stored",
        )
        # sql-review/PRDs/003-object-review and 004-script-review
        self.review_runs_started = meter.create_counter(
            "dwhcodereview_review_runs_started_total",
            unit="{run}",
            description="Review runs started by kind",
        )
        self.review_runs_finished = meter.create_counter(
            "dwhcodereview_review_runs_finished_total",
            unit="{run}",
            description="Review runs finished by kind and final status",
        )
        self.review_run_duration = meter.create_histogram(
            "dwhcodereview_review_run_duration_seconds",
            unit="s",
            description="Duration of review runs by kind and final status",
            explicit_bucket_boundaries_advisory=_REVIEW_RUN_BUCKETS,
        )
        self.review_rule_calls = meter.create_counter(
            "dwhcodereview_review_rule_calls_total",
            unit="{call}",
            description="Rule reviews of one text by kind and whether the LLM answered",
        )
        self.review_rule_results = meter.create_counter(
            "dwhcodereview_review_rule_results_total",
            unit="{result}",
            description="Stored rule results of completed runs by kind and status",
        )
        # sql-review/PRDs/005-review-history-export
        self.review_exports = meter.create_counter(
            "dwhcodereview_review_exports_total",
            unit="{export}",
            description="Review result downloads by format",
        )
        self.review_history_retention_deleted_runs = meter.create_counter(
            "dwhcodereview_review_history_retention_deleted_runs_total",
            unit="{run}",
            description="Review runs deleted by the retention job",
        )
        self.review_history_retention_last_success = meter.create_gauge(
            "dwhcodereview_review_history_retention_last_success_timestamp_seconds",
            unit="s",
            description="Unix time of the last successful retention job run",
        )
        # application-foundation/PRDs/001-directory-login
        self.auth_login_attempts = meter.create_counter(
            "dwhcodereview_auth_login_attempts_total",
            unit="{attempt}",
            description="Login attempts by outcome class",
        )


@dataclass(frozen=True, slots=True)
class _Signals:
    tracer: trace.Tracer
    instruments: _Instruments


def _signals_from(
    tracer_provider: trace.TracerProvider, meter_provider: metrics.MeterProvider
) -> _Signals:
    return _Signals(
        tracer=tracer_provider.get_tracer(SCOPE, SERVICE_VERSION),
        instruments=_Instruments(meter_provider.get_meter(SCOPE, SERVICE_VERSION)),
    )


_NOOP = _signals_from(trace.NoOpTracerProvider(), metrics.NoOpMeterProvider())
_signals = _NOOP


def install(tracer_provider: trace.TracerProvider, meter_provider: metrics.MeterProvider) -> None:
    """Send every later signal of this process to these providers."""

    global _signals
    _signals = _signals_from(tracer_provider, meter_provider)


def uninstall() -> None:
    """Return to the no-op providers."""

    global _signals
    _signals = _NOOP


class TelemetryExport:
    """The OTLP providers of this process; ``shutdown`` flushes and stops them."""

    def __init__(self, tracer_provider: TracerProvider, meter_provider: MeterProvider) -> None:
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider

    def shutdown(self) -> None:
        uninstall()
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


def configure_telemetry(settings: Settings) -> TelemetryExport | None:
    """Install OTLP/gRPC export when an endpoint is configured; otherwise change nothing."""

    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if not endpoint:
        return None
    # Imported only when export is on: the exporters load gRPC.
    from opentelemetry.exporter.otlp.proto.grpc import metric_exporter, trace_exporter

    insecure = urlsplit(endpoint).scheme == "http"
    # Built directly, not with Resource.create, so no process variable adds attributes.
    resource = Resource(
        {
            "service.name": settings.otel_service_name,
            "service.version": SERVICE_VERSION,
            "deployment.environment.name": settings.runtime_environment,
        }
    )
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.otel_traces_sample_ratio)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            trace_exporter.OTLPSpanExporter(
                endpoint=endpoint, insecure=insecure, timeout=_EXPORT_TIMEOUT_SECONDS
            )
        )
    )
    reader = PeriodicExportingMetricReader(
        metric_exporter.OTLPMetricExporter(
            endpoint=endpoint, insecure=insecure, timeout=_EXPORT_TIMEOUT_SECONDS
        ),
        export_interval_millis=settings.otel_metric_export_interval_seconds * 1000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    install(tracer_provider, meter_provider)
    return TelemetryExport(tracer_provider, meter_provider)


def _content_free_span(name: str, kind: SpanKind, attributes: dict[str, Any]) -> Any:
    return _signals.tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    )


def _fail(span: Span) -> None:
    # A status without description: the exception text never reaches the trace.
    span.set_status(Status(StatusCode.ERROR))


# --- HTTP server requests ----------------------------------------------------------------------


class HttpServerSpan:
    """The server span of one request; ``complete`` names it after the matched route template."""

    def __init__(self, span: Span, method: str) -> None:
        self._span = span
        self._method = method

    def complete(self, route_template: str, status_code: int) -> None:
        self._span.update_name(f"{self._method} {route_template}")
        self._span.set_attribute("http.route", route_template)
        self._span.set_attribute("http.response.status_code", status_code)
        if status_code >= 500:
            _fail(self._span)


@contextmanager
def http_server_span(method: str) -> Iterator[HttpServerSpan]:
    """Method, route template and status only; never the raw path, query, headers or body."""

    bounded_method = method if method in HTTP_METHODS else "_OTHER"
    with _content_free_span(
        bounded_method, SpanKind.SERVER, {"http.request.method": bounded_method}
    ) as span:
        yield HttpServerSpan(span, bounded_method)


# --- PostgreSQL through SQLAlchemy -------------------------------------------------------------


def statement_operation(statement: str) -> str:
    """The leading SQL keyword of a statement, within DB_OPERATIONS; the text itself is dropped."""

    text = statement.lstrip()
    while text.startswith(("--", "/*")):
        if text.startswith("--"):
            _, _, text = text.partition("\n")
        else:
            _, _, text = text.partition("*/")
        text = text.lstrip()
    keyword = text.split(None, 1)[0].upper() if text else ""
    return keyword if keyword in DB_OPERATIONS else OTHER


def _before_cursor_execute(
    _connection: Any,
    _cursor: Any,
    statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    if context is None:
        return
    operation = statement_operation(statement)
    span = _signals.tracer.start_span(
        operation,
        kind=SpanKind.CLIENT,
        attributes={"db.system.name": "postgresql", "db.operation.name": operation},
    )
    setattr(context, _SPAN_ID_ATTRIBUTE, span)


def _after_cursor_execute(
    _connection: Any,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    span = getattr(context, _SPAN_ID_ATTRIBUTE, None)
    if span is not None:
        span.end()
        setattr(context, _SPAN_ID_ATTRIBUTE, None)


def _handle_error(exception_context: Any) -> None:
    context = exception_context.execution_context
    span = getattr(context, _SPAN_ID_ATTRIBUTE, None) if context is not None else None
    if span is not None:
        _fail(span)
        span.end()
        setattr(context, _SPAN_ID_ATTRIBUTE, None)


def instrument_engine(engine: Engine) -> None:
    """One client span per statement with the operation keyword only; idempotent."""

    if event.contains(engine, "before_cursor_execute", _before_cursor_execute):
        return
    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    event.listen(engine, "after_cursor_execute", _after_cursor_execute)
    event.listen(engine, "handle_error", _handle_error)


# --- SQL Server catalog calls (002-sql-server-connection) --------------------------------------


@dataclass(slots=True)
class CallOutcome:
    """What the caller learned about one call; ``outcome`` stays None until it is known."""

    outcome: str | None = None
    http_status: int | None = None
    completion_tokens: int | None = None


@contextmanager
def sql_server_call(operation: str) -> Iterator[CallOutcome]:
    """Span, in-flight gauge, count and duration of one catalog call; never the database name."""

    signals = _signals
    bounded_operation = bounded(operation, SQL_SERVER_OPERATIONS)
    record = CallOutcome()
    started = time.monotonic()
    signals.instruments.sql_server_inflight.add(1)
    with _content_free_span(
        f"sql_server {bounded_operation}",
        SpanKind.CLIENT,
        {"db.system.name": "microsoft.sql_server", "db.operation.name": bounded_operation},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome or "", SQL_SERVER_OUTCOMES)
            span.set_attribute("dwhcodereview.outcome", outcome)
            if outcome != "ok":
                _fail(span)
            signals.instruments.sql_server_inflight.add(-1)
            signals.instruments.sql_server_calls.add(
                1, {"operation": bounded_operation, "outcome": outcome}
            )
            signals.instruments.sql_server_call_duration.record(
                time.monotonic() - started, {"operation": bounded_operation}
            )


# --- LLM call attempts (006-llm-connection) ----------------------------------------------------


@contextmanager
def llm_attempt(*, model: str, chat_api: str, attempt: int) -> Iterator[CallOutcome]:
    """Span with model, outcome, HTTP code and attempt number; metrics by the fixed classes."""

    signals = _signals
    bounded_api = bounded(chat_api, LLM_CHAT_APIS)
    record = CallOutcome()
    started = time.monotonic()
    if attempt > 1:
        signals.instruments.llm_retries.add(1)
    signals.instruments.llm_inflight_calls.add(1)
    with _content_free_span(
        "llm chat",
        SpanKind.CLIENT,
        {"gen_ai.request.model": model, "dwhcodereview.llm.attempt": attempt},
    ) as span:
        try:
            yield record
        finally:
            outcome = bounded(record.outcome or "", LLM_OUTCOMES)
            span.set_attribute("dwhcodereview.llm.outcome", outcome)
            if record.http_status is not None:
                span.set_attribute("http.response.status_code", record.http_status)
            if outcome != LlmCallOutcome.OK.value:
                _fail(span)
            signals.instruments.llm_inflight_calls.add(-1)
            signals.instruments.llm_calls.add(1, {"outcome": outcome, "chat_api": bounded_api})
            signals.instruments.llm_call_duration.record(
                time.monotonic() - started, {"outcome": outcome}
            )
            if record.completion_tokens:
                signals.instruments.llm_completion_tokens.add(record.completion_tokens)


def record_llm_call_summary_write_failure() -> None:
    _signals.instruments.llm_call_summary_write_failures.add(1)


# --- Review runs (003-object-review, 004-script-review) ----------------------------------------


def record_review_run_started(kind: str) -> None:
    _signals.instruments.review_runs_started.add(1, {"kind": bounded(kind, REVIEW_KINDS)})


@dataclass(slots=True)
class RunOutcome:
    status: str | None = None


@contextmanager
def review_run(kind: str, *, object_count: int, rule_count: int) -> Iterator[RunOutcome]:
    """Span of one run in its own task; the finished count and duration carry the final status."""

    signals = _signals
    bounded_kind = bounded(kind, REVIEW_KINDS)
    record = RunOutcome()
    started = time.monotonic()
    with _content_free_span(
        "review_run",
        SpanKind.INTERNAL,
        {
            "dwhcodereview.review.kind": bounded_kind,
            "dwhcodereview.review.object_count": object_count,
            "dwhcodereview.review.rule_count": rule_count,
        },
    ) as span:
        try:
            yield record
        finally:
            status = bounded(record.status or "", REVIEW_FINISHED_STATUSES)
            span.set_attribute("dwhcodereview.review.status", status)
            if status not in {ReviewRunStatus.COMPLETED.value, ReviewRunStatus.CANCELLED.value}:
                _fail(span)
            labels = {"kind": bounded_kind, "status": status}
            signals.instruments.review_runs_finished.add(1, labels)
            signals.instruments.review_run_duration.record(time.monotonic() - started, labels)


def record_rule_call(kind: str, *, ok: bool) -> None:
    _signals.instruments.review_rule_calls.add(
        1, {"kind": bounded(kind, REVIEW_KINDS), "outcome": "ok" if ok else "failed"}
    )


def record_rule_results(kind: str, statuses: Iterable[str]) -> None:
    counter = _signals.instruments.review_rule_results
    bounded_kind = bounded(kind, REVIEW_KINDS)
    totals: dict[str, int] = {}
    for status in statuses:
        label = bounded(status, RULE_RESULT_STATUSES)
        totals[label] = totals.get(label, 0) + 1
    for label, count in sorted(totals.items()):
        counter.add(count, {"kind": bounded_kind, "status": label})


# --- Review history and export (005-review-history-export) -------------------------------------


def record_review_export(export_format: str) -> None:
    _signals.instruments.review_exports.add(1, {"format": bounded(export_format, EXPORT_FORMATS)})


def record_review_history_retention(*, outcome: str, deleted: int) -> None:
    """Only a run that finished its delete counts as the last success."""

    if outcome != "ok":
        return
    _signals.instruments.review_history_retention_deleted_runs.add(deleted)
    _signals.instruments.review_history_retention_last_success.set(time.time())


# --- Login (application-foundation/PRDs/001-directory-login) -----------------------------------


def record_login_attempt(outcome: str) -> None:
    _signals.instruments.auth_login_attempts.add(1, {"outcome": bounded(outcome, LOGIN_OUTCOMES)})
