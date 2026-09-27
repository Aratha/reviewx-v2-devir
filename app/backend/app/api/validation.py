"""Route classes that render request validation failures in the single error envelope."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.core.errors import error_body


def envelope_validation_route(status_code: int) -> type[APIRoute]:
    """An APIRoute answering malformed input with ``status_code`` and code invalid_request.

    The body never echoes the rejected values, so submitted secrets or SQL stay out of it.
    """

    class EnvelopeValidationRoute(APIRoute):
        def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
            handler = super().get_route_handler()

            async def route_handler(request: Request) -> Response:
                try:
                    return await handler(request)
                except RequestValidationError:
                    return JSONResponse(
                        status_code=status_code,
                        content=error_body("invalid_request", "İstek değerleri geçersiz."),
                    )

            return route_handler

    return EnvelopeValidationRoute
