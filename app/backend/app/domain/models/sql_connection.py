"""SQL Server connection saved by the super admin in nonprod (sql-review 002-sql-server-connection).

One row per tenant. The password is stored only as authenticated ciphertext; the key lives in the
runtime Secret, never in the database.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin
from app.domain.sql_server import (
    DATABASE_NAME_MAX_LENGTH,
    SERVER_MAX_LENGTH,
    USER_NAME_MAX_LENGTH,
)


class SqlConnectionSetting(AuditSoftDeleteMixin, Base):
    __tablename__ = "sql_connection_setting"
    __table_args__ = (
        Index(
            "ix_sql_connection_setting_active_tenant",
            "tenant_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("port BETWEEN 1 AND 65535", name="port_range"),
        CheckConstraint("cardinality(allowed_databases) >= 1", name="allowed_databases_not_empty"),
        {
            "comment": (
                "SQL Server catalog connection the super admin saves from the interface in the "
                "nonprod environment; owned by the sql-review sql-server-connection capability. "
                "At most one row per tenant. It is used only while the deployment supplies no "
                "complete connection. Encryption and server certificate verification are always "
                "on for it and are not stored. updated_at and updated_by are the last save time "
                "and user."
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
    allowed_databases: Mapped[list[str]] = mapped_column(
        ARRAY(String(DATABASE_NAME_MAX_LENGTH)),
        nullable=False,
        comment=(
            "Names of the business databases open to review, as entered; compared "
            "case-insensitively. Never empty and never a system database (master, tempdb, "
            "model, msdb)."
        ),
    )
