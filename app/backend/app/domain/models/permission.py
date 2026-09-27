"""Permission definitions and their role mappings."""

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id


class Permission(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_permission"
    __table_args__ = (
        Index(
            "ix_app_permission_active_code",
            "code",
            postgresql_where=text("is_deleted = false"),
        ),
        {"comment": "Stable resource:action permission codes used by endpoint guards."},
    )

    permission_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    code: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class RolePermission(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_role_permission"
    __table_args__ = (
        Index(
            "ix_app_role_permission_active_role",
            "role_id",
            postgresql_where=text("is_deleted = false"),
        ),
        {"comment": "Permission grants attached to an RBAC role."},
    )

    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_role.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_permission.permission_id", ondelete="CASCADE"),
        primary_key=True,
    )
