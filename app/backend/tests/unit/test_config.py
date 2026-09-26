"""Typed settings contract: environment mapping, directory start-up checks and bounds.

Specs: application-foundation/PRDs/001-directory-login (Requirement 3, 6, 7, 9, 10, 11),
sql-review/PRDs/002-sql-server-connection (Requirement 1), 003-object-review (Requirement 8, 9,
18), 005-review-history-export (Requirement 6) and 006-llm-connection (Requirement 1).
"""

import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

pytestmark = pytest.mark.unit

_KEPT_VARIABLES = {"DWHCODEREVIEW_JWT_PRIVATE_KEY", "DWHCODEREVIEW_DATABASE_URL"}


@pytest.fixture(autouse=True)
def _defaults_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert the typed defaults, not the values the local Compose stack injects."""

    for name in list(os.environ):
        if name.startswith("DWHCODEREVIEW_") and name not in _KEPT_VARIABLES:
            monkeypatch.delenv(name)


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("development", "local"),
        ("DEVELOPMENT", "local"),
        (" development ", "local"),
        ("staging", "nonprod"),
        ("production", "nonprod"),
        ("test", "nonprod"),
        ("", "nonprod"),
        ("unknown-value", "nonprod"),
    ),
)
def test_environment_maps_to_local_or_fails_towards_nonprod(value: str, expected: str) -> None:
    assert _settings(environment=value).runtime_environment == expected


def test_local_password_login_is_limited_to_super_admin_outside_local() -> None:
    assert _settings(environment="development").local_login_super_admin_only is False
    assert _settings(environment="staging").local_login_super_admin_only is True
    # The switch can only tighten the environment rule, never open nonprod to local accounts.
    assert (
        _settings(environment="development", local_login_super_admin_only_enforced=True)
    ).local_login_super_admin_only is True
    assert (
        _settings(environment="staging", local_login_super_admin_only_enforced=False)
    ).local_login_super_admin_only is True


def test_session_lifetimes_follow_the_accepted_decision() -> None:
    settings = _settings()
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_session_idle_minutes == 60
    assert settings.refresh_session_absolute_hours == 8


def test_directory_is_disabled_by_default_and_needs_no_other_value() -> None:
    settings = _settings(environment="development")
    assert settings.directory_enabled is False
    assert settings.directory_port == 636
    assert settings.directory_connect_timeout_seconds == 5
    assert settings.directory_read_timeout_seconds == 10


def _ca_bundle(tmp_path: Path) -> str:
    path = tmp_path / "directory-ca.crt"
    path.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    return str(path)


def _directory(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "directory_enabled": True,
        "directory_host": "dc01.corp.example.test",
        "directory_base_dn": "DC=corp,DC=example,DC=test",
        "directory_upn_suffix": "corp.example.test",
        "directory_ca_bundle_path": _ca_bundle(tmp_path),
    }
    values.update(overrides)
    return values


def test_enabled_directory_with_complete_settings_starts(tmp_path: Path) -> None:
    settings = _settings(**_directory(tmp_path))
    assert settings.directory_enabled is True
    assert settings.directory_upn_suffix == "corp.example.test"


@pytest.mark.parametrize(
    "missing",
    ("directory_host", "directory_base_dn", "directory_upn_suffix", "directory_ca_bundle_path"),
)
def test_enabled_directory_without_a_required_setting_stops_start_up(
    tmp_path: Path, missing: str
) -> None:
    with pytest.raises(ValidationError, match=missing):
        _settings(**_directory(tmp_path, **{missing: ""}))


@pytest.mark.parametrize(
    "host",
    (
        "10.13.9.1",
        "ldaps://dc01.corp.example.test",
        "dc01.corp.example.test:636",
        "dc01",
        "dc01 .corp.example.test",
    ),
)
def test_directory_host_must_be_a_certificate_name(tmp_path: Path, host: str) -> None:
    with pytest.raises(ValidationError, match="directory_host"):
        _settings(**_directory(tmp_path, directory_host=host))


def test_directory_ca_bundle_must_be_a_readable_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="directory_ca_bundle_path"):
        _settings(**_directory(tmp_path, directory_ca_bundle_path=str(tmp_path / "missing.crt")))


@pytest.mark.parametrize("suffix", ("@corp.example.test", "corp", "corp example.test"))
def test_directory_upn_suffix_must_be_a_dns_suffix(tmp_path: Path, suffix: str) -> None:
    with pytest.raises(ValidationError, match="directory_upn_suffix"):
        _settings(**_directory(tmp_path, directory_upn_suffix=suffix))


def test_directory_upn_suffix_is_normalized(tmp_path: Path) -> None:
    settings = _settings(**_directory(tmp_path, directory_upn_suffix=" Corp.Example.TEST "))
    assert settings.directory_upn_suffix == "corp.example.test"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("directory_port", 0),
        ("directory_port", 65536),
        ("directory_connect_timeout_seconds", 0),
        ("directory_read_timeout_seconds", 121),
        ("refresh_session_idle_minutes", 0),
        ("refresh_session_absolute_hours", 25),
        ("mssql_port", 0),
        ("mssql_login_timeout_seconds", 61),
        ("mssql_query_timeout_seconds", 301),
        ("mssql_max_concurrency", 17),
        ("llm_read_timeout_seconds", 59),
        ("llm_read_timeout_seconds", 3601),
        ("llm_request_retries", 6),
        ("llm_max_concurrent_calls", 33),
        ("llm_process_max_concurrent_calls", 129),
        ("review_history_retention_days", 0),
        ("review_history_retention_days", 366),
        ("review_rate_limit_max_requests", 0),
        ("review_rate_limit_window_seconds", 0),
        ("review_max_sql_chars", 0),
        ("review_two_part_threshold_chars", 0),
    ),
)
def test_numeric_settings_outside_their_accepted_range_stop_start_up(
    field: str, value: int
) -> None:
    with pytest.raises(ValidationError, match=field):
        _settings(**{field: value})


def test_review_and_llm_defaults_follow_the_accepted_prds() -> None:
    settings = _settings()
    assert settings.mssql_port == 1433
    assert settings.mssql_encrypt is True
    assert settings.mssql_trust_server_certificate is False
    assert settings.mssql_login_timeout_seconds == 15
    assert settings.mssql_query_timeout_seconds == 60
    assert settings.mssql_max_concurrency == 4
    assert settings.llm_read_timeout_seconds == 900
    assert settings.llm_request_retries == 2
    assert settings.llm_max_concurrent_calls == 6
    assert settings.llm_process_max_concurrent_calls == 12
    assert settings.llm_user_agent == "DWHCodeReview-Backend/1.0 (internal SQL review; httpx)"
    assert settings.review_max_sql_chars == 120_000
    assert settings.review_two_part_threshold_chars == 45_000
    assert settings.review_rate_limit_window_seconds == 60
    assert settings.review_rate_limit_max_requests == 30
    assert settings.review_history_retention_days == 90


def test_empty_optional_secrets_mean_not_configured() -> None:
    settings = _settings(mssql_password="", llm_api_key="")
    assert settings.mssql_password is None
    assert settings.llm_api_key is None


def test_optional_secrets_are_not_rendered() -> None:
    settings = _settings(mssql_password="distinct-marker-secret", llm_api_key="other-marker")
    rendered = repr(settings) + str(settings.model_dump())
    assert "distinct-marker-secret" not in rendered
    assert "other-marker" not in rendered


def test_llm_chat_api_accepts_only_the_two_request_formats() -> None:
    assert _settings(llm_chat_api="openai").llm_chat_api == "openai"
    with pytest.raises(ValidationError, match="llm_chat_api"):
        _settings(llm_chat_api="gpt_oss")


def test_allowed_database_list_is_parsed_case_insensitively() -> None:
    settings = _settings(mssql_allowed_databases=" DWH_Stage , dwh_core,,")
    assert settings.mssql_allowed_database_names == frozenset({"dwh_stage", "dwh_core"})


def test_trusted_proxy_networks_are_parsed_and_validated() -> None:
    settings = _settings(trusted_proxy_cidrs="10.42.0.0/16, 192.168.1.10")
    assert [str(network) for network in settings.trusted_proxy_networks] == [
        "10.42.0.0/16",
        "192.168.1.10/32",
    ]
    with pytest.raises(ValidationError, match="trusted_proxy_cidrs"):
        _settings(trusted_proxy_cidrs="not-a-network")


def test_public_origin_must_be_an_exact_origin() -> None:
    assert _settings(public_origin="https://app.example.test").public_origin == (
        "https://app.example.test"
    )
    for value in ("https://app.example.test/", "https://app.example.test/path", "app.example"):
        with pytest.raises(ValidationError, match="public_origin"):
            _settings(public_origin=value)
