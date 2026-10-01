"""SQL Server connection settings contracts (sql-review 002-sql-server-connection)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.domain.sql_server import SERVER_MAX_LENGTH, USER_NAME_MAX_LENGTH

EnvironmentValue = Literal["local", "nonprod"]
ManagedByValue = Literal["local_process", "deployment", "super_admin"]


class SqlConnectionView(BaseModel):
    """Only the editing caller sees server, user and options; nobody sees a password."""

    environment: EnvironmentValue
    editable: bool
    configured: bool
    managed_by: ManagedByValue = Field(
        description=(
            "Where the connection is managed: local_process = this process only (local), "
            "deployment = values of the deployment, super_admin = saved by the super admin."
        )
    )
    server: str | None = None
    port: int | None = None
    user: str | None = None
    encrypt: bool | None = None
    trust_server_certificate: bool | None = None
    password_set: bool | None = None


class SqlConnectionChange(BaseModel):
    """Partial values; a missing password keeps the stored one and an empty one removes it."""

    model_config = ConfigDict(extra="forbid")

    server: str | None = Field(default=None, max_length=SERVER_MAX_LENGTH)
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None, max_length=USER_NAME_MAX_LENGTH)
    password: str | None = Field(default=None, max_length=128)
    encrypt: StrictBool | None = Field(
        default=None, description="Editable only locally; nonprod accepts only true."
    )
    trust_server_certificate: StrictBool | None = Field(
        default=None,
        description="True accepts the server certificate without verifying it; still encrypted.",
    )


class SqlConnectionTestResult(BaseModel):
    ok: bool
    code: str | None = Field(
        description="Failure class of Requirement 8 or password_required; empty on success."
    )
    message: str
    databases: list[str] = Field(
        description="Online databases the account can access, without system databases."
    )
