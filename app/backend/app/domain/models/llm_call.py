"""Content-free summary of every LLM call attempt (sql-review/PRDs/006-llm-connection)."""

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
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.domain.models.mixins import AuditSoftDeleteMixin, new_public_id

LLM_CALL_SUMMARY_RETENTION_DAYS = 90


class LlmChatApi(StrEnum):
    """Request format of the LLM endpoint."""

    OPENAI = "openai"
    API_V1_CHAT = "api_v1_chat"


class LlmCallOutcome(StrEnum):
    """Result class of one attempt; everything except OK is a fixed failure class."""

    OK = "ok"
    TIMEOUT = "timeout"
    CONNECT_ERROR = "connect_error"
    TLS_ERROR = "tls_error"
    NETWORK_POLICY_DENIED = "network_policy_denied"
    UPSTREAM_STATUS = "upstream_status"
    INVALID_RESPONSE = "invalid_response"
    RESPONSE_TOO_LARGE = "response_too_large"
    CANCELLED = "cancelled"


class LlmCallSummary(AuditSoftDeleteMixin, Base):
    __tablename__ = "llm_call_summary"
    __table_args__ = (
        Index(
            "ix_llm_call_summary_active_tenant_started",
            "tenant_id",
            "started_at",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_llm_call_summary_started_at", "started_at"),
        CheckConstraint("chat_api IN ('openai', 'api_v1_chat')", name="chat_api_allowed"),
        CheckConstraint(
            "outcome IN ('ok', 'timeout', 'connect_error', 'tls_error', "
            "'network_policy_denied', 'upstream_status', 'invalid_response', "
            "'response_too_large', 'cancelled')",
            name="outcome_allowed",
        ),
        CheckConstraint("part_index IS NULL OR part_index IN (1, 2)", name="part_index_allowed"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="http_status_range"
        ),
        CheckConstraint(
            "(completion_tokens IS NULL OR completion_tokens >= 0)"
            " AND (prompt_tokens IS NULL OR prompt_tokens >= 0)"
            " AND (response_chars IS NULL OR response_chars >= 0)",
            name="counters_not_negative",
        ),
        {
            "comment": (
                "Metadata of one LLM call attempt (each retry is its own row); owned by the "
                "sql-review llm-connection capability. It never holds the prompt, SQL, object "
                "metadata, response text, server error body, key or headers. The application "
                "only inserts rows; the retention job deletes rows 90 days after started_at."
            )
        },
    )

    llm_call_summary_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
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
    review_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("review_run.review_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment=(
            "Review run that made the call; references review_run.review_run_id. The database "
            "empties it when the run is deleted and the summary stays until its own retention."
        ),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="UTC start time of the attempt."
    )
    object_label: Mapped[str] = mapped_column(
        String(400),
        nullable=False,
        comment=(
            "Reviewed object label ('[database] schema.name (type)') or '<label> (SCRIPT)' for "
            "pasted text; visible only to the rule manager."
        ),
    )
    rule_code: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="KuralNN code of the rule being evaluated."
    )
    part_index: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment=(
            "Part of a two-part analysis: 1 = '#1/2', 2 = '#2/2'; empty for a single-part call."
        ),
    )
    attempt: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment="Attempt number of the call, starting at 1."
    )
    chat_api: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment=(
            "Request format; code reflection app.domain.models.llm_call.LlmChatApi: "
            "'openai' = /chat/completions, 'api_v1_chat' = /api/v1/chat."
        ),
    )
    model: Mapped[str] = mapped_column(String(256), nullable=False, comment="Model identifier.")
    endpoint_host: Mapped[str] = mapped_column(
        String(253),
        nullable=False,
        comment="Host name of the endpoint only; never the path, query or credentials.",
    )
    streamed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="True when the response arrived as a stream."
    )
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment=(
            "Result class; code reflection app.domain.models.llm_call.LlmCallOutcome: 'ok', "
            "'timeout', 'connect_error', 'tls_error', 'network_policy_denied', "
            "'upstream_status', 'invalid_response', 'response_too_large', 'cancelled'."
        ),
    )
    http_status: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="HTTP status code when a response arrived."
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Duration of the attempt in milliseconds."
    )
    completion_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Completion tokens reported or counted for the call."
    )
    prompt_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Prompt tokens when the endpoint reports them."
    )
    response_chars: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Number of characters in the response text."
    )
