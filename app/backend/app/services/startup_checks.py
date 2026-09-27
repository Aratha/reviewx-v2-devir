"""Start-up refusal of unsafe integration settings.

sql-review/PRDs/002-sql-server-connection Requirement 1 (Decision 5, 6 and 11) and
006-llm-connection Requirement 1 and 2: in nonprod the SQL Server connection must be encrypted
with a verified certificate and, once server, user and password are all set, limited to business
databases; an incomplete connection only leaves the SQL Server area not configured. The LLM
endpoint must be https with a model. In nonprod a configured OpenTelemetry collector endpoint
must be https as well. In every environment configured values must be well formed. Only setting
names are reported, never values.
"""

from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import Settings
from app.domain.llm import LlmEndpointInvalid, resolve_chat_url, validate_endpoint_url
from app.domain.models.llm_call import LlmChatApi
from app.domain.sql_server import SYSTEM_DATABASES
from app.infrastructure.sql_server.connection_string import (
    InvalidConnectionValue,
    validate_server,
    validate_user,
)


def _url_is_valid(url: str, *, allow_http: bool) -> bool:
    try:
        validate_endpoint_url(url, allow_http=allow_http)
    except LlmEndpointInvalid:
        return False
    return True


def integration_setting_errors(settings: Settings) -> list[str]:
    """Names of settings that stop the process; empty when start-up may continue."""

    errors: list[str] = []
    local = settings.runtime_environment == "local"
    try:
        validate_server(settings.mssql_server)
    except InvalidConnectionValue:
        errors.append("DWHCODEREVIEW_MSSQL_SERVER")
    try:
        validate_user(settings.mssql_user)
    except InvalidConnectionValue:
        errors.append("DWHCODEREVIEW_MSSQL_USER")
    for name, url in (
        ("DWHCODEREVIEW_LLM_BASE_URL", settings.llm_base_url),
        ("DWHCODEREVIEW_LLM_CHAT_URL", settings.llm_chat_url),
    ):
        if url.strip() and not _url_is_valid(url, allow_http=local):
            errors.append(name)
    if settings.llm_ca_bundle and not Path(settings.llm_ca_bundle).is_file():
        errors.append("DWHCODEREVIEW_LLM_CA_BUNDLE")
    if local:
        return errors

    # Without server, user or password the SQL Server area is not configured and the process
    # starts (Decision 11); a usable connection is never left without the allow-list.
    connection_complete = bool(
        settings.mssql_server.strip()
        and settings.mssql_user.strip()
        and settings.mssql_password is not None
    )
    allowed = settings.mssql_allowed_database_names
    if (connection_complete and not allowed) or allowed & SYSTEM_DATABASES:
        errors.append("DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES")
    if not settings.mssql_encrypt:
        errors.append("DWHCODEREVIEW_MSSQL_ENCRYPT")
    if settings.mssql_trust_server_certificate:
        errors.append("DWHCODEREVIEW_MSSQL_TRUST_SERVER_CERTIFICATE")
    resolved = resolve_chat_url(
        LlmChatApi(settings.llm_chat_api), settings.llm_base_url, settings.llm_chat_url
    )
    if (
        not settings.llm_base_url.strip()
        or not _url_is_valid(settings.llm_base_url, allow_http=False)
        or resolved is None
        or not _url_is_valid(resolved, allow_http=False)
    ):
        errors.append("DWHCODEREVIEW_LLM_BASE_URL")
    if not settings.llm_model.strip():
        errors.append("DWHCODEREVIEW_LLM_MODEL")
    telemetry_endpoint = settings.otel_exporter_otlp_endpoint
    if telemetry_endpoint and urlsplit(telemetry_endpoint).scheme != "https":
        errors.append("DWHCODEREVIEW_OTEL_EXPORTER_OTLP_ENDPOINT")
    return sorted(set(errors))
