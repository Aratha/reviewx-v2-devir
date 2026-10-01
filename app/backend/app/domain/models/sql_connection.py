"""SQL Server connection saved by the super admin in nonprod (sql-review 002-sql-server-connection).

One row per tenant. The password is stored only as authenticated ciphertext; the key lives in the
runtime Secret, never in the database. Which databases can be read is decided by the permissions
of the account.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin
from app.domain.sql_server import SERVER_MAX_LENGTH, USER_NAME_MAX_LENGTH


class SqlConnectionSetting(AuditSoftDeleteMixin, Base):
    __tablename__ = "sql_connection_setting"
    __table_args__ = (
        Index(
            "ix_sql_connection_setting_active_tenant",
            "tenant_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
        {
            "comment": (
                "SQL Server catalog connection the super admin saves from the interface in the "
                "nonprod environment; owned by the sql-review sql-server-connection capability. "
                "At most one row per tenant. It is used only while the deployment supplies no "
                "complete connection. Encryption is always on for it and is not stored. Which databases can be read is decided by the "
                "permissions of the account, not by this row. updated_at and updated_by are the "
                "last save time and user."
            )
        },
    )

    sql_connection_setting_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        comment="Owning tenant; exactly one connection per tenant. References tenant.tenant_id.",
    )
    server: Mapped[str] = mapped_column(
        String(SERVER_MAX_LENGTH),
        nullable=False,
        comment="SQL Server host name or address, optionally with an instance name.",
    )
    port: Mapped[int] = mapped_column(Integer, nullable=False, comment="TCP port, 1 to 65535.")
    user_name: Mapped[str] = mapped_column(
        String(USER_NAME_MAX_LENGTH),
        nullable=False,
        comment="Login name of the shared read-only SQL Server account.",
    )
    password_ciphertext: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Password of the account sealed with AES-256-GCM as 'v1.<nonce>.<ciphertext>'; the "
            "key is the settings encryption key of the runtime Secret and the value is bound to "
            "this tenant. Empty when no password is saved; the connection is then not "
            "configured. The plain password is never stored."
        ),
    )
    trust_server_certificate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=(
            "True when the connection accepts the server certificate without verifying it "
            "(TrustServerCertificate=yes); the connection stays encrypted. False verifies the "
            "certificate against the trust store of the image."
        ),
    )
