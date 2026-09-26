"""Structured, secret-safe application logging configuration."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO


class JsonFormatter(logging.Formatter):
    """Render stable JSON records without serializing arbitrary request or user data."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
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
