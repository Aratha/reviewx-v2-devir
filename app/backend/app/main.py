"""FastAPI application factory for the neutral platform baseline."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.integrations import close_integrations
from app.api.router import local_environment_router, router
from app.core.config import Settings, get_settings
from app.core.errors import ApplicationError, application_error_handler
from app.core.logging import configure_logging, log_event
from app.db.session import async_session_factory, engine
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.services.llm_call_summary_service import run_llm_call_retention
from app.services.startup_checks import integration_setting_errors

logger = logging.getLogger("app.startup")


class UnsafeIntegrationSettings(RuntimeError):
    """The process refuses to start; the message names settings, never their values."""


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        invalid = integration_setting_errors(settings)
        if invalid:
            log_event(logger, "startup.integration_settings_invalid", settings=",".join(invalid))
            raise UnsafeIntegrationSettings("unsafe integration settings: " + ", ".join(invalid))
        retention = asyncio.create_task(run_llm_call_retention(async_session_factory))
        try:
            yield
        finally:
            retention.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await retention
            close_integrations()
            await engine.dispose()

    return lifespan


def create_application(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.project_name,
        version="0.1.0",
        description="Platform API for dwhcodereview",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan(settings),
    )
    # Register tenant context first; Starlette makes the later CORS middleware outermost,
    # so even authorization failures receive the browser-facing CORS headers.
    application.add_middleware(TenantContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["WWW-Authenticate", "X-Request-ID"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.include_router(router)
    if settings.runtime_environment == "local":
        application.include_router(local_environment_router(settings.api_prefix))
    return application


app = create_application()
