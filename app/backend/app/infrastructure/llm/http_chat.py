"""httpx adapter of LlmChatPort (sql-review/PRDs/006-llm-connection, Decision 1 and 5).

Transport behaviour ported from the previous application: ``openai`` streams SSE chunks from
``/chat/completions`` and falls back to a plain JSON body, ``api_v1_chat`` posts
``system_prompt`` + ``input`` without streaming, a 200 body with an ``error`` field or empty
text fails, and only connect/read timeouts are retried with a ``1.5 * 2^n`` second (at most 12 s)
wait. On top of it: verified TLS without proxies or redirects, the private-network policy, a
4 MiB response limit, run-wide and process-wide concurrency limits and one content-free summary
per attempt, with one content-free span and the Gözlemlenebilirlik metrics. No prompt, SQL,
response text, URL or server error body is logged, stored or traced.
"""

import asyncio
import json
import ssl
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpcore
import httpx

from app.core.telemetry import llm_attempt
from app.domain.llm import (
    MAX_RESPONSE_BYTES,
    PROGRESS_MIN_INTERVAL_SECONDS,
    LlmCallAttempt,
    LlmCallRecorder,
    LlmChatPort,
    LlmChatRequest,
    LlmChatResult,
    LlmEndpoint,
    LlmNotConfigured,
    LlmStreamProgress,
    LlmUsage,
    ProgressCallback,
)
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.domain.models.mixins import new_public_id
from app.infrastructure.llm.network import (
    HostUnresolved,
    NetworkPolicyDenied,
    PolicyTransport,
    PrivateNetworkBackend,
    Resolver,
    resolve_private,
    system_resolver,
    tls_context,
)
from app.infrastructure.llm.response_text import (
    error_field_message,
    extract_response_text,
    stream_delta,
    usage_tokens,
)

_CONNECT_TIMEOUT_CAP_SECONDS = 120.0
_RETRY_BASE_SECONDS = 1.5
_RETRY_MAX_SECONDS = 12.0
_SSE_CONTROL_PREFIXES = ("event:", "id:", "retry:", ":")


class _Failure(Exception):
    def __init__(self, outcome: LlmCallOutcome) -> None:
        super().__init__(outcome.value)
        self.outcome = outcome


@dataclass
class _Observed:
    """What one attempt learned; counters only."""

    streamed: bool = False
    http_status: int | None = None
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    response_chars: int | None = None


def retry_delay_seconds(attempt_index: int) -> float:
    """Wait before the attempt after ``attempt_index`` (0-based): 1.5, 3, 6, 12, 12 ..."""

    delay: float = _RETRY_BASE_SECONDS * 2.0**attempt_index
    return min(delay, _RETRY_MAX_SECONDS)


def _caused_by_tls(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, ssl.SSLError):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def classify_transport_error(error: BaseException) -> LlmCallOutcome:
    if isinstance(error, _Failure):
        return error.outcome
    if isinstance(error, NetworkPolicyDenied):
        return LlmCallOutcome.NETWORK_POLICY_DENIED
    if isinstance(error, (httpx.TimeoutException, httpcore.TimeoutException)):
        return LlmCallOutcome.TIMEOUT
    if isinstance(error, httpx.ConnectError):
        return LlmCallOutcome.TLS_ERROR if _caused_by_tls(error) else LlmCallOutcome.CONNECT_ERROR
    if isinstance(error, HostUnresolved):
        return LlmCallOutcome.CONNECT_ERROR
    if isinstance(error, (httpx.DecodingError, httpx.RemoteProtocolError)):
        return LlmCallOutcome.INVALID_RESPONSE
    if isinstance(error, httpx.TransportError):
        return LlmCallOutcome.TLS_ERROR if _caused_by_tls(error) else LlmCallOutcome.CONNECT_ERROR
    raise error


class _Progress:
    """At most one ``llm_stream`` event per 0.2 s for one call (Requirement 3)."""

    def __init__(self, callback: ProgressCallback | None, rule_code: str) -> None:
        self._callback = callback
        self._rule_code = rule_code
        self._last = float("-inf")
        self._pending: tuple[int | None, int] | None = None

    async def update(self, completion_tokens: int | None, total_chars: int) -> None:
        if self._callback is None:
            return
        self._pending = (completion_tokens, total_chars)
        now = time.monotonic()
        if now - self._last < PROGRESS_MIN_INTERVAL_SECONDS:
            return
        self._last = now
        self._pending = None
        await self._callback(LlmStreamProgress(self._rule_code, completion_tokens, total_chars))

    async def flush(self) -> None:
        if self._pending is not None:
            tokens, chars = self._pending
            await self.update(tokens, chars)


async def _bounded_lines(response: httpx.Response) -> AsyncIterator[str]:
    """Body lines; the call fails with response_too_large past 4 MiB (Requirement 5)."""

    received = 0
    buffer = b""
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > MAX_RESPONSE_BYTES:
            raise _Failure(LlmCallOutcome.RESPONSE_TOO_LARGE)
        buffer += chunk
        *lines, buffer = buffer.split(b"\n")
        for line in lines:
            yield line.decode("utf-8", errors="replace").rstrip("\r")
    if buffer:
        yield buffer.decode("utf-8", errors="replace").rstrip("\r")


