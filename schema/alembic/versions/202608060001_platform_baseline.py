"""Create the tenant, user, and RBAC platform baseline.

Revision ID: 202608060001
Revises: None
Create Date: 2026-08-06 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202608060001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _operational_columns() -> list[sa.Column]:
    return [
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
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("tenant_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *_operational_columns(),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_tenant")),
        sa.UniqueConstraint("code", name=op.f("uq_tenant_code")),
        sa.UniqueConstraint("public_id", name=op.f("uq_tenant_public_id")),
        comment="Application tenant and authorization boundary.",
    )
    op.create_index(
        "ix_tenant_active_public_id",
        "tenant",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "app_role",
        sa.Column("role_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "scope",
            sa.String(length=32),
            server_default=sa.text("'tenant'"),
            nullable=False,
        ),
        sa.Column(
            "is_system",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        *_operational_columns(),
        sa.PrimaryKeyConstraint("role_id", name=op.f("pk_app_role")),
        sa.UniqueConstraint("code", name=op.f("uq_app_role_code")),
        sa.UniqueConstraint("public_id", name=op.f("uq_app_role_public_id")),
        comment="RBAC role definition; super_admin is an application role only.",
    )
    op.create_index(
        "ix_app_role_active_code",
        "app_role",
        ["code"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "app_permission",
        sa.Column("permission_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("code", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_operational_columns(),
        sa.PrimaryKeyConstraint("permission_id", name=op.f("pk_app_permission")),
        sa.UniqueConstraint("code", name=op.f("uq_app_permission_code")),
        sa.UniqueConstraint("public_id", name=op.f("uq_app_permission_public_id")),
        comment="Stable resource:action permission codes used by endpoint guards.",
    )
    op.create_index(
        "ix_app_permission_active_code",
        "app_permission",
        ["code"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "app_user",
        sa.Column("user_id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("home_tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        *_operational_columns(),
        sa.ForeignKeyConstraint(
            ["home_tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_app_user_home_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("email", name=op.f("uq_app_user_email")),
        sa.UniqueConstraint("public_id", name=op.f("uq_app_user_public_id")),
        sa.UniqueConstraint("username", name=op.f("uq_app_user_username")),
        comment="Human application identity; credentials never cross the API boundary.",
    )
    op.create_index(
        op.f("ix_app_user_home_tenant_id"),
        "app_user",
        ["home_tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_app_user_active_public_id",
        "app_user",
        ["public_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "app_role_permission",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        *_operational_columns(),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["app_permission.permission_id"],
            name=op.f("fk_app_role_permission_permission_id_app_permission"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["app_role.role_id"],
            name=op.f("fk_app_role_permission_role_id_app_role"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "role_id",
            "permission_id",
            name=op.f("pk_app_role_permission"),
        ),
        comment="Permission grants attached to an RBAC role.",
    )
    op.create_index(
        "ix_app_role_permission_active_role",
        "app_role_permission",
        ["role_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "app_user_role",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        *_operational_columns(),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["app_role.role_id"],
            name=op.f("fk_app_user_role_role_id_app_role"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_app_user_role_tenant_id_tenant"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_user_role_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", "tenant_id", name=op.f("pk_app_user_role")),
        comment="A user's role assignment inside one tenant.",
    )
    op.create_index(
        "ix_app_user_role_active_user",
        "app_user_role",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.execute(sa.text("""
            INSERT INTO app_role (public_id, code, name, scope, is_system)
            VALUES (
                '00000000-0000-4000-8000-000000000001',
                'super_admin',
                'Super Admin',
                'global',
                true
            )
            """))
    op.execute(sa.text("""
            INSERT INTO app_permission (public_id, code, name)
            VALUES (
                '00000000-0000-4000-8000-000000000002',
                'platform:access',
                'Access the platform baseline'
            )
            """))
    op.execute(sa.text("""
            INSERT INTO app_role_permission (role_id, permission_id)
            SELECT role_id, permission_id
            FROM app_role CROSS JOIN app_permission
            WHERE app_role.code = 'super_admin'
              AND app_permission.code = 'platform:access'
            """))


def downgrade() -> None:
    op.drop_index("ix_app_user_role_active_user", table_name="app_user_role")
    op.drop_table("app_user_role")
    op.drop_index("ix_app_role_permission_active_role", table_name="app_role_permission")
    op.drop_table("app_role_permission")
    op.drop_index("ix_app_user_active_public_id", table_name="app_user")
    op.drop_index(op.f("ix_app_user_home_tenant_id"), table_name="app_user")
    op.drop_table("app_user")
    op.drop_index("ix_app_permission_active_code", table_name="app_permission")
    op.drop_table("app_permission")
    op.drop_index("ix_app_role_active_code", table_name="app_role")
    op.drop_table("app_role")
    op.drop_index("ix_tenant_active_public_id", table_name="tenant")
    op.drop_table("tenant")
