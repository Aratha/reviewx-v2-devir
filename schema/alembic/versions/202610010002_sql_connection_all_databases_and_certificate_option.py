"""Drop the allowed database list from the saved SQL Server connection; add the certificate option.

Adds trust_server_certificate (false for existing rows: the certificate stays verified). Every
online database the account can access is offered for review, so the list is no longer stored.
Contract step: the column and its check constraint are removed, and the lists in existing
rows are lost; server, account and encrypted password stay. An application version that still
reads the column cannot use the saved connection on this schema. Downgrade restores the column
only while the table is empty, because a restored row would have no list to satisfy the check.

Spec: sql-review/PRDs/002-sql-server-connection (Veri ve geçiş, Decision 5).

Revision ID: 202610010002
Revises: 202610010001
Create Date: 2026-10-01 10:21:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202610010002"
down_revision: str | None = "202610010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table_comment(
        "sql_connection_setting",
        "SQL Server catalog connection the super admin saves from the interface in the nonprod environment; owned by the sql-review sql-server-connection capability. At most one row per tenant. It is used only while the deployment supplies no complete connection. Encryption is always on for it and is not stored. Which databases can be read is decided by the permissions of the account, not by this row. updated_at and updated_by are the last save time and user.",
        existing_comment="SQL Server catalog connection the super admin saves from the interface in the nonprod environment; owned by the sql-review sql-server-connection capability. At most one row per tenant. It is used only while the deployment supplies no complete connection. Encryption and server certificate verification are always on for it and are not stored. updated_at and updated_by are the last save time and user.",
        schema=None,
    )
    op.add_column(
        "sql_connection_setting",
        sa.Column(
            "trust_server_certificate",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the connection accepts the server certificate without verifying it (TrustServerCertificate=yes); the connection stays encrypted. False verifies the certificate against the trust store of the image.",
        ),
    )
    op.drop_constraint(
        op.f("ck_sql_connection_setting_allowed_databases_not_empty"),
        "sql_connection_setting",
        type_="check",
    )
    op.drop_column("sql_connection_setting", "allowed_databases")


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM sql_connection_setting")).scalar()
    if rows:
        raise RuntimeError(
            "sql_connection_setting holds a saved connection; remove it before downgrading, "
            "because the allowed database list of the previous schema cannot be restored"
        )
    op.drop_column("sql_connection_setting", "trust_server_certificate")
    op.add_column(
        "sql_connection_setting",
        sa.Column(
            "allowed_databases",
            postgresql.ARRAY(sa.VARCHAR(length=128)),
            autoincrement=False,
            nullable=False,
            comment="Names of the business databases open to review, as entered; compared case-insensitively. Never empty and never a system database (master, tempdb, model, msdb).",
        ),
    )
    op.create_check_constraint(
        op.f("ck_sql_connection_setting_allowed_databases_not_empty"),
        "sql_connection_setting",
        "cardinality(allowed_databases) >= 1",
    )
    op.create_table_comment(
        "sql_connection_setting",
        "SQL Server catalog connection the super admin saves from the interface in the nonprod environment; owned by the sql-review sql-server-connection capability. At most one row per tenant. It is used only while the deployment supplies no complete connection. Encryption and server certificate verification are always on for it and are not stored. updated_at and updated_by are the last save time and user.",
        existing_comment="SQL Server catalog connection the super admin saves from the interface in the nonprod environment; owned by the sql-review sql-server-connection capability. At most one row per tenant. It is used only while the deployment supplies no complete connection. Encryption is always on for it and is not stored. Which databases can be read is decided by the permissions of the account, not by this row. updated_at and updated_by are the last save time and user.",
        schema=None,
    )