async def _bounded_body(response: httpx.Response) -> bytes:
    received = bytearray()
    async for chunk in response.aiter_bytes():
        received.extend(chunk)
        if len(received) > MAX_RESPONSE_BYTES:
            raise _Failure(LlmCallOutcome.RESPONSE_TOO_LARGE)
    return bytes(received)


def _require_success_status(response: httpx.Response, observed: _Observed) -> None:
    observed.http_status = response.status_code
    # Redirects are never followed; any non-2xx status is an upstream failure.
    if not 200 <= response.status_code < 300:
        raise _Failure(LlmCallOutcome.UPSTREAM_STATUS)


def _text_from_body(body: object, observed: _Observed) -> str:
    if not isinstance(body, dict) or error_field_message(body) is not None:
        raise _Failure(LlmCallOutcome.INVALID_RESPONSE)
    observed.completion_tokens = usage_tokens(body, "completion_tokens")
    observed.prompt_tokens = usage_tokens(body, "prompt_tokens")
    text = extract_response_text(body).strip()
    if not text:
        raise _Failure(LlmCallOutcome.INVALID_RESPONSE)
    return text


def _headers(endpoint: LlmEndpoint) -> dict[str, str]:
    # Authorization is sent only when a key is configured (Requirement 8).
    return {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}


