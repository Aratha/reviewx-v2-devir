"""Typed application settings; this is the only application environment boundary."""

import os
from functools import cached_property, lru_cache
from typing import Literal

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_RSA_MINIMUM_KEY_BITS = 2048

JwtSigningKey = ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey
JwtVerificationKey = ec.EllipticCurvePublicKey | rsa.RSAPublicKey

# LangChain's langsmith and langgraph-sdk clients reach the paid hosted LangSmith and LangGraph
# services only through these process variables; technology-profile.yml#llm_orchestration forbids
# those services, so a configured key, endpoint or tracing switch stops startup.
_HOSTED_LLM_SERVICE_VARIABLES = (
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_RUNS_ENDPOINTS",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_ENDPOINT",
    "LANGGRAPH_API_KEY",
)
_HOSTED_LLM_TRACING_VARIABLES = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)


class MigrationSettings(BaseSettings):
    """Least-privilege configuration for the schema migration process."""

    model_config = SettingsConfigDict(
        env_prefix="DWHCODEREVIEW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Validation errors would otherwise echo raw inputs such as the signing key or database
        # credentials into startup logs.
        hide_input_in_errors=True,
    )

    # Required, like in Settings: the connection carries credentials, so no default exists.
    database_url: str

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return value


class Settings(BaseSettings):
    """Configuration loaded from prefixed environment variables and an optional .env."""

    model_config = SettingsConfigDict(
        env_prefix="DWHCODEREVIEW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Validation errors would otherwise echo raw inputs such as the signing key or database
        # credentials into startup logs.
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    project_name: str = "dwhcodereview"

    api_prefix: str = "/api/dwhcodereview/v1"
    tenant_header: str = "x-tenant-id"
    cors_allow_origins: str = "http://localhost:3000,http://localhost:8080"

    # Required in every process because the connection carries credentials. Local Compose builds it
    # from the disposable password of scripts/dev-secrets.sh; deployments supply it through the
    # pre-created backend.existingSecret.
    database_url: str

    # Required in every process. rules/58 fixes the asymmetric RS256/ES256 profile: the PEM private
    # key signs, its derived public key verifies. Local Compose receives a disposable development
    # key from scripts/dev-secrets.sh; a missing key in a pre-created deployment Secret stops
    # startup instead of enabling a known signing key.
    jwt_private_key: SecretStr
    jwt_algorithm: Literal["ES256", "RS256"] = "ES256"
    jwt_issuer: str = "dwhcodereview"
    jwt_audience: str = "dwhcodereview-api"
    access_token_expire_minutes: int = 60

    bootstrap_super_admin_email: str = "admin@example.invalid"
    bootstrap_super_admin_username: str = "super-admin"
    bootstrap_super_admin_password: SecretStr | None = None

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("/"):
            raise ValueError("api_prefix must begin with '/'")
        return normalized

    @field_validator("tenant_header")
    @classmethod
    def validate_tenant_header(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "_" in normalized:
            raise ValueError("tenant_header must be a non-empty HTTP header name using hyphens")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use the postgresql+asyncpg driver")
        return value

    @field_validator("access_token_expire_minutes")
    @classmethod
    def validate_access_token_expiry(cls, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError("access_token_expire_minutes must be between 1 and 1440")
        return value

    @property
    def cors_allow_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @cached_property
    def jwt_signing_key(self) -> JwtSigningKey:
        return _load_signing_key(self.jwt_private_key)

    @cached_property
    def jwt_verification_key(self) -> JwtVerificationKey:
        return self.jwt_signing_key.public_key()

    @model_validator(mode="after")
    def require_key_matching_the_algorithm(self) -> "Settings":
        key = self.jwt_signing_key
        if self.jwt_algorithm == "ES256":
            if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
                raise ValueError("jwt_algorithm ES256 requires a P-256 elliptic-curve private key")
        elif not isinstance(key, rsa.RSAPrivateKey) or key.key_size < _RSA_MINIMUM_KEY_BITS:
            raise ValueError(
                f"jwt_algorithm RS256 requires an RSA private key of at least "
                f"{_RSA_MINIMUM_KEY_BITS} bits"
            )
        return self

    @model_validator(mode="after")
    def reject_hosted_llm_services(self) -> "Settings":
        configured = [name for name in _HOSTED_LLM_SERVICE_VARIABLES if os.environ.get(name)]
        configured += [
            name
            for name in _HOSTED_LLM_TRACING_VARIABLES
            if os.environ.get(name, "").strip().lower() not in {"", "0", "false"}
        ]
        if configured:
            raise ValueError(
                "hosted LangSmith and LangGraph services are not allowed: "
                + ", ".join(sorted(configured))
            )
        return self


def _load_signing_key(value: SecretStr) -> JwtSigningKey:
    try:
        key = load_pem_private_key(value.get_secret_value().encode("utf-8"), password=None)
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise ValueError("jwt_private_key must be an unencrypted PEM private key") from None
    if isinstance(key, (ec.EllipticCurvePrivateKey, rsa.RSAPrivateKey)):
        return key
    raise ValueError("jwt_private_key must be an elliptic-curve or RSA private key")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings view."""

    # BaseSettings resolves the required secret from its configured environment source at runtime;
    # static type checkers cannot model that source injection.
    return Settings()  # type: ignore[call-arg]


@lru_cache
def get_migration_settings() -> MigrationSettings:
    """Return the DB-only settings view used by Alembic jobs."""

    # As in get_settings, the required database URL comes from the environment source at runtime.
    return MigrationSettings()  # type: ignore[call-arg]
