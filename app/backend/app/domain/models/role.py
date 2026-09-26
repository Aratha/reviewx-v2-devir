"""Role definitions and tenant-scoped user assignments."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

SUPER_ADMIN_ROLE = "super_admin"


class Role(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_role"
    __table_args__ = (
        Index(
            "ix_app_role_active_code",
            "code",
            postgresql_where=text("is_deleted = false"),
        ),
        {"comment": "RBAC role definition; super_admin is an application role only."},
    )

    role_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="tenant",
        server_default=text("'tenant'"),
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )


class UserRole(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_user_role"
    __table_args__ = (
        Index(
            "ix_app_user_role_active_user",
            "user_id",
            postgresql_where=text("is_deleted = false"),
        ),
        {"comment": "A user's role assignment inside one tenant."},
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_role.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="CASCADE"),
        primary_key=True,
    )
