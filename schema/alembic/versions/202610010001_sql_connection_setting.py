"""Add the table that keeps the SQL Server connection the super admin saves in nonprod.

Expand-only: one new table, no change to existing rows, so the previous application version keeps
working with the new schema. The password column holds only AES-256-GCM ciphertext; the key is
never in the database. Downgrade drops the table and with it the saved connection; the SQL Server
area then reads "not configured" until the connection is entered again.

Spec: sql-review/PRDs/002-sql-server-connection (Veri ve geçiş, Requirement 10).

Revision ID: 202610010001
Revises: 202609260003
Create Date: 2026-10-01 06:13:36.017226
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610010001"
down_revision: str | None = "202609260003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sql_connection_setting",
        sa.Column(
            "sql_connection_setting_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; exactly one connection per tenant. References tenant.tenant_id.",
        ),
        sa.Column(
            "server",
            sa.String(length=255),
            nullable=False,
            comment="SQL Server host name or address, optionally with an instance name.",
        ),
        sa.Column("port", sa.Integer(), nullable=False, comment="TCP port, 1 to 65535."),
        sa.Column(
            "user_name",
            sa.String(length=128),
            nullable=False,
            comment="Login name of the shared read-only SQL Server account.",
        ),
        sa.Column(
            "password_ciphertext",
            sa.Text(),
            nullable=True,
            comment="Password of the account sealed with AES-256-GCM as 'v1.<nonce>.<ciphertext>'; the key is the settings encryption key of the runtime Secret and the value is bound to this tenant. Empty when no password is saved; the connection is then not configured. The plain password is never stored.",
        ),
        sa.Column(
            "allowed_databases",
            postgresql.ARRAY(sa.String(length=128)),
            nullable=False,
            comment="Names of the business databases open to review, as entered; compared case-insensitively. Never empty and never a system database (master, tempdb, model, msdb).",
        ),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "port BETWEEN 1 AND 65535", name=op.f("ck_sql_connection_setting_port_range")
        ),
        sa.CheckConstraint(
            "cardinality(allowed_databases) >= 1",
            name=op.f("ck_sql_connection_setting_allowed_databases_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_sql_connection_setting_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "sql_connection_setting_id", name=op.f("pk_sql_connection_setting")
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_sql_connection_setting_tenant_id")),
        comment="SQL Server catalog connection the super admin saves from the interface in the nonprod environment; owned by the sql-review sql-server-connection capability. At most one row per tenant. It is used only while the deployment supplies no complete connection. Encryption and server certificate verification are always on for it and are not stored. updated_at and updated_by are the last save time and user.",
    )
    op.create_index(
        "ix_sql_connection_setting_active_tenant",
        "sql_connection_setting",
        ["tenant_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sql_connection_setting_active_tenant",
        table_name="sql_connection_setting",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("sql_connection_setting")
