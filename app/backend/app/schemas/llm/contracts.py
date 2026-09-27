"""LLM connection settings and call summary contracts (sql-review 006-llm-connection)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EnvironmentValue = Literal["local", "nonprod"]
ChatApiValue = Literal["openai", "api_v1_chat"]
LlmCallOutcomeValue = Literal[
    "ok",
    "timeout",
    "connect_error",
    "tls_error",
    "network_policy_denied",
    "upstream_status",
    "invalid_response",
    "response_too_large",
    "cancelled",
]


class LlmConnectionView(BaseModel):
    """Nonprod returns only environment, editable, chat_api and model."""

    environment: EnvironmentValue
    editable: bool
    chat_api: ChatApiValue
    model: str
    base_url: str | None = None
    chat_url: str | None = None
    resolved_chat_url: str | None = None
    api_key_set: bool | None = None


class LlmConnectionUpdate(BaseModel):
    """Partial change; a missing api_key keeps the stored key and an empty one removes it."""

    model_config = ConfigDict(extra="forbid")

    chat_api: ChatApiValue | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    chat_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=256)
    api_key: str | None = Field(default=None, max_length=4096)


class LlmCallSummaryItem(BaseModel):
    public_id: str
    started_at: datetime
    review_run_id: str | None
    object_label: str
    rule_id: str
    part_index: int | None = Field(description="Empty for a single part, 1 or 2 otherwise.")
    attempt: int
    chat_api: ChatApiValue
    model: str
    endpoint_host: str
    streamed: bool
    outcome: LlmCallOutcomeValue
    http_status: int | None
    duration_ms: int
    completion_tokens: int | None
    prompt_tokens: int | None
    response_chars: int | None


class LlmCallSummaryPage(BaseModel):
    items: list[LlmCallSummaryItem]
    limit: int
    total: int