async def _openai_call(
    client: httpx.AsyncClient,
    endpoint: LlmEndpoint,
    request: LlmChatRequest,
    progress: _Progress,
    observed: _Observed,
) -> str:
    payload = {
        "model": endpoint.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_content},
        ],
        "stream": True,
    }
    async with client.stream(
        "POST", endpoint.chat_url, json=payload, headers=_headers(endpoint)
    ) as response:
        _require_success_status(response, observed)
        accumulated: list[str] = []
        total_chars = 0
        parsed_any_chunk = False
        json_lines: list[str] = []
        async for line in _bounded_lines(response):
            stripped = line.strip()
            if stripped.startswith("data:"):
                observed.streamed = True
                json_lines.clear()
                data = stripped[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(chunk, dict):
                    continue
                parsed_any_chunk = True
                delta = stream_delta(chunk)
                if delta:
                    accumulated.append(delta)
                    total_chars += len(delta)
                tokens = usage_tokens(chunk, "completion_tokens")
                if tokens is not None:
                    observed.completion_tokens = tokens
                prompt_tokens = usage_tokens(chunk, "prompt_tokens")
                if prompt_tokens is not None:
                    observed.prompt_tokens = prompt_tokens
                await progress.update(observed.completion_tokens, total_chars)
                continue
            if observed.streamed or not stripped or stripped.startswith(_SSE_CONTROL_PREFIXES):
                continue
            json_lines.append(line)

    if observed.streamed:
        await progress.flush()
        text = "".join(accumulated).strip()
        if not parsed_any_chunk or not text:
            raise _Failure(LlmCallOutcome.INVALID_RESPONSE)
        return text
    try:
        body: Any = json.loads("\n".join(json_lines)) if json_lines else None
    except json.JSONDecodeError:
        raise _Failure(LlmCallOutcome.INVALID_RESPONSE) from None
    text = _text_from_body(body, observed)
    await progress.update(observed.completion_tokens, len(text))
    return text


async def _api_v1_chat_call(
    client: httpx.AsyncClient,
    endpoint: LlmEndpoint,
    request: LlmChatRequest,
    progress: _Progress,
    observed: _Observed,
) -> str:
    payload = {
        "model": endpoint.model,
        "system_prompt": request.system_prompt,
        "input": request.user_content,
    }
    async with client.stream(
        "POST", endpoint.chat_url, json=payload, headers=_headers(endpoint)
    ) as response:
        _require_success_status(response, observed)
        raw = await _bounded_body(response)
    try:
        body: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _Failure(LlmCallOutcome.INVALID_RESPONSE) from None
    text = _text_from_body(body, observed)
    await progress.update(observed.completion_tokens, len(text))
    return text


class HttpLlmChat:
    """LlmChatPort over httpx; one instance per process holds the process-wide limit."""

    def __init__(
        self,
        *,
        endpoint: Callable[[], LlmEndpoint | None],
        recorder: LlmCallRecorder,
        ca_bundle: str,
        read_timeout_seconds: float,
        request_retries: int,
        run_max_concurrent_calls: int,
        process_max_concurrent_calls: int,
        user_agent: str,
        resolver: Resolver = system_resolver,
    ) -> None:
        self._endpoint = endpoint
        self._recorder = recorder
        self._ca_bundle = ca_bundle
        self._read_timeout = float(read_timeout_seconds)
        self._connect_timeout = min(_CONNECT_TIMEOUT_CAP_SECONDS, self._read_timeout)
        self._retries = request_retries
        self._run_limit = run_max_concurrent_calls
        self._process_slots = asyncio.Semaphore(process_max_concurrent_calls)
        self._user_agent = user_agent
        self._resolver = resolver

    @asynccontextmanager
    async def open_run(self) -> AsyncIterator["_Run"]:
        transport = PolicyTransport(
            ssl_context=tls_context(self._ca_bundle),
            max_connections=self._run_limit,
            network_backend=PrivateNetworkBackend(self._resolver),
        )
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(self._read_timeout, connect=self._connect_timeout),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": self._user_agent},
        ) as client:
            yield _Run(self, client)

    async def _call(
        self,
        client: httpx.AsyncClient,
        request: LlmChatRequest,
        progress: ProgressCallback | None,
    ) -> LlmChatResult:
        endpoint = self._endpoint()
        if endpoint is None:
            raise LlmNotConfigured()
        attempt = 1
        while True:
            result = await self._attempt(client, endpoint, request, progress, attempt)
            if result.outcome is not LlmCallOutcome.TIMEOUT or attempt > self._retries:
                return result
            await asyncio.sleep(retry_delay_seconds(attempt - 1))
            attempt += 1

    async def _attempt(
        self,
        client: httpx.AsyncClient,
        endpoint: LlmEndpoint,
        request: LlmChatRequest,
        progress_callback: ProgressCallback | None,
        attempt: int,
    ) -> LlmChatResult:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        observed = _Observed()
        progress = _Progress(progress_callback, request.target.rule_code)
        parts = urlsplit(endpoint.chat_url)
        host = parts.hostname or ""
        text: str | None = None
        with llm_attempt(
            model=endpoint.model, chat_api=endpoint.chat_api.value, attempt=attempt
        ) as call:
            try:
                await resolve_private(
                    self._resolver,
                    host,
                    parts.port or (443 if parts.scheme == "https" else 80),
                    timeout=self._connect_timeout,
                )
                if endpoint.chat_api is LlmChatApi.OPENAI:
                    text = await _openai_call(client, endpoint, request, progress, observed)
                else:
                    text = await _api_v1_chat_call(client, endpoint, request, progress, observed)
                outcome = LlmCallOutcome.OK
                observed.response_chars = len(text)
            except asyncio.CancelledError:
                call.outcome = LlmCallOutcome.CANCELLED.value
                call.http_status = observed.http_status
                await asyncio.shield(
                    self._record(
                        request,
                        endpoint,
                        host,
                        attempt,
                        started_at,
                        started,
                        LlmCallOutcome.CANCELLED,
                        observed,
                    )
                )
                raise
            except Exception as error:  # noqa: BLE001 - unknown errors propagate from classify
                outcome = classify_transport_error(error)
                text = None
            call.outcome = outcome.value
            call.http_status = observed.http_status
            call.completion_tokens = observed.completion_tokens
        await self._record(request, endpoint, host, attempt, started_at, started, outcome, observed)
        usage = LlmUsage(
            completion_tokens=observed.completion_tokens,
            prompt_tokens=observed.prompt_tokens,
            total_chars=observed.response_chars or 0,
        )
        return LlmChatResult(
            outcome=outcome, text=text, http_status=observed.http_status, usage=usage
        )

    async def _record(
        self,
        request: LlmChatRequest,
        endpoint: LlmEndpoint,
        host: str,
        attempt: int,
        started_at: datetime,
        started: float,
        outcome: LlmCallOutcome,
        observed: _Observed,
    ) -> None:
        await self._recorder.record(
            LlmCallAttempt(
                public_id=new_public_id(),
                target=request.target,
                started_at=started_at,
                attempt=attempt,
                chat_api=endpoint.chat_api,
                model=endpoint.model,
                endpoint_host=host,
                streamed=observed.streamed,
                outcome=outcome,
                http_status=observed.http_status,
                duration_ms=int((time.monotonic() - started) * 1000),
                completion_tokens=observed.completion_tokens,
                prompt_tokens=observed.prompt_tokens,
                response_chars=observed.response_chars,
            )
        )


class _Run:
    """One review run: one HTTP client and the run-wide limit (Requirement 7)."""

    def __init__(self, chat: HttpLlmChat, client: httpx.AsyncClient) -> None:
        self._chat = chat
        self._client = client
        self._run_slots = asyncio.Semaphore(chat._run_limit)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator["_Slot"]:
        async with self._run_slots, self._chat._process_slots:
            yield _Slot(self._chat, self._client)


class _Slot:
    def __init__(self, chat: HttpLlmChat, client: httpx.AsyncClient) -> None:
        self._chat = chat
        self._client = client

    async def chat(
        self, request: LlmChatRequest, *, progress: ProgressCallback | None = None
    ) -> LlmChatResult:
        return await self._chat._call(self._client, request, progress)


if TYPE_CHECKING:

    def _implements_port(chat: HttpLlmChat) -> LlmChatPort:
        return chat
