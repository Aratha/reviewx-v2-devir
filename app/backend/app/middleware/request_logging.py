"""Request correlation and bounded structured access logging."""

import logging
import re
from time import monotonic
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
logger = logging.getLogger("app.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log transport metadata only; never log headers, query strings, or bodies."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID_RE.fullmatch(supplied) else str(uuid4())
        request.state.request_id = request_id
        started = monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", "unmatched")
            api_prefix = get_settings().api_prefix
            request_path = str(request.scope.get("path", ""))
            if request_path.startswith(f"{api_prefix}/") and not route_template.startswith(
                api_prefix
            ):
                route_template = f"{api_prefix}{route_template}"
            logger.info(
                "request.completed",
                extra={
                    "structured_fields": {
                        "duration_ms": round((monotonic() - started) * 1000, 3),
                        "http_method": request.method,
                        "http_route": route_template,
                        "http_status": status_code,
                        "request_id": request_id,
                    }
                },
            )
