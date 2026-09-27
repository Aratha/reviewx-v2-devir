"""Structured, secret-safe application logging configuration."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

from opentelemetry import trace

# The x-request-id of the request being served; request logging middleware sets it so every
# application event of that request carries the same correlation identifier.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

EventValue = str | int | bool | None


class JsonFormatter(logging.Formatter):
    """Render stable JSON records without serializing arbitrary request or user data."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            # Links the line to its trace in the local observability stack; ids carry no content.
            payload["trace_id"] = format(span_context.trace_id, "032x")
            payload["span_id"] = format(span_context.span_id, "016x")
        fields = getattr(record, "structured_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class ApplicationJsonHandler(logging.StreamHandler[TextIO]):
    """Marker type for the handler owned by this application."""


def configure_logging(level: str) -> None:
    """Install one application-owned JSON handler without deleting host handlers."""

    handler = ApplicationJsonHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [
        existing for existing in root.handlers if not isinstance(existing, ApplicationJsonHandler)
    ]
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_event(logger: logging.Logger, event: str, **fields: EventValue) -> None:
    """Emit one structured audit or domain event; callers pass only non-sensitive values."""

    logger.info(event, extra={"structured_fields": {"event": event, **fields}})
