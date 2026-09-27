"""Request correlation and bounded structured access logging."""

import logging
import re
from time import monotonic
from uuid import uuid4

from fastapi import Request
from fastapi.routing import iter_route_contexts
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match

from app.core.logging import request_id_var
from app.core.telemetry import http_server_span

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
logger = logging.getLogger("app.http")
UNMATCHED_ROUTE = "unmatched"


def route_template(request: Request) -> str:
    """Return the matched route's full path template, never the concrete request path.

    FastAPI records the endpoint's own route, whose path lacks the prefixes of the routers that
    include it. The application's route contexts carry the full template; the one for the matched
    route that also matches this request is chosen, so a router included twice keeps each prefix.
    """

    matched = request.scope.get("route")
    if matched is None:
        return UNMATCHED_ROUTE
    for context in iter_route_contexts(request.app.routes):
        if context.original_route is not matched:
            continue
        match, _ = context.matches(request.scope)
        if match is not Match.NONE and context.path_format:
            return context.path_format
    return UNMATCHED_ROUTE


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log and trace transport metadata only; never headers, query strings, or bodies."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID_RE.fullmatch(supplied) else str(uuid4())
        request.state.request_id = request_id
        request_id_token = request_id_var.set(request_id)
        started = monotonic()
        status_code = 500
        with http_server_span(request.method) as span:
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers["x-request-id"] = request_id
                return response
            finally:
                template = route_template(request)
                span.complete(template, status_code)
                logger.info(
                    "request.completed",
                    extra={
                        "structured_fields": {
                            "duration_ms": round((monotonic() - started) * 1000, 3),
                            "http_method": request.method,
                            "http_route": template,
                            "http_status": status_code,
                            "request_id": request_id,
                        }
                    },
                )
                request_id_var.reset(request_id_token)
