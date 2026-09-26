"""Process-wide SQL Server and LLM integration objects, injected at the transport boundary.

Each is created once per process on first use: the connection stores hold the local edits of
this process and the catalog adapter owns the bounded SQL Server thread pool. Tests replace
them through dependency overrides.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.llm.network import Resolver, system_resolver
from app.infrastructure.sql_server.catalog_adapter import PyodbcSqlCatalog
from app.services.llm_connection_service import (
    LlmConnectionStore,
    initial_llm_connection,
)
from app.services.sql_connection_service import (
    SqlConnectionStore,
    initial_sql_connection,
)


@lru_cache
def get_sql_connection_store() -> SqlConnectionStore:
    return SqlConnectionStore(initial_sql_connection(get_settings()))


@lru_cache
def get_sql_catalog() -> PyodbcSqlCatalog:
    settings = get_settings()
    return PyodbcSqlCatalog(
        config=get_sql_connection_store().current,
        allowed_databases=settings.mssql_allowed_database_names,
        login_timeout_seconds=settings.mssql_login_timeout_seconds,
        query_timeout_seconds=settings.mssql_query_timeout_seconds,
        max_concurrency=settings.mssql_max_concurrency,
    )


@lru_cache
def get_llm_connection_store() -> LlmConnectionStore:
    return LlmConnectionStore(initial_llm_connection(get_settings()))


def get_llm_resolver() -> Resolver:
    return system_resolver


def close_integrations() -> None:
    if get_sql_catalog.cache_info().currsize:
        get_sql_catalog().close()
