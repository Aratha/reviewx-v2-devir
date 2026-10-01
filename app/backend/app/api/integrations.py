"""Process-wide SQL Server, LLM and review objects, injected at the transport boundary.

Each is created once per process on first use: the connection stores hold the connection in force
in this process, the catalog adapter owns the bounded SQL Server thread pool, the LLM adapter owns
the process-wide call limit, and the review registry and rate limiter keep the running reviews
and start counters of this process. Tests replace them through dependency overrides.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.core.review_throttle import ReviewRateLimiter
from app.core.secret_cipher import SecretCipher, decode_encryption_key
from app.db.session import async_session_factory
from app.infrastructure.llm.http_chat import HttpLlmChat
from app.infrastructure.llm.network import Resolver, system_resolver
from app.infrastructure.sql_server.catalog_adapter import PyodbcSqlCatalog
from app.services.llm_call_summary_service import LlmCallSummaryRecorder
from app.services.llm_connection_service import (
    LlmConnectionStore,
    initial_llm_connection,
)
from app.services.review_run_service import ReviewRunRegistry
from app.services.sql_connection_service import (
    SqlConnectionMode,
    SqlConnectionStore,
    StoredSqlConnection,
    initial_sql_connection,
    sql_connection_mode,
)


@lru_cache
def get_sql_connection_store() -> SqlConnectionStore:
    return SqlConnectionStore(initial_sql_connection(get_settings()))


@lru_cache
def get_sql_connection_storage() -> StoredSqlConnection | None:
    """The PostgreSQL-backed connection of a nonprod process; None where nothing is stored."""

    settings = get_settings()
    key = settings.settings_encryption_key
    if sql_connection_mode(settings) is not SqlConnectionMode.STORED or key is None:
        return None
    return StoredSqlConnection(
        session_factory=async_session_factory,
        cipher=SecretCipher(decode_encryption_key(key.get_secret_value())),
        store=get_sql_connection_store(),
    )


@lru_cache
def get_sql_catalog_adapter() -> PyodbcSqlCatalog:
    settings = get_settings()
    return PyodbcSqlCatalog(
        config=get_sql_connection_store().current,
        login_timeout_seconds=settings.mssql_login_timeout_seconds,
        query_timeout_seconds=settings.mssql_query_timeout_seconds,
        max_concurrency=settings.mssql_max_concurrency,
    )


async def get_sql_catalog(
    storage: Annotated[StoredSqlConnection | None, Depends(get_sql_connection_storage)],
    catalog: Annotated[PyodbcSqlCatalog, Depends(get_sql_catalog_adapter)],
) -> PyodbcSqlCatalog:
    """The catalog after the saved connection was read again (002 Requirement 11).

    Every request that is about to use SQL Server passes here, so a connection saved through
    another replica is in force on the next request without a restart.
    """

    if storage is not None:
        await storage.refresh()
    return catalog


@lru_cache
def get_llm_connection_store() -> LlmConnectionStore:
    return LlmConnectionStore(initial_llm_connection(get_settings()))


def get_llm_resolver() -> Resolver:
    return system_resolver


@lru_cache
def get_llm_chat() -> HttpLlmChat:
    settings = get_settings()
    return HttpLlmChat(
        endpoint=get_llm_connection_store().endpoint,
        recorder=LlmCallSummaryRecorder(async_session_factory),
        ca_bundle=settings.llm_ca_bundle,
        read_timeout_seconds=settings.llm_read_timeout_seconds,
        request_retries=settings.llm_request_retries,
        run_max_concurrent_calls=settings.llm_max_concurrent_calls,
        process_max_concurrent_calls=settings.llm_process_max_concurrent_calls,
        user_agent=settings.llm_user_agent,
        resolver=get_llm_resolver(),
    )


@lru_cache
def get_review_registry() -> ReviewRunRegistry:
    return ReviewRunRegistry()


@lru_cache
def get_review_rate_limiter() -> ReviewRateLimiter:
    return ReviewRateLimiter()


def close_integrations() -> None:
    if get_sql_catalog_adapter.cache_info().currsize:
        get_sql_catalog_adapter().close()
