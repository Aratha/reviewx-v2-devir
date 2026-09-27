"""Application user: a local password account or an Active Directory login identity."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id


class AccountType(StrEnum):
    """How an account proves its password (application-foundation 001 Requirement 3)."""

    LOCAL = "local"
    DIRECTORY = "directory"


class User(AuditSoftDeleteMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        Index(
            "ix_app_user_active_public_id",
            "public_id",
            postgresql_where=text("is_deleted = false"),
        ),
        CheckConstraint(
            "account_type IN ('local', 'directory')",
            name="account_type_allowed",
        ),
        # A local account verifies its own password hash; a directory account never stores a
        # password hash and is keyed by its immutable directory identity.
        CheckConstraint(
            "(account_type = 'local' AND password_hash IS NOT NULL"
            " AND directory_object_guid IS NULL)"
            " OR (account_type = 'directory' AND password_hash IS NULL"
            " AND directory_object_guid IS NOT NULL)",
            name="credential_matches_account_type",
        ),
        {
            "comment": (
                "Human application identity owned by the application-foundation context: a local "
                "password account or an Active Directory login identity created at its first "
                "successful directory login. Credentials never cross the API boundary."
            )
        },
    )

    user_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    public_id: Mapped[str] = mapped_column(
        Text,
        default=new_public_id,
        nullable=False,
        unique=True,
    )
    home_tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant that scopes the user's role assignments; references tenant.tenant_id.",
    )
    username: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        comment=(
            "Lower-case login name: the local account name, or the userPrincipalName of a "
            "directory account. A local name never carries the directory UPN suffix."
        ),
    )
    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        comment="Lower-case e-mail; a directory account without mail stores its UPN here.",
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AccountType.LOCAL.value,
        server_default=text("'local'"),
        comment=(
            "Credential source; code reflection app.domain.models.user.AccountType: "
            "'local' = application password hash, 'directory' = LDAPS bind against "
            "Active Directory."
        ),
    )
    password_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Argon2 password hash; present only on local accounts.",
    )
    directory_object_guid: Mapped[UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        unique=True,
        comment=(
            "Immutable Active Directory objectGUID; the identity key of a directory account and "
            "absent on local accounts."
        ),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC time of the last successful login.",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        comment=(
            "False after the super admin deactivates the account; an inactive account cannot "
            "log in or refresh a session."
        ),
    )
