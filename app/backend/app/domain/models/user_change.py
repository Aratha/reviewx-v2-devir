"""Append-only history of role and activation changes made by the super admin."""

from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin


class UserChangeField(StrEnum):
    """The user attribute a history row records (application-foundation 001 Requirement 5)."""

    ROLE = "role"
    ACTIVE = "active"


class UserChange(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_user_change"
    __table_args__ = (
        Index(
            "ix_app_user_change_active_target",
            "target_user_id",
            "created_at",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint("changed_field IN ('role', 'active')", name="changed_field_allowed"),
        {
            "comment": (
                "Append-only history of role and activation changes to a user, written in the "
                "same transaction as the change; owned by the application-foundation context. "
                "The application only inserts rows: it never updates or deletes them. "
                "created_at is the change time."
            )
        },
    )

    app_user_change_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant in which the change happened; references tenant.tenant_id.",
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Super admin who made the change; references app_user.user_id.",
    )
    target_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        comment="User whose role or activation changed; references app_user.user_id.",
    )
    changed_field: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Changed attribute; code reflection app.domain.models.user_change.UserChangeField: "
            "'role' = application role, 'active' = account activation."
        ),
    )
    old_value: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=(
            "Value before the change: a role code ('inceleyici', 'kural-yoneticisi') or "
            "'true'/'false' for activation; empty when the user held no application role."
        ),
    )
    new_value: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Value after the change, in the same encoding as old_value.",
    )
