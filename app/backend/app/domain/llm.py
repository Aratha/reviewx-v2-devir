"""LLM chat port, endpoint rules and fixed failure classes (sql-review/PRDs/006-llm-connection).

Review services reach the approved internal LLM only through ``LlmChatPort`` (Decision 1). A
run opens one session (one HTTP client and the run-wide concurrency limit); every call takes a
slot in that session, and a two-part analysis makes both calls inside the same slot. Prompts,
SQL and response text never enter logs or summaries; the dataclasses keep them out of repr.
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi

# Requirement 5: the whole body, and the text accumulated from a stream, stay under 4 MiB.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
# Requirement 3: at most five progress events per second for one call.
PROGRESS_MIN_INTERVAL_SECONDS = 0.2

_FAILURE_MESSAGES: dict[LlmCallOutcome, str] = {
    LlmCallOutcome.TIMEOUT: "LLM sunucusu yanıt vermedi (zaman aşımı).",
    LlmCallOutcome.CONNECT_ERROR: "LLM sunucusuna bağlanılamadı.",
    LlmCallOutcome.TLS_ERROR: "LLM sunucusuyla güvenli bağlantı kurulamadı.",
    LlmCallOutcome.NETWORK_POLICY_DENIED: "LLM adresi kurum ağı politikası gereği engellendi.",
    LlmCallOutcome.UPSTREAM_STATUS: "LLM sunucusu hata döndürdü.",
    LlmCallOutcome.INVALID_RESPONSE: "LLM yanıtı çözümlenemedi.",
    LlmCallOutcome.RESPONSE_TOO_LARGE: "LLM yanıtı izin verilen boyutu aştı.",
    LlmCallOutcome.CANCELLED: "LLM isteği iptal edildi.",
}


def failure_message(outcome: LlmCallOutcome, http_status: int | None = None) -> str:
    """The short Turkish reason a reviewer sees (Requirement 9); never the server body."""

    if outcome is LlmCallOutcome.OK:
        raise ValueError("a successful call has no failure message")
    message = _FAILURE_MESSAGES[outcome]
    if outcome is LlmCallOutcome.UPSTREAM_STATUS and http_status is not None:
        return f"LLM sunucusu hata döndürdü (HTTP {http_status})."
    return message


class LlmNotConfigured(Exception):
    """No chat URL or model is configured; a review cannot call the LLM."""


@dataclass(frozen=True, slots=True)
class LlmEndpoint:
    """The effective endpoint of this process: format, resolved chat URL, model and key."""

    chat_api: LlmChatApi
    chat_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)


class LlmEndpointInvalid(ValueError):
    """A base or chat URL that Requirement 2 rejects."""


def validate_endpoint_url(url: str, *, allow_http: bool) -> str:
    """Accept only https (http locally) URLs with a host, no credentials and no fragment."""

    value = url.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise LlmEndpointInvalid("malformed") from None
    allowed = {"https", "http"} if allow_http else {"https"}
    if (
        parts.scheme not in allowed
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or "@" in parts.netloc
        or parts.fragment
        or "#" in value
        or (port is not None and not 1 <= port <= 65535)
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise LlmEndpointInvalid("rejected")
    return value


def _with_path(url: str, path: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def resolve_chat_url(chat_api: LlmChatApi, base_url: str, chat_url: str) -> str | None:
    """The chat endpoint of the previous application's rule; None while nothing is configured.

    openai: the chat URL when given (``/chat/completions`` appended after a trailing ``/v1``),
    otherwise the base URL plus ``/chat/completions``. api_v1_chat: the chat URL when given,
    otherwise the base URL without a trailing ``/v1`` plus ``/api/v1/chat``.
    """

    explicit = chat_url.strip()
    base = base_url.strip()
    if chat_api is LlmChatApi.OPENAI:
        if not explicit and not base:
            return None
        source = explicit or base
        path = urlsplit(source).path.rstrip("/")
        if not explicit or path.endswith("/v1"):
            path = f"{path}/chat/completions"
        return _with_path(source, path)
    if explicit:
        return _with_path(explicit, urlsplit(explicit).path.rstrip("/"))
    if not base:
        return None
    path = urlsplit(base).path.rstrip("/").removesuffix("/v1")
    return _with_path(base, f"{path}/api/v1/chat")


@dataclass(frozen=True, slots=True)
class LlmCallTarget:
    """What a call belongs to; recorded in the content-free call summary (Requirement 10)."""

    tenant_id: int
    object_label: str
    rule_code: str
    review_run_id: int | None = None
    review_run_public_id: str | None = None
    # None for a single-part call, 1 or 2 for the parts of a two-part analysis.
    part_index: int | None = None


@dataclass(frozen=True, slots=True)
class LlmChatRequest:
    target: LlmCallTarget
    system_prompt: str = field(repr=False)
    user_content: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LlmStreamProgress:
    """The ``llm_stream`` event content: rule code and counters only, never text."""

    rule_code: str
    completion_tokens: int | None
    total_chars: int


ProgressCallback = Callable[[LlmStreamProgress], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class LlmUsage:
    completion_tokens: int | None
    prompt_tokens: int | None
    total_chars: int


@dataclass(frozen=True, slots=True)
class LlmChatResult:
    """The response text, or a fixed failure class with the HTTP status when one arrived."""

    outcome: LlmCallOutcome
    text: str | None = field(default=None, repr=False)
    http_status: int | None = None
    usage: LlmUsage | None = None

    @property
    def ok(self) -> bool:
        return self.outcome is LlmCallOutcome.OK

    @property
    def failure_message(self) -> str | None:
        return None if self.ok else failure_message(self.outcome, self.http_status)


class LlmCallSlot(Protocol):
    async def chat(
        self, request: LlmChatRequest, *, progress: ProgressCallback | None = None
    ) -> LlmChatResult:
        """One call with its retries; cancellation closes it and re-raises."""
        ...


class LlmRunSession(Protocol):
    def slot(self) -> AbstractAsyncContextManager[LlmCallSlot]:
        """Wait for a run slot and a process slot; a cancelled wait never starts a call."""
        ...


class LlmChatPort(Protocol):
    def open_run(self) -> AbstractAsyncContextManager[LlmRunSession]:
        """One review run: a single HTTP client and the run-wide concurrency limit."""
        ...


@dataclass(frozen=True, slots=True)
class LlmCallAttempt:
    """Metadata of one attempt, the only persisted trace of an LLM call (Requirement 10)."""

    public_id: str
    target: LlmCallTarget
    started_at: datetime
    attempt: int
    chat_api: LlmChatApi
    model: str
    endpoint_host: str
    streamed: bool
    outcome: LlmCallOutcome
    http_status: int | None
    duration_ms: int
    completion_tokens: int | None
    prompt_tokens: int | None
    response_chars: int | None


class LlmCallRecorder(Protocol):
    async def record(self, attempt: LlmCallAttempt) -> None:
        """Persist and log one attempt; a failure to persist must not stop the review."""
        ...
