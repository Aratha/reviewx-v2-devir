"""SQL Server connection settings contracts (sql-review 002-sql-server-connection)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

EnvironmentValue = Literal["local", "nonprod"]


class SqlConnectionView(BaseModel):
    """Nonprod returns only environment, editable and configured; never a password."""

    environment: EnvironmentValue
    editable: bool
    configured: bool
    server: str | None = None
    port: int | None = None
    user: str | None = None
    encrypt: bool | None = None
    trust_server_certificate: bool | None = None
    password_set: bool | None = None
    allowed_databases: list[str] | None = None


class SqlConnectionChange(BaseModel):
    """Partial values; a missing password keeps the stored one and an empty one removes it."""

    model_config = ConfigDict(extra="forbid")

    server: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=128)
    encrypt: StrictBool | None = None
    trust_server_certificate: StrictBool | None = None


class SqlConnectionTestResult(BaseModel):
    ok: bool
    code: str | None = Field(
        description="Failure class of Requirement 8 or password_required; empty on success."
    )
    message: str
    databases: list[str]
