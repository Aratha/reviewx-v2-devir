"""Add the directory-login identity, session and history tables and the SQL review data model.

Expand-only: it adds tables, nullable or defaulted columns and constraints that the existing
rows already satisfy, and it widens app_user.username. It seeds the single platform tenant, the
two application roles and their baseline permission so directory login works before any super
admin exists. Downgrade refuses while directory accounts exist, because a local account needs a
password hash.

Specs: application-foundation/PRDs/001-directory-login (Veri ve geçiş) and the data sections of
sql-review/PRDs/001-rule-management, 003-object-review, 004-script-review,
005-review-history-export and 006-llm-connection.

Revision ID: 202609260001
Revises: 202608060001
Create Date: 2026-09-26 15:39:34.975445
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202609260001"
down_revision: str | None = "202608060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Stable identifiers of the seeded rows, so every database addresses them alike.
_PLATFORM_TENANT_PUBLIC_ID = "00000000-0000-4000-8000-000000000010"
_REVIEWER_ROLE_PUBLIC_ID = "00000000-0000-4000-8000-000000000011"
_RULE_MANAGER_ROLE_PUBLIC_ID = "00000000-0000-4000-8000-000000000012"


def upgrade() -> None:
    op.create_table(
        "rule_set_draft",
        sa.Column("rule_set_draft_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; exactly one draft per tenant. References tenant.tenant_id.",
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Change counter; every successful save adds one. Save and publish requests must carry the current value (optimistic concurrency).",
        ),
        sa.Column(
            "next_rule_number",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
            comment="First KuralNN number never used in any draft or version of the tenant; a new rule receives this number or a larger one.",
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
            "next_rule_number >= 1", name=op.f("ck_rule_set_draft_next_rule_number_positive")
        ),
        sa.CheckConstraint("revision >= 0", name=op.f("ck_rule_set_draft_revision_not_negative")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_rule_set_draft_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("rule_set_draft_id", name=op.f("pk_rule_set_draft")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_rule_set_draft_tenant_id")),
        comment="The single editable rule-set draft of a tenant (sql-review rule-management). updated_at and updated_by are the last save time and user.",
    )
    op.create_index(
        "ix_rule_set_draft_active_tenant",
        "rule_set_draft",
        ["tenant_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "app_user_change",
        sa.Column("app_user_change_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Tenant in which the change happened; references tenant.tenant_id.",
        ),
        sa.Column(
            "actor_user_id",
            sa.BigInteger(),
            nullable=False,
            comment="Super admin who made the change; references app_user.user_id.",
        ),
        sa.Column(
            "target_user_id",
            sa.BigInteger(),
            nullable=False,
            comment="User whose role or activation changed; references app_user.user_id.",
        ),
        sa.Column(
            "changed_field",
            sa.String(length=16),
            nullable=False,
            comment="Changed attribute; code reflection app.domain.models.user_change.UserChangeField: 'role' = application role, 'active' = account activation.",
        ),
        sa.Column(
            "old_value",
            sa.String(length=32),
            nullable=True,
            comment="Value before the change: a role code ('inceleyici', 'kural-yoneticisi') or 'true'/'false' for activation; empty when the user held no application role.",
        ),
        sa.Column(
            "new_value",
            sa.String(length=32),
            nullable=False,
            comment="Value after the change, in the same encoding as old_value.",
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
            "changed_field IN ('role', 'active')",
            name=op.f("ck_app_user_change_changed_field_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_user_change_actor_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_app_user_change_target_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_app_user_change_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("app_user_change_id", name=op.f("pk_app_user_change")),
        comment="Append-only history of role and activation changes to a user, written in the same transaction as the change; owned by the application-foundation context. The application only inserts rows: it never updates or deletes them. created_at is the change time.",
    )
    op.create_index(
        "ix_app_user_change_active_target",
        "app_user_change",
        ["target_user_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_app_user_change_actor_user_id"), "app_user_change", ["actor_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_app_user_change_tenant_id"), "app_user_change", ["tenant_id"], unique=False
    )
    op.create_table(
        "auth_refresh_session",
        sa.Column(
            "auth_refresh_session_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Tenant of the signed-in user; references tenant.tenant_id.",
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            nullable=False,
            comment="Signed-in user; references app_user.user_id.",
        ),
        sa.Column(
            "family_id",
            sa.Uuid(),
            nullable=False,
            comment="Session family: every token issued from one login and its rotations.",
        ),
        sa.Column(
            "token_sha256",
            sa.String(length=64),
            nullable=False,
            comment="Lower-case hex SHA-256 digest of the refresh token; the token is never stored.",
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time the token was presented and rotated; empty while unused.",
        ),
        sa.Column(
            "idle_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC time the unused token expires for inactivity (60 minutes after issue).",
        ),
        sa.Column(
            "absolute_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC upper bound of the whole family (8 hours after login); never extended.",
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time the token stopped being usable; empty while usable.",
        ),
        sa.Column(
            "revoke_reason",
            sa.String(length=32),
            nullable=True,
            comment="Why the token ended; code reflection app.domain.models.refresh_session.RefreshSessionEndReason: 'rotated' = replaced by its successor, 'logout' = user logged out, 'reuse_detected' = an ended token was presented again, 'authorization_changed' = role or activation changed.",
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
            "revoke_reason IS NULL OR revoke_reason IN ('rotated', 'logout', 'reuse_detected', 'authorization_changed')",
            name=op.f("ck_auth_refresh_session_revoke_reason_allowed"),
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason IS NULL)",
            name=op.f("ck_auth_refresh_session_revocation_is_complete"),
        ),
        sa.CheckConstraint(
            "idle_expires_at <= absolute_expires_at",
            name=op.f("ck_auth_refresh_session_idle_within_absolute"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_auth_refresh_session_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.user_id"],
            name=op.f("fk_auth_refresh_session_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("auth_refresh_session_id", name=op.f("pk_auth_refresh_session")),
        sa.UniqueConstraint("token_sha256", name=op.f("uq_auth_refresh_session_token_sha256")),
        comment="One row per issued refresh token of the application-foundation context. Rows of one login share family_id; each refresh ends the presented row as 'rotated' and inserts its successor. Presenting an ended row ends the whole family as 'reuse_detected'. The token itself is never stored, only its SHA-256 digest. Rows whose end or expiry is older than seven days are deleted by the login flow.",
    )
    op.create_index(
        "ix_auth_refresh_session_absolute_expires_at",
        "auth_refresh_session",
        ["absolute_expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_refresh_session_active_family",
        "auth_refresh_session",
        ["family_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_auth_refresh_session_user_id", "auth_refresh_session", ["user_id"], unique=False
    )
    op.create_table(
        "rule_set_draft_rule",
        sa.Column(
            "rule_set_draft_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning draft; references rule_set_draft.rule_set_draft_id.",
        ),
        sa.Column(
            "rule_code",
            sa.String(length=16),
            nullable=False,
            comment="Rule identifier in KuralNN form; never reassigned to another rule once used in any draft or version of the tenant.",
        ),
        sa.Column(
            "priority_group",
            sa.String(length=16),
            nullable=False,
            comment="Priority group; code reflection app.domain.models.rule_set.RulePriorityGroup: 'critical' = kritik (sent first), 'normal' = normal.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Zero-based order inside the priority group; the LLM receives rules in it.",
        ),
        sa.Column(
            "rule_text",
            sa.Text(),
            nullable=False,
            comment="Trimmed rule text, at most 8000 characters; never logged.",
        ),
        sa.Column(
            "requires_metadata",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the rule's LLM request also receives the object metadata (dependencies and column summary).",
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
            "priority_group IN ('critical', 'normal')",
            name=op.f("ck_rule_set_draft_rule_priority_group_allowed"),
        ),
        sa.CheckConstraint(
            "rule_code ~ '^Kural(0[1-9]|[1-9][0-9]+)$'",
            name=op.f("ck_rule_set_draft_rule_rule_code_format"),
        ),
        sa.CheckConstraint(
            "char_length(rule_text) BETWEEN 1 AND 8000",
            name=op.f("ck_rule_set_draft_rule_rule_text_length"),
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_rule_set_draft_rule_position_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_draft_id"],
            ["rule_set_draft.rule_set_draft_id"],
            name=op.f("fk_rule_set_draft_rule_rule_set_draft_id_rule_set_draft"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rule_set_draft_id", "rule_code", name=op.f("pk_rule_set_draft_rule")
        ),
        comment="A rule of the tenant draft. A save soft-deletes rules removed from the draft, so used codes stay visible to the never-reuse check.",
    )
    op.create_index(
        "ix_rule_set_draft_rule_active_draft",
        "rule_set_draft_rule",
        ["rule_set_draft_id", "priority_group", "position"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "rule_set_version",
        sa.Column(
            "rule_set_version_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "number",
            sa.Integer(),
            nullable=False,
            comment="Business version number, 1, 2, 3 ... unique inside the tenant.",
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC publication time; for the import it is the source file's published_at.",
        ),
        sa.Column(
            "published_by_user_id",
            sa.BigInteger(),
            nullable=True,
            comment="Publishing rule manager; empty for the import. References app_user.user_id.",
        ),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            comment="Origin; code reflection app.domain.models.rule_set.RuleSetVersionSource: 'arayuz' = published from the user interface, 'ice-aktarim' = one-time import of the previous application's rule file.",
        ),
        sa.Column(
            "content_sha256",
            sa.String(length=64),
            nullable=False,
            comment="Lower-case hex SHA-256 of the canonical rule content; publishing an unchanged draft returns the existing version instead of creating one.",
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
            "(source = 'ice-aktarim') = (published_by_user_id IS NULL)",
            name=op.f("ck_rule_set_version_publisher_matches_source"),
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_rule_set_version_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "source IN ('arayuz', 'ice-aktarim')", name=op.f("ck_rule_set_version_source_allowed")
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_rule_set_version_number_positive")),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_rule_set_version_published_by_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_rule_set_version_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("rule_set_version_id", name=op.f("pk_rule_set_version")),
        sa.UniqueConstraint("public_id", name=op.f("uq_rule_set_version_public_id")),
        sa.UniqueConstraint("tenant_id", "number", name="uq_rule_set_version_tenant_number"),
        comment="Immutable published rule-set version (sql-review rule-management). The application only inserts versions; it has no update or delete path. Review runs pin the latest version when they start.",
    )
    op.create_index(
        "ix_rule_set_version_active_tenant_number",
        "rule_set_version",
        ["tenant_id", "number"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_rule_set_version_published_by_user_id"),
        "rule_set_version",
        ["published_by_user_id"],
        unique=False,
    )
    op.create_table(
        "review_run",
        sa.Column("review_run_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "owner_user_id",
            sa.BigInteger(),
            nullable=False,
            comment="User who started the run; references app_user.user_id.",
        ),
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            comment="Run kind; code reflection app.domain.models.review.ReviewRunKind: 'object' = SQL Server objects (nesne), 'script' = pasted SQL text (metin).",
        ),
        sa.Column(
            "label",
            sa.String(length=200),
            nullable=True,
            comment="Label of a script run, at most 200 characters; empty for object runs.",
        ),
        sa.Column(
            "rule_set_version_id",
            sa.BigInteger(),
            nullable=False,
            comment="Published rule-set version pinned when the run started; references rule_set_version.rule_set_version_id.",
        ),
        sa.Column(
            "object_count",
            sa.Integer(),
            nullable=False,
            comment="Number of selected objects, 1 to 50; always 1 for a script run.",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'running'"),
            nullable=False,
            comment="Run state; code reflection app.domain.models.review.ReviewRunStatus: 'running' = sürüyor, 'completed' = tamamlandı, 'failed' = hata, 'cancelled' = iptal edildi (no partial result is stored), 'interrupted' = yarıda kesildi (still running when the process started again).",
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, comment="UTC start time."
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC end time; empty while running. Retention counts from this time.",
        ),
        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
            comment="Stable error code when the run ended with an error; empty otherwise.",
        ),
        sa.Column(
            "error_message",
            sa.String(length=500),
            nullable=True,
            comment="Safe Turkish error message; never contains driver, SQL or endpoint details.",
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
            "(status = 'running') = (finished_at IS NULL)",
            name=op.f("ck_review_run_finished_at_matches_status"),
        ),
        sa.CheckConstraint(
            "kind = 'object' OR object_count = 1", name=op.f("ck_review_run_script_has_one_object")
        ),
        sa.CheckConstraint(
            "kind = 'script' OR label IS NULL", name=op.f("ck_review_run_label_only_for_script")
        ),
        sa.CheckConstraint("kind IN ('object', 'script')", name=op.f("ck_review_run_kind_allowed")),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')",
            name=op.f("ck_review_run_status_allowed"),
        ),
        sa.CheckConstraint(
            "label IS NULL OR char_length(label) BETWEEN 1 AND 200",
            name=op.f("ck_review_run_label_length"),
        ),
        sa.CheckConstraint(
            "object_count BETWEEN 1 AND 50", name=op.f("ck_review_run_object_count_range")
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.user_id"],
            name=op.f("fk_review_run_owner_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_version_id"],
            ["rule_set_version.rule_set_version_id"],
            name=op.f("fk_review_run_rule_set_version_id_rule_set_version"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_review_run_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("review_run_id", name=op.f("pk_review_run")),
        sa.UniqueConstraint("public_id", name=op.f("uq_review_run_public_id")),
        comment="One review run of an object selection or a pasted SQL text, pinned to one published rule-set version (sql-review object-review). Only the owner and the rule manager may read it. Deleting a run physically removes its objects, results, findings and stored SQL text in one transaction (review-history-export); runs are also deleted by the retention job once finished_at is older than the configured retention days.",
    )
    op.create_index(
        "ix_review_run_active_owner_started",
        "review_run",
        ["tenant_id", "owner_user_id", "started_at"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index("ix_review_run_finished_at", "review_run", ["finished_at"], unique=False)
    op.create_index(
        op.f("ix_review_run_owner_user_id"), "review_run", ["owner_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_run_rule_set_version_id"),
        "review_run",
        ["rule_set_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_run_tenant_started", "review_run", ["tenant_id", "started_at"], unique=False
    )
    op.create_table(
        "rule_set_version_rule",
        sa.Column(
            "rule_set_version_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning version; references rule_set_version.rule_set_version_id.",
        ),
        sa.Column(
            "rule_code",
            sa.String(length=16),
            nullable=False,
            comment="Rule identifier in KuralNN form; never reassigned to another rule once used in any draft or version of the tenant.",
        ),
        sa.Column(
            "priority_group",
            sa.String(length=16),
            nullable=False,
            comment="Priority group; code reflection app.domain.models.rule_set.RulePriorityGroup: 'critical' = kritik (sent first), 'normal' = normal.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Zero-based order inside the priority group; the LLM receives rules in it.",
        ),
        sa.Column(
            "rule_text",
            sa.Text(),
            nullable=False,
            comment="Rule text as published, at most 8000 characters.",
        ),
        sa.Column(
            "requires_metadata",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the rule's LLM request also receives the object metadata (dependencies and column summary).",
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
            "priority_group IN ('critical', 'normal')",
            name=op.f("ck_rule_set_version_rule_priority_group_allowed"),
        ),
        sa.CheckConstraint(
            "rule_code ~ '^Kural(0[1-9]|[1-9][0-9]+)$'",
            name=op.f("ck_rule_set_version_rule_rule_code_format"),
        ),
        sa.CheckConstraint(
            "char_length(rule_text) BETWEEN 1 AND 8000",
            name=op.f("ck_rule_set_version_rule_rule_text_length"),
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_rule_set_version_rule_position_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["rule_set_version_id"],
            ["rule_set_version.rule_set_version_id"],
            name=op.f("fk_rule_set_version_rule_rule_set_version_id_rule_set_version"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "rule_set_version_id", "rule_code", name=op.f("pk_rule_set_version_rule")
        ),
        sa.UniqueConstraint(
            "rule_set_version_id",
            "priority_group",
            "position",
            name="uq_rule_set_version_rule_group_position",
        ),
        comment="A rule frozen inside a published version; inserted with its version and never changed.",
    )
    op.create_index(
        "ix_rule_set_version_rule_active_version",
        "rule_set_version_rule",
        ["rule_set_version_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "llm_call_summary",
        sa.Column(
            "llm_call_summary_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning tenant; references tenant.tenant_id.",
        ),
        sa.Column(
            "review_run_id",
            sa.BigInteger(),
            nullable=True,
            comment="Review run that made the call; references review_run.review_run_id. The database empties it when the run is deleted and the summary stays until its own retention.",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC start time of the attempt.",
        ),
        sa.Column(
            "object_label",
            sa.String(length=400),
            nullable=False,
            comment="Reviewed object label ('[database] schema.name (type)') or '<label> (SCRIPT)' for pasted text; visible only to the rule manager.",
        ),
        sa.Column(
            "rule_code",
            sa.String(length=16),
            nullable=False,
            comment="KuralNN code of the rule being evaluated.",
        ),
        sa.Column(
            "part_index",
            sa.SmallInteger(),
            nullable=True,
            comment="Part of a two-part analysis: 1 = '#1/2', 2 = '#2/2'; empty for a single-part call.",
        ),
        sa.Column(
            "attempt",
            sa.SmallInteger(),
            nullable=False,
            comment="Attempt number of the call, starting at 1.",
        ),
        sa.Column(
            "chat_api",
            sa.String(length=16),
            nullable=False,
            comment="Request format; code reflection app.domain.models.llm_call.LlmChatApi: 'openai' = /chat/completions, 'api_v1_chat' = /api/v1/chat.",
        ),
        sa.Column("model", sa.String(length=256), nullable=False, comment="Model identifier."),
        sa.Column(
            "endpoint_host",
            sa.String(length=253),
            nullable=False,
            comment="Host name of the endpoint only; never the path, query or credentials.",
        ),
        sa.Column(
            "streamed",
            sa.Boolean(),
            nullable=False,
            comment="True when the response arrived as a stream.",
        ),
        sa.Column(
            "outcome",
            sa.String(length=32),
            nullable=False,
            comment="Result class; code reflection app.domain.models.llm_call.LlmCallOutcome: 'ok', 'timeout', 'connect_error', 'tls_error', 'network_policy_denied', 'upstream_status', 'invalid_response', 'response_too_large', 'cancelled'.",
        ),
        sa.Column(
            "http_status",
            sa.SmallInteger(),
            nullable=True,
            comment="HTTP status code when a response arrived.",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=False,
            comment="Duration of the attempt in milliseconds.",
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=True,
            comment="Completion tokens reported or counted for the call.",
        ),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=True,
            comment="Prompt tokens when the endpoint reports them.",
        ),
        sa.Column(
            "response_chars",
            sa.Integer(),
            nullable=True,
            comment="Number of characters in the response text.",
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
            "chat_api IN ('openai', 'api_v1_chat')",
            name=op.f("ck_llm_call_summary_chat_api_allowed"),
        ),
        sa.CheckConstraint(
            "outcome IN ('ok', 'timeout', 'connect_error', 'tls_error', 'network_policy_denied', 'upstream_status', 'invalid_response', 'response_too_large', 'cancelled')",
            name=op.f("ck_llm_call_summary_outcome_allowed"),
        ),
        sa.CheckConstraint(
            "(completion_tokens IS NULL OR completion_tokens >= 0) AND (prompt_tokens IS NULL OR prompt_tokens >= 0) AND (response_chars IS NULL OR response_chars >= 0)",
            name=op.f("ck_llm_call_summary_counters_not_negative"),
        ),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_llm_call_summary_attempt_positive")),
        sa.CheckConstraint(
            "duration_ms >= 0", name=op.f("ck_llm_call_summary_duration_not_negative")
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name=op.f("ck_llm_call_summary_http_status_range"),
        ),
        sa.CheckConstraint(
            "part_index IS NULL OR part_index IN (1, 2)",
            name=op.f("ck_llm_call_summary_part_index_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["review_run_id"],
            ["review_run.review_run_id"],
            name=op.f("fk_llm_call_summary_review_run_id_review_run"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.tenant_id"],
            name=op.f("fk_llm_call_summary_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("llm_call_summary_id", name=op.f("pk_llm_call_summary")),
        sa.UniqueConstraint("public_id", name=op.f("uq_llm_call_summary_public_id")),
        comment="Metadata of one LLM call attempt (each retry is its own row); owned by the sql-review llm-connection capability. It never holds the prompt, SQL, object metadata, response text, server error body, key or headers. The application only inserts rows; the retention job deletes rows 90 days after started_at.",
    )
    op.create_index(
        "ix_llm_call_summary_active_tenant_started",
        "llm_call_summary",
        ["tenant_id", "started_at"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        op.f("ix_llm_call_summary_review_run_id"),
        "llm_call_summary",
        ["review_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_call_summary_started_at", "llm_call_summary", ["started_at"], unique=False
    )
    op.create_table(
        "review_run_object",
        sa.Column(
            "review_run_object_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column(
            "review_run_id",
            sa.BigInteger(),
            nullable=False,
            comment="Owning run; references review_run.review_run_id. Deleting the run deletes the object (accepted physical deletion).",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Zero-based order of the object in the selection.",
        ),
        sa.Column(
            "database_name",
            sa.String(length=128),
            nullable=True,
            comment="SQL Server database name; empty for a script run.",
        ),
        sa.Column(
            "schema_name",
            sa.String(length=128),
            nullable=False,
            comment="SQL Server schema name; 'sql' for a script run.",
        ),
        sa.Column(
            "object_name",
            sa.String(length=200),
            nullable=False,
            comment="SQL Server object name, or the label of a script run.",
        ),
        sa.Column(
            "type_code",
            sa.String(length=8),
            nullable=False,
            comment="SQL Server object type code: 'P' procedure, 'V' view, 'FN' scalar function, 'IF' inline table function, 'TF' table function, 'SF' CLR scalar function; 'SCRIPT' for pasted text.",
        ),
        sa.Column(
            "object_type",
            sa.String(length=64),
            nullable=False,
            comment="SQL Server type description as listed to the user; 'SCRIPT' for pasted text.",
        ),
        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
            comment="Stable object-level error code, for example 'object_not_found'.",
        ),
        sa.Column(
            "error_message",
            sa.String(length=500),
            nullable=True,
            comment="Safe Turkish object-level error message.",
        ),
        sa.Column(
            "parse_warning",
            sa.Text(),
            nullable=True,
            comment="Merged '[RuleCode] warning' lines of the object, including the truncation note.",
        ),
        sa.Column(
            "source_sql",
            sa.Text(),
            nullable=True,
            comment="Reviewed SQL text without line numbers, at most 120000 characters; empty when no definition could be read.",
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
            "position >= 0", name=op.f("ck_review_run_object_position_not_negative")
        ),
        sa.CheckConstraint(
            "source_sql IS NULL OR char_length(source_sql) <= 120000",
            name=op.f("ck_review_run_object_source_sql_length"),
        ),
        sa.ForeignKeyConstraint(
            ["review_run_id"],
            ["review_run.review_run_id"],
            name=op.f("fk_review_run_object_review_run_id_review_run"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("review_run_object_id", name=op.f("pk_review_run_object")),
        sa.UniqueConstraint("review_run_id", "position", name="uq_review_run_object_run_position"),
        comment="An object (or the single pasted text) inside a review run with the SQL text that was reviewed. The text is source code of the organization: it is kept only for the retention period, never logged, and returned only by the export endpoints to the run owner and the rule manager.",
    )
    op.create_index(
        "ix_review_run_object_active_run",
        "review_run_object",
        ["review_run_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "review_rule_result",
        sa.Column(
            "review_rule_result_id", sa.BigInteger(), sa.Identity(always=False), nullable=False
        ),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "review_run_object_id",
            sa.BigInteger(),
            nullable=False,
            comment="Reviewed object; references review_run_object.review_run_object_id and is deleted with it.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Zero-based order: critical rules first, then normal.",
        ),
        sa.Column("rule_code", sa.String(length=16), nullable=False, comment="KuralNN code."),
        sa.Column(
            "priority_group",
            sa.String(length=16),
            nullable=False,
            comment="Priority group of the rule: 'critical' or 'normal'.",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="Verdict; code reflection app.domain.models.review.RuleResultStatus: 'PASS' = uyumlu, 'FAIL' = ihlal var, 'NOT_APPLICABLE' = kapsam dışı, 'UNKNOWN' = değerlendirilemedi.",
        ),
        sa.Column(
            "severity",
            sa.String(length=8),
            nullable=False,
            comment="Severity; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Critical rules report HIGH, normal rules LOW; an invalid model value becomes LOW.",
        ),
        sa.Column(
            "decision_basis",
            sa.Text(),
            nullable=True,
            comment="The model's stated basis for the verdict (karar dayanağı).",
        ),
        sa.Column(
            "explanation",
            sa.String(length=500),
            nullable=True,
            comment="Explanation, at most 500 characters.",
        ),
        sa.Column(
            "line_reference",
            sa.String(length=64),
            nullable=True,
            comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        ),
        sa.Column(
            "code_snippet",
            sa.String(length=500),
            nullable=True,
            comment="Code excerpt, at most 500 characters; never logged.",
        ),
        sa.Column(
            "false_positive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the run owner marked it as a false positive (sql-review review-history-export).",
        ),
        sa.Column(
            "false_positive_changed_by",
            sa.BigInteger(),
            nullable=True,
            comment="User who last changed false_positive; empty until the first change. References app_user.user_id.",
        ),
        sa.Column(
            "false_positive_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time false_positive last changed; empty until the first change.",
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
            "priority_group IN ('critical', 'normal')",
            name=op.f("ck_review_rule_result_priority_group_allowed"),
        ),
        sa.CheckConstraint(
            "rule_code ~ '^Kural(0[1-9]|[1-9][0-9]+)$'",
            name=op.f("ck_review_rule_result_rule_code_format"),
        ),
        sa.CheckConstraint(
            "severity IN ('HIGH', 'MEDIUM', 'LOW')",
            name=op.f("ck_review_rule_result_severity_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'NOT_APPLICABLE', 'UNKNOWN')",
            name=op.f("ck_review_rule_result_status_allowed"),
        ),
        sa.CheckConstraint(
            "(false_positive_changed_at IS NULL) = (false_positive_changed_by IS NULL)",
            name=op.f("ck_review_rule_result_false_positive_change_is_complete"),
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_review_rule_result_position_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["false_positive_changed_by"],
            ["app_user.user_id"],
            name=op.f("fk_review_rule_result_false_positive_changed_by_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_run_object_id"],
            ["review_run_object.review_run_object_id"],
            name=op.f("fk_review_rule_result_review_run_object_id_review_run_object"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("review_rule_result_id", name=op.f("pk_review_rule_result")),
        sa.UniqueConstraint("public_id", name=op.f("uq_review_rule_result_public_id")),
        sa.UniqueConstraint(
            "review_run_object_id", "position", name="uq_review_rule_result_object_position"
        ),
        comment="The LLM verdict for one rule on one reviewed object, in published rule order.",
    )
    op.create_index(
        "ix_review_rule_result_active_object",
        "review_rule_result",
        ["review_run_object_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_table(
        "review_finding",
        sa.Column("review_finding_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column(
            "review_rule_result_id",
            sa.BigInteger(),
            nullable=False,
            comment="Rule result the finding belongs to; references review_rule_result.review_rule_result_id and is deleted with it.",
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            comment="Zero-based order of the finding under its rule result.",
        ),
        sa.Column("rule_code", sa.String(length=16), nullable=False, comment="KuralNN code."),
        sa.Column(
            "severity",
            sa.String(length=8),
            nullable=False,
            comment="Severity; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Critical rules report HIGH, normal rules LOW; an invalid model value becomes LOW.",
        ),
        sa.Column(
            "description",
            sa.String(length=4000),
            nullable=False,
            comment="'object name: reason' text, at most 4000 characters; never logged.",
        ),
        sa.Column(
            "line_reference",
            sa.String(length=64),
            nullable=True,
            comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        ),
        sa.Column(
            "code_snippet",
            sa.String(length=4000),
            nullable=True,
            comment="Code excerpt, at most 4000 characters; never logged.",
        ),
        sa.Column(
            "false_positive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True when the run owner marked it as a false positive (sql-review review-history-export).",
        ),
        sa.Column(
            "false_positive_changed_by",
            sa.BigInteger(),
            nullable=True,
            comment="User who last changed false_positive; empty until the first change. References app_user.user_id.",
        ),
        sa.Column(
            "false_positive_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time false_positive last changed; empty until the first change.",
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
            "rule_code ~ '^Kural(0[1-9]|[1-9][0-9]+)$'",
            name=op.f("ck_review_finding_rule_code_format"),
        ),
        sa.CheckConstraint(
            "severity IN ('HIGH', 'MEDIUM', 'LOW')", name=op.f("ck_review_finding_severity_allowed")
        ),
        sa.CheckConstraint(
            "(false_positive_changed_at IS NULL) = (false_positive_changed_by IS NULL)",
            name=op.f("ck_review_finding_false_positive_change_is_complete"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_review_finding_position_not_negative")),
        sa.ForeignKeyConstraint(
            ["false_positive_changed_by"],
            ["app_user.user_id"],
            name=op.f("fk_review_finding_false_positive_changed_by_app_user"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_rule_result_id"],
            ["review_rule_result.review_rule_result_id"],
            name=op.f("fk_review_finding_review_rule_result_id_review_rule_result"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("review_finding_id", name=op.f("pk_review_finding")),
        sa.UniqueConstraint("public_id", name=op.f("uq_review_finding_public_id")),
        sa.UniqueConstraint(
            "review_rule_result_id", "position", name="uq_review_finding_result_position"
        ),
        comment="A single violation (bulgu) reported under a rule result; its description is the correction note. No separate fix-suggestion column exists.",
    )
    op.create_index(
        "ix_review_finding_active_result",
        "review_finding",
        ["review_rule_result_id"],
        unique=False,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "account_type",
            sa.String(length=16),
            server_default=sa.text("'local'"),
            nullable=False,
            comment="Credential source; code reflection app.domain.models.user.AccountType: 'local' = application password hash, 'directory' = LDAPS bind against Active Directory.",
        ),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "directory_object_guid",
            sa.Uuid(),
            nullable=True,
            comment="Immutable Active Directory objectGUID; the identity key of a directory account and absent on local accounts.",
        ),
    )
    op.add_column(
        "app_user",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC time of the last successful login.",
        ),
    )
    op.alter_column(
        "app_user",
        "home_tenant_id",
        existing_type=sa.BIGINT(),
        comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "username",
        existing_type=sa.VARCHAR(length=120),
        type_=sa.String(length=320),
        comment="Lower-case login name: the local account name, or the userPrincipalName of a directory account. A local name never carries the directory UPN suffix.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "email",
        existing_type=sa.VARCHAR(length=320),
        comment="Lower-case e-mail; a directory account without mail stores its UPN here.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "password_hash",
        existing_type=sa.TEXT(),
        nullable=True,
        comment="Argon2 password hash; present only on local accounts.",
    )
    op.alter_column(
        "app_user",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="False after the super admin deactivates the account; an inactive account cannot log in or refresh a session.",
        existing_nullable=False,
        existing_server_default=sa.text("true"),
    )
    op.create_unique_constraint(
        op.f("uq_app_user_directory_object_guid"), "app_user", ["directory_object_guid"]
    )
    op.create_table_comment(
        "app_user",
        "Human application identity owned by the application-foundation context: a local password account or an Active Directory login identity created at its first successful directory login. Credentials never cross the API boundary.",
        existing_comment="Human application identity; credentials never cross the API boundary.",
        schema=None,
    )
    op.create_check_constraint(
        op.f("ck_app_user_account_type_allowed"),
        "app_user",
        "account_type IN ('local', 'directory')",
    )
    op.create_check_constraint(
        op.f("ck_app_user_credential_matches_account_type"),
        "app_user",
        "(account_type = 'local' AND password_hash IS NOT NULL AND directory_object_guid IS NULL) OR (account_type = 'directory' AND password_hash IS NULL AND directory_object_guid IS NOT NULL)",
    )
    _seed_platform_tenant_and_roles()


def _seed_platform_tenant_and_roles() -> None:
    # An existing local database may already hold the platform tenant, created by
    # create_super_admin before this revision; the natural keys keep the seed idempotent.
    op.execute(
        sa.text(
            "INSERT INTO tenant (public_id, code, name) "
            "VALUES (:public_id, 'platform', 'Platform') "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(public_id=_PLATFORM_TENANT_PUBLIC_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO app_role (public_id, code, name, scope, is_system) VALUES "
            "(:reviewer, 'inceleyici', 'İnceleyici', 'tenant', true), "
            "(:rule_manager, 'kural-yoneticisi', 'Kural yöneticisi', 'tenant', true) "
            "ON CONFLICT (code) DO NOTHING"
        ).bindparams(
            reviewer=_REVIEWER_ROLE_PUBLIC_ID,
            rule_manager=_RULE_MANAGER_ROLE_PUBLIC_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO app_role_permission (role_id, permission_id) "
            "SELECT app_role.role_id, app_permission.permission_id "
            "FROM app_role CROSS JOIN app_permission "
            "WHERE app_role.code IN ('inceleyici', 'kural-yoneticisi') "
            "AND app_permission.code = 'platform:access' "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM app_role WHERE code IN ('inceleyici', 'kural-yoneticisi') "
            "AND public_id IN (:reviewer, :rule_manager)"
        ).bindparams(
            reviewer=_REVIEWER_ROLE_PUBLIC_ID,
            rule_manager=_RULE_MANAGER_ROLE_PUBLIC_ID,
        )
    )
    op.drop_constraint(
        op.f("ck_app_user_credential_matches_account_type"), "app_user", type_="check"
    )
    op.drop_constraint(op.f("ck_app_user_account_type_allowed"), "app_user", type_="check")
    op.create_table_comment(
        "app_user",
        "Human application identity; credentials never cross the API boundary.",
        existing_comment="Human application identity owned by the application-foundation context: a local password account or an Active Directory login identity created at its first successful directory login. Credentials never cross the API boundary.",
        schema=None,
    )
    op.drop_constraint(op.f("uq_app_user_directory_object_guid"), "app_user", type_="unique")
    op.alter_column(
        "app_user",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="False after the super admin deactivates the account; an inactive account cannot log in or refresh a session.",
        existing_nullable=False,
        existing_server_default=sa.text("true"),
    )
    op.alter_column(
        "app_user",
        "password_hash",
        existing_type=sa.TEXT(),
        nullable=False,
        comment=None,
        existing_comment="Argon2 password hash; present only on local accounts.",
    )
    op.alter_column(
        "app_user",
        "email",
        existing_type=sa.VARCHAR(length=320),
        comment=None,
        existing_comment="Lower-case e-mail; a directory account without mail stores its UPN here.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "username",
        existing_type=sa.String(length=320),
        type_=sa.VARCHAR(length=120),
        comment=None,
        existing_comment="Lower-case login name: the local account name, or the userPrincipalName of a directory account. A local name never carries the directory UPN suffix.",
        existing_nullable=False,
    )
    op.alter_column(
        "app_user",
        "home_tenant_id",
        existing_type=sa.BIGINT(),
        comment=None,
        existing_comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
        existing_nullable=False,
    )
    op.drop_column("app_user", "last_login_at")
    op.drop_column("app_user", "directory_object_guid")
    op.drop_column("app_user", "account_type")
    op.drop_index(
        "ix_review_finding_active_result",
        table_name="review_finding",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("review_finding")
    op.drop_index(
        "ix_review_rule_result_active_object",
        table_name="review_rule_result",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("review_rule_result")
    op.drop_index(
        "ix_review_run_object_active_run",
        table_name="review_run_object",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("review_run_object")
    op.drop_index("ix_llm_call_summary_started_at", table_name="llm_call_summary")
    op.drop_index(op.f("ix_llm_call_summary_review_run_id"), table_name="llm_call_summary")
    op.drop_index(
        "ix_llm_call_summary_active_tenant_started",
        table_name="llm_call_summary",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("llm_call_summary")
    op.drop_index(
        "ix_rule_set_version_rule_active_version",
        table_name="rule_set_version_rule",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("rule_set_version_rule")
    op.drop_index("ix_review_run_tenant_started", table_name="review_run")
    op.drop_index(op.f("ix_review_run_rule_set_version_id"), table_name="review_run")
    op.drop_index(op.f("ix_review_run_owner_user_id"), table_name="review_run")
    op.drop_index("ix_review_run_finished_at", table_name="review_run")
    op.drop_index(
        "ix_review_run_active_owner_started",
        table_name="review_run",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("review_run")
    op.drop_index(op.f("ix_rule_set_version_published_by_user_id"), table_name="rule_set_version")
    op.drop_index(
        "ix_rule_set_version_active_tenant_number",
        table_name="rule_set_version",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("rule_set_version")
    op.drop_index(
        "ix_rule_set_draft_rule_active_draft",
        table_name="rule_set_draft_rule",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("rule_set_draft_rule")
    op.drop_index("ix_auth_refresh_session_user_id", table_name="auth_refresh_session")
    op.drop_index(
        "ix_auth_refresh_session_active_family",
        table_name="auth_refresh_session",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_index("ix_auth_refresh_session_absolute_expires_at", table_name="auth_refresh_session")
    op.drop_table("auth_refresh_session")
    op.drop_index(op.f("ix_app_user_change_tenant_id"), table_name="app_user_change")
    op.drop_index(op.f("ix_app_user_change_actor_user_id"), table_name="app_user_change")
    op.drop_index(
        "ix_app_user_change_active_target",
        table_name="app_user_change",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("app_user_change")
    op.drop_index(
        "ix_rule_set_draft_active_tenant",
        table_name="rule_set_draft",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_table("rule_set_draft")
    op.execute(
        sa.text(
            "DELETE FROM tenant WHERE public_id = :public_id "
            "AND NOT EXISTS (SELECT 1 FROM app_user WHERE app_user.home_tenant_id = tenant.tenant_id)"
        ).bindparams(public_id=_PLATFORM_TENANT_PUBLIC_ID)
    )
