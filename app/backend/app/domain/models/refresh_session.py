"""Server-side refresh-token records with rotation, reuse detection and revocation."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin

# application-foundation 001 "Veri ve geçiş": an ended record is removed seven days later.
REFRESH_SESSION_RETENTION_DAYS = 7


class RefreshSessionEndReason(StrEnum):
    """Why a refresh token stopped being usable."""

    ROTATED = "rotated"
    LOGOUT = "logout"
    REUSE_DETECTED = "reuse_detected"
    AUTHORIZATION_CHANGED = "authorization_changed"


class RefreshSession(AuditSoftDeleteMixin, Base):
    __tablename__ = "auth_refresh_session"
    __table_args__ = (
        Index(
            "ix_auth_refresh_session_active_family",
            "family_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_auth_refresh_session_user_id", "user_id"),
        Index("ix_auth_refresh_session_absolute_expires_at", "absolute_expires_at"),
        CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN "
            "('rotated', 'logout', 'reuse_detected', 'authorization_changed')",
            name="revoke_reason_allowed",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason IS NULL)",
            name="revocation_is_complete",
        ),
        CheckConstraint("idle_expires_at <= absolute_expires_at", name="idle_within_absolute"),
        {
            "comment": (
                "One row per issued refresh token of the application-foundation context. Rows "
                "of one login share family_id; each refresh ends the presented row as "
                "'rotated' and inserts its successor. Presenting an ended row ends the whole "
                "family as 'reuse_detected'. The token itself is never stored, only its SHA-256 "
                "digest. Rows whose end or expiry is older than seven days are deleted by the "
                "login flow."
            )
        },
    )

    auth_refresh_session_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenant.tenant_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Tenant of the signed-in user; references tenant.tenant_id.",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("app_user.user_id", ondelete="RESTRICT"),
        nullable=False,
        comment="Signed-in user; references app_user.user_id.",
    )
    family_id: Mapped[UUID] = mapped_column(
        Uuid,
        nullable=False,
        comment="Session family: every token issued from one login and its rotations.",
    )
    token_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="Lower-case hex SHA-256 digest of the refresh token; the token is never stored.",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC time the token was presented and rotated; empty while unused.",
    )
    idle_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC time the unused token expires for inactivity (60 minutes after issue).",
    )
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="UTC upper bound of the whole family (8 hours after login); never extended.",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC time the token stopped being usable; empty while usable.",
    )
    revoke_reason: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=(
            "Why the token ended; code reflection "
            "app.domain.models.refresh_session.RefreshSessionEndReason: 'rotated' = replaced "
            "by its successor, 'logout' = user logged out, 'reuse_detected' = an ended token "
            "was presented again, 'authorization_changed' = role or activation changed."
        ),
    )
