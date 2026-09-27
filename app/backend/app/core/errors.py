"""The single API error envelope: {"detail": {"code": "...", "message": "..."}}.

Layers raise ApplicationError with a stable code and a safe, localized message; the application
factory renders it. Messages never carry stack traces, SQL, tokens or directory diagnostics.
"""

from collections.abc import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse


class ApplicationError(Exception):
    """A request outcome with a stable HTTP status, error code and person-facing message."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = dict(headers or {})


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"detail": {"code": code, "message": message}}


async def application_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApplicationError):  # pragma: no cover - registered for this type only
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
        headers=exc.headers or None,
    )
