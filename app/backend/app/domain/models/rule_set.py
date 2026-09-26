"""Review rule set: one editable draft per tenant and immutable numbered published versions.

Owned by sql-review/PRDs/001-rule-management. Review runs read only published versions.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

RULE_TEXT_MAX_LENGTH = 8000
RULE_SET_MAX_RULES = 200
# KuralNN: two digits up to Kural99, then as many as needed (Kural100 ...); never Kural00.
RULE_CODE_PATTERN = "^Kural(0[1-9]|[1-9][0-9]+)$"


class RulePriorityGroup(StrEnum):
    """Rule priority group; critical rules go to the LLM before normal ones."""

    CRITICAL = "critical"
    NORMAL = "normal"


class RuleSetVersionSource(StrEnum):
    """How a published version came into existence."""

    USER_INTERFACE = "arayuz"
    IMPORT = "ice-aktarim"


_GROUP_CHECK = "priority_group IN ('critical', 'normal')"
_GROUP_COMMENT = (
    "Priority group; code reflection app.domain.models.rule_set.RulePriorityGroup: "
    "'critical' = kritik (sent first), 'normal' = normal."
)
_CODE_COMMENT = (
    "Rule identifier in KuralNN form; never reassigned to another rule once used in any draft "
    "or version of the tenant."
)
_POSITION_COMMENT = "Zero-based order inside the priority group; the LLM receives rules in it."
_METADATA_COMMENT = (
    "True when the rule's LLM request also receives the object metadata (dependencies and "
    "column summary)."
)


class RuleSetDraft(AuditSoftDeleteMixin, Base):
    __tablename__ = "rule_set_draft"
    __table_args__ = (
        Index(
            "ix_rule_set_draft_active_tenant",
            "tenant_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("revision >= 0", name="revision_not_negative"),
        CheckConstraint("next_rule_number >= 1", name="next_rule_number_positive"),
        {
            "comment": (
                "The single editable rule-set draft of a tenant (sql-review rule-management). "
                "updated_at and updated_by are the last save time and user."
            )
        },
    )

    rule_set_draft_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        comment="Owning tenant; exactly one draft per tenant. References tenant.tenant_id.",
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment=(
            "Change counter; every successful save adds one. Save and publish requests must "
            "carry the current value (optimistic concurrency)."
        ),
    )
    next_rule_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        comment=(
            "First KuralNN number never used in any draft or version of the tenant; a new rule "
            "receives this number or a larger one."
        ),
    )


class RuleSetDraftRule(AuditSoftDeleteMixin, Base):
    __tablename__ = "rule_set_draft_rule"
    __table_args__ = (
        Index(
            "ix_rule_set_draft_rule_active_draft",
            "rule_set_draft_id",
            "priority_group",
            "position",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint(_GROUP_CHECK, name="priority_group_allowed"),
        CheckConstraint(f"rule_code ~ '{RULE_CODE_PATTERN}'", name="rule_code_format"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint(
            f"char_length(rule_text) BETWEEN 1 AND {RULE_TEXT_MAX_LENGTH}",
            name="rule_text_length",
        ),
        {
            "comment": (
                "A rule of the tenant draft. A save soft-deletes rules removed from the draft, "
                "so used codes stay visible to the never-reuse check."
            )
        },
    )

    rule_set_draft_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rule_set_draft.rule_set_draft_id", ondelete="RESTRICT"),
        primary_key=True,
        comment="Owning draft; references rule_set_draft.rule_set_draft_id.",
    )
    rule_code: Mapped[str] = mapped_column(String(16), primary_key=True, comment=_CODE_COMMENT)
    priority_group: Mapped[str] = mapped_column(String(16), nullable=False, comment=_GROUP_COMMENT)
    position: Mapped[int] = mapped_column(Integer, nullable=False, comment=_POSITION_COMMENT)
    rule_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Trimmed rule text, at most 8000 characters; never logged."
    )
    requires_metadata: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=_METADATA_COMMENT,
    )


class RuleSetVersion(AuditSoftDeleteMixin, Base):
    __tablename__ = "rule_set_version"
    __table_args__ = (
        Index(
            "ix_rule_set_version_active_tenant_number",
            "tenant_id",
            "number",
            postgresql_where=text("is_deleted = false"),
        ),
        UniqueConstraint("tenant_id", "number", name="uq_rule_set_version_tenant_number"),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint("source IN ('arayuz', 'ice-aktarim')", name="source_allowed"),
        CheckConstraint(
            "(source = 'ice-aktarim') = (published_by_user_id IS NULL)",
            name="publisher_matches_source",
        ),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="content_sha256_format"),
        {
            "comment": (
                "Immutable published rule-set version (sql-review rule-management). The "
                "application only inserts versions; it has no update or delete path. Review "
                "runs pin the latest version when they start."
            )
        },
    )

    rule_set_version_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owning tenant; references tenant.tenant_id.",
    )
    number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Business version number, 1, 2, 3 ... unique inside the tenant.",
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC publication time; for the import it is the source file's published_at.",
    )
    published_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        comment="Publishing rule manager; empty for the import. References app_user.user_id.",
    )
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Origin; code reflection app.domain.models.rule_set.RuleSetVersionSource: "
            "'arayuz' = published from the user interface, 'ice-aktarim' = one-time import "
            "of the previous application's rule file."
        ),
    )
    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Lower-case hex SHA-256 of the canonical rule content; publishing an unchanged "
            "draft returns the existing version instead of creating one."
        ),
    )


class RuleSetVersionRule(AuditSoftDeleteMixin, Base):
    __tablename__ = "rule_set_version_rule"
    __table_args__ = (
        UniqueConstraint(
            "rule_set_version_id",
            "priority_group",
            "position",
            name="uq_rule_set_version_rule_group_position",
        ),
        Index(
            "ix_rule_set_version_rule_active_version",
            "rule_set_version_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint(_GROUP_CHECK, name="priority_group_allowed"),
        CheckConstraint(f"rule_code ~ '{RULE_CODE_PATTERN}'", name="rule_code_format"),
        CheckConstraint("position >= 0", name="position_not_negative"),
        CheckConstraint(
            f"char_length(rule_text) BETWEEN 1 AND {RULE_TEXT_MAX_LENGTH}",
            name="rule_text_length",
        ),
        {
            "comment": (
                "A rule frozen inside a published version; inserted with its version and never "
                "changed."
            )
        },
    )

    rule_set_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("rule_set_version.rule_set_version_id", ondelete="RESTRICT"),
        primary_key=True,
        comment="Owning version; references rule_set_version.rule_set_version_id.",
    )
    rule_code: Mapped[str] = mapped_column(String(16), primary_key=True, comment=_CODE_COMMENT)
    priority_group: Mapped[str] = mapped_column(String(16), nullable=False, comment=_GROUP_COMMENT)
    position: Mapped[int] = mapped_column(Integer, nullable=False, comment=_POSITION_COMMENT)
    rule_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Rule text as published, at most 8000 characters."
    )
    requires_metadata: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment=_METADATA_COMMENT,
    )
