"""Tenant aggregate root."""

from sqlalchemy import BigInteger, Boolean, Identity, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id


class Tenant(AuditSoftDeleteMixin, Base):
    __tablename__ = "tenant"
    __table_args__ = (
        Index(
            "ix_tenant_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        {"comment": "Application tenant and authorization boundary."},
    )

    tenant_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
