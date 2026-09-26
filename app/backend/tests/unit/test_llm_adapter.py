"""The httpx LLM adapter against a real-TCP fake endpoint with its own test CA.

sql-review/PRDs/006-llm-connection Requirement 2-9 (Acceptance 1) and Requirement 7 (Acceptance
2): formats, streaming, error classes, retries, TLS, the private-network policy, the response
limit, the User-Agent, cancellation and the run-wide and process-wide concurrency limits.
"""

import asyncio
import itertools
import json
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpcore
import pytest

from app.domain.llm import (
    MAX_RESPONSE_BYTES,
    LlmCallAttempt,
    LlmCallTarget,
    LlmChatRequest,
    LlmEndpoint,
    LlmEndpointInvalid,
    LlmNotConfigured,
    LlmStreamProgress,
    failure_message,
    resolve_chat_url,
    validate_endpoint_url,
)
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.infrastructure.llm import http_chat
from app.infrastructure.llm.http_chat import HttpLlmChat, retry_delay_seconds
from app.infrastructure.llm.network import (
    NetworkPolicyDenied,
    PrivateNetworkBackend,
    is_private_address,
)
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    Writer,
    chunk,
    http_response,
    openai_delta,
    sse_event,
    sse_head,
    write_pki,
)

pytestmark = pytest.mark.unit

USER_AGENT = "DWHCodeReview-Backend/1.0 (internal SQL review; httpx)"
MARKER = f"GIZLI-{uuid4().hex}"
TARGET = LlmCallTarget(
    tenant_id=1, object_label="[DWH] dbo.usp_Load (PROCEDURE)", rule_code="Kural05"
)


class Recorder:
    def __init__(self) -> None:
        self.attempts: list[LlmCallAttempt] = []

    async def record(self, attempt: LlmCallAttempt) -> None:
        self.attempts.append(attempt)


def _request(target: LlmCallTarget = TARGET) -> LlmChatRequest:
    return LlmChatRequest(
        target=target,
        system_prompt=f"sistem {MARKER}",
        user_content=f"SELECT '{MARKER}' FROM dbo.Musteri",
    )


async def private_resolver(host: str, port: int) -> list[str]:
    assert host == HOST_NAME
    return ["127.0.0.1"]


@pytest.fixture
def pki(tmp_path: Path) -> Any:
    return write_pki(tmp_path / "pki")


@pytest.fixture
async def server(pki: Any) -> AsyncIterator[FakeLlmServer]:
    fake = await FakeLlmServer(pki).start()
    try:
        yield fake
    finally:
        await fake.close()


@pytest.fixture
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_chat, "retry_delay_seconds", lambda attempt: 0.0)


def _chat(
    server: FakeLlmServer,
    recorder: Recorder,
    *,
    chat_api: LlmChatApi = LlmChatApi.OPENAI,
    path: str = "/v1/chat/completions",
    api_key: str | None = None,
    resolver: Any = private_resolver,
    read_timeout: float = 5.0,
    retries: int = 2,
    run_limit: int = 6,
    process_limit: int = 12,
    ca_bundle: str | None = None,
) -> HttpLlmChat:
    endpoint = LlmEndpoint(chat_api, server.url(path), "test-model", api_key)
    return HttpLlmChat(
        endpoint=lambda: endpoint,
        recorder=recorder,
        ca_bundle=ca_bundle or str(server.pki.ca_path),
        read_timeout_seconds=read_timeout,
        request_retries=retries,
        run_max_concurrent_calls=run_limit,
        process_max_concurrent_calls=process_limit,
        user_agent=USER_AGENT,
        resolver=resolver,
    )


async def _one_call(chat: HttpLlmChat, progress: Any = None) -> Any:
    async with chat.open_run() as run, run.slot() as slot:
        return await slot.chat(_request(), progress=progress)


def reply(payload: bytes) -> Any:
    async def scenario(request: RecordedRequest, writer: Writer) -> None:
        writer.write(payload)
        await writer.drain()

    return scenario


# --- pure rules ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chat_api", "base", "chat", "expected"),
    [
        (
            LlmChatApi.OPENAI,
            "https://h/inference/m/v1",
            "",
            "https://h/inference/m/v1/chat/completions",
        ),
        (LlmChatApi.OPENAI, "https://h/v1/", "", "https://h/v1/chat/completions"),
        (LlmChatApi.OPENAI, "", "https://h/v1", "https://h/v1/chat/completions"),
        (
            LlmChatApi.OPENAI,
            "https://x",
            "https://h/v1/chat/completions/",
            "https://h/v1/chat/completions",
        ),
        (LlmChatApi.OPENAI, "", "https://h/custom", "https://h/custom"),
        (
            LlmChatApi.API_V1_CHAT,
            "http://127.0.0.1:1234/v1",
            "",
            "http://127.0.0.1:1234/api/v1/chat",
        ),
        (LlmChatApi.API_V1_CHAT, "http://127.0.0.1:1234", "", "http://127.0.0.1:1234/api/v1/chat"),
        (LlmChatApi.API_V1_CHAT, "http://x/v1", "http://h/api/v1/chat/", "http://h/api/v1/chat"),
        (LlmChatApi.OPENAI, "", "", None),
    ],
)
def test_chat_url_follows_the_source_rule(
    chat_api: LlmChatApi, base: str, chat: str, expected: str | None
) -> None:
    assert resolve_chat_url(chat_api, base, chat) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@h/v1",
        "https://user@h/v1",
        "https://h/v1#part",
        "ftp://h/v1",
        "https:///v1",
        "https://h:99999/v1",
        "https://h/v 1",
        "javascript:alert(1)",
    ],
)
def test_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(LlmEndpointInvalid):
        validate_endpoint_url(url, allow_http=True)


def test_http_is_accepted_only_when_allowed() -> None:
    assert validate_endpoint_url("http://127.0.0.1:1234/v1", allow_http=True)
    with pytest.raises(LlmEndpointInvalid):
        validate_endpoint_url("http://127.0.0.1:1234/v1", allow_http=False)


def test_retry_waits_grow_and_stop_at_twelve_seconds() -> None:
    assert [retry_delay_seconds(n) for n in range(5)] == [1.5, 3.0, 6.0, 12.0, 12.0]


@pytest.mark.parametrize(
    ("address", "private"),
    [
        ("10.14.3.99", True),
        ("172.16.0.1", True),
        ("172.32.0.1", False),
        ("192.168.1.1", True),
        ("127.0.0.1", True),
        ("169.254.10.1", True),
        ("100.64.0.1", True),
        ("100.128.0.1", False),
        ("8.8.8.8", False),
        ("::1", True),
        ("fe80::1%eth0", True),
        ("fd12:3456::1", True),
        ("2001:4860::8888", False),
        ("::ffff:10.0.0.1", True),
        ("::ffff:8.8.8.8", False),
        ("not-an-address", False),
    ],
)
def test_private_ranges_are_the_policy_ranges(address: str, private: bool) -> None:
    assert is_private_address(address) is private


def test_failure_messages_are_short_turkish_and_carry_only_the_status() -> None:
    assert failure_message(LlmCallOutcome.TIMEOUT) == "LLM sunucusu yanıt vermedi (zaman aşımı)."
    assert failure_message(LlmCallOutcome.UPSTREAM_STATUS, 503) == (
        "LLM sunucusu hata döndürdü (HTTP 503)."
    )
    for outcome in LlmCallOutcome:
        if outcome is not LlmCallOutcome.OK:
            message = failure_message(outcome, 500)
            assert ".env" not in message and "LM Studio" not in message and "http" not in message


# --- real TCP ----------------------------------------------------------------------------------


async def test_openai_stream_returns_text_counts_and_throttled_progress(
    server: FakeLlmServer,
) -> None:
    async def scenario(request: RecordedRequest, writer: Writer) -> None:
        writer.write(sse_head())
        for index in range(12):
            writer.write(sse_event(openai_delta(f"parça{index} ")))
            await writer.drain()
            await asyncio.sleep(0.05)
        writer.write(sse_event(openai_delta(f"{MARKER}", completion_tokens=13)))
        writer.write(chunk(b"data: [DONE]\n\n") + chunk(b""))
        await writer.drain()

    server.scenario = scenario
    recorder = Recorder()
    events: list[tuple[float, LlmStreamProgress]] = []

    async def progress(event: LlmStreamProgress) -> None:
        events.append((asyncio.get_running_loop().time(), event))

    result = await _one_call(_chat(server, recorder), progress)

    assert result.ok and result.text.endswith(MARKER)
    assert result.usage.completion_tokens == 13 and result.usage.prompt_tokens == 7
    (request,) = server.requests
    assert request.path == "/v1/chat/completions"
    assert request.headers["user-agent"] == USER_AGENT
    assert "authorization" not in request.headers
    assert request.json() == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": f"sistem {MARKER}"},
            {"role": "user", "content": f"SELECT '{MARKER}' FROM dbo.Musteri"},
        ],
        "stream": True,
    }
    assert events and all(e.rule_code == "Kural05" for _, e in events)
    gaps = [b[0] - a[0] for a, b in itertools.pairwise(events)]
    assert all(gap >= 0.19 for gap in gaps)
    (attempt,) = recorder.attempts
    assert attempt.outcome is LlmCallOutcome.OK and attempt.streamed is True
    assert (attempt.attempt, attempt.chat_api, attempt.model) == (
        1,
        LlmChatApi.OPENAI,
        "test-model",
    )
    assert attempt.endpoint_host == HOST_NAME and attempt.http_status == 200
    assert attempt.completion_tokens == 13 and attempt.response_chars == len(result.text)
    assert MARKER not in repr(attempt) and MARKER not in repr(result)


async def test_openai_without_stream_reads_the_json_body(server: FakeLlmServer) -> None:
    body = {"choices": [{"message": {"content": " yanıt "}}], "usage": {"completion_tokens": 3}}
    server.scenario = reply(http_response(200, json.dumps(body).encode()))
    recorder = Recorder()

    result = await _one_call(_chat(server, recorder))

    assert (result.ok, result.text, result.usage.completion_tokens) == (True, "yanıt", 3)
    assert recorder.attempts[0].streamed is False


async def test_api_v1_chat_posts_system_prompt_and_input(server: FakeLlmServer) -> None:
    body = {
        "output": [
            {"type": "reasoning", "content": "düşünce"},
            {"type": "message", "content": "sonuç"},
        ]
    }
    server.scenario = reply(http_response(200, json.dumps(body).encode()))
    recorder = Recorder()
    progress_events: list[LlmStreamProgress] = []

    async def progress(event: LlmStreamProgress) -> None:
        progress_events.append(event)

    result = await _one_call(
        _chat(
            server, recorder, chat_api=LlmChatApi.API_V1_CHAT, path="/api/v1/chat", api_key="k-1"
        ),
        progress,
    )

    assert result.ok and result.text == "sonuç"
    (request,) = server.requests
    assert request.path == "/api/v1/chat"
    assert request.headers["authorization"] == "Bearer k-1"
    assert request.json() == {
        "model": "test-model",
        "system_prompt": f"sistem {MARKER}",
        "input": f"SELECT '{MARKER}' FROM dbo.Musteri",
    }
    assert progress_events == [LlmStreamProgress("Kural05", None, len("sonuç"))]


@pytest.mark.parametrize(
    ("payload", "outcome", "status"),
    [
        (
            http_response(200, json.dumps({"error": f"model yok {MARKER}"}).encode()),
            "invalid_response",
            200,
        ),
        (
            http_response(200, b'{"choices": [{"message": {"content": "  "}}]}'),
            "invalid_response",
            200,
        ),
        (http_response(200, b"<html>not json</html>"), "invalid_response", 200),
        (http_response(500, f"iç hata {MARKER}".encode()), "upstream_status", 500),
        (
            http_response(302, b"", extra="Location: https://example.com/elsewhere\r\n"),
            "upstream_status",
            302,
        ),
        (sse_head() + chunk(b"data: not-json\n\n") + chunk(b""), "invalid_response", 200),
    ],
)
async def test_failures_map_to_fixed_classes_without_retry(
    server: FakeLlmServer, payload: bytes, outcome: str, status: int
) -> None:
    server.scenario = reply(payload)
    recorder = Recorder()

    result = await _one_call(_chat(server, recorder))

    assert result.outcome.value == outcome and result.http_status == status
    assert result.text is None
    assert len(server.requests) == 1 and len(recorder.attempts) == 1
    assert MARKER not in (result.failure_message or "")


async def test_a_hanging_endpoint_times_out_and_is_retried(
    server: FakeLlmServer, no_retry_wait: None
) -> None:
    async def hang(request: RecordedRequest, writer: Writer) -> None:
        await asyncio.sleep(10)

    server.scenario = hang
    recorder = Recorder()

    result = await _one_call(_chat(server, recorder, read_timeout=0.3, retries=2))

    assert result.outcome is LlmCallOutcome.TIMEOUT
    assert result.failure_message == "LLM sunucusu yanıt vermedi (zaman aşımı)."
    assert [a.attempt for a in recorder.attempts] == [1, 2, 3]
    assert all(a.outcome is LlmCallOutcome.TIMEOUT for a in recorder.attempts)
    assert len(server.requests) == 3


async def test_a_refused_connection_is_not_retried(pki: Any, no_retry_wait: None) -> None:
    closed = await FakeLlmServer(pki).start()
    await closed.close()
    recorder = Recorder()

    result = await _one_call(_chat(closed, recorder))

    assert result.outcome is LlmCallOutcome.CONNECT_ERROR
    assert len(recorder.attempts) == 1


async def test_bodies_over_four_mebibytes_are_cut(server: FakeLlmServer) -> None:
    async def huge(request: RecordedRequest, writer: Writer) -> None:
        writer.write(sse_head())
        piece = sse_event(openai_delta("x" * 60_000))
        for _ in range(MAX_RESPONSE_BYTES // 60_000 + 5):
            writer.write(piece)
            await writer.drain()

    server.scenario = huge
    result = await _one_call(_chat(server, Recorder()))
    assert result.outcome is LlmCallOutcome.RESPONSE_TOO_LARGE


async def test_an_untrusted_certificate_is_a_tls_error_and_no_body_arrives(
    pki: Any, tmp_path: Path
) -> None:
    impostor = await FakeLlmServer(pki).start(certificate=write_pki(tmp_path / "impostor"))
    impostor.scenario = reply(http_response(200, b'{"choices":[{"message":{"content":"x"}}]}'))
    try:
        result = await _one_call(_chat(impostor, Recorder()))
    finally:
        await impostor.close()
    assert result.outcome is LlmCallOutcome.TLS_ERROR
    assert impostor.requests == []


async def test_a_public_address_is_denied_before_any_connection(server: FakeLlmServer) -> None:
    async def public(host: str, port: int) -> list[str]:
        return ["127.0.0.1", "93.184.216.34"]

    recorder = Recorder()
    result = await _one_call(_chat(server, recorder, resolver=public))

    assert result.outcome is LlmCallOutcome.NETWORK_POLICY_DENIED
    assert server.connections == 0 and server.requests == []
    assert recorder.attempts[0].outcome is LlmCallOutcome.NETWORK_POLICY_DENIED


async def test_an_address_that_changes_at_connect_time_is_denied(server: FakeLlmServer) -> None:
    answers = iter([["127.0.0.1"], ["93.184.216.34"]])

    async def rebinding(host: str, port: int) -> list[str]:
        return next(answers)

    result = await _one_call(_chat(server, Recorder(), resolver=rebinding))

    assert result.outcome is LlmCallOutcome.NETWORK_POLICY_DENIED
    assert server.connections == 0 and server.requests == []


class _PublicPeerStream(httpcore.AsyncNetworkStream):
    closed = False

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        raise AssertionError("no byte may be read")

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        raise AssertionError("no byte may be written")

    async def aclose(self) -> None:
        self.closed = True

    def get_extra_info(self, info: str) -> Any:
        return ("198.51.100.7", 443) if info == "server_addr" else None


class _PublicPeerBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.stream = _PublicPeerStream()

    async def connect_tcp(self, host: str, port: int, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        return self.stream

    async def connect_unix_socket(self, path: str, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise AssertionError

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def test_the_connected_peer_address_is_checked_too() -> None:
    inner = _PublicPeerBackend()
    backend = PrivateNetworkBackend(private_resolver, inner)
    with pytest.raises(NetworkPolicyDenied):
        await backend.connect_tcp(HOST_NAME, 443, timeout=1)
    assert inner.stream.closed


async def test_proxies_from_the_environment_are_ignored(
    server: FakeLlmServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "HTTP_PROXY"):
        monkeypatch.setenv(name, "http://10.255.255.1:3128")
    server.scenario = reply(http_response(200, b'{"choices":[{"message":{"content":"ok"}}]}'))
    result = await _one_call(_chat(server, Recorder()))
    assert result.ok and len(server.requests) == 1


async def test_a_cancelled_call_is_closed_and_recorded_as_cancelled(server: FakeLlmServer) -> None:
    started = asyncio.Event()

    async def hang(request: RecordedRequest, writer: Writer) -> None:
        started.set()
        await asyncio.sleep(10)

    server.scenario = hang
    recorder = Recorder()
    task = asyncio.create_task(_one_call(_chat(server, recorder)))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [a.outcome for a in recorder.attempts] == [LlmCallOutcome.CANCELLED]


async def test_a_missing_endpoint_is_reported_before_any_call() -> None:
    chat = HttpLlmChat(
        endpoint=lambda: None,
        recorder=Recorder(),
        ca_bundle="",
        read_timeout_seconds=60,
        request_retries=0,
        run_max_concurrent_calls=1,
        process_max_concurrent_calls=1,
        user_agent=USER_AGENT,
    )
    async with chat.open_run() as run, run.slot() as slot:
        with pytest.raises(LlmNotConfigured):
            await slot.chat(_request())


def _slow_ok(delay: float) -> Any:
    async def scenario(request: RecordedRequest, writer: Writer) -> None:
        await asyncio.sleep(delay)
        writer.write(http_response(200, b'{"choices":[{"message":{"content":"ok"}}]}'))
        await writer.drain()

    return scenario


async def test_one_run_never_exceeds_its_limit_across_objects(server: FakeLlmServer) -> None:
    """3 objects x 10 rules in one run with a run limit of 4."""

    server.scenario = _slow_ok(0.05)
    chat = _chat(server, Recorder(), run_limit=4, process_limit=12)

    async with chat.open_run() as run:

        async def rule(object_index: int, rule_index: int) -> bool:
            target = LlmCallTarget(1, f"obj{object_index}", f"Kural{rule_index + 1:02d}")
            async with run.slot() as slot:
                result = await slot.chat(_request(target))
            return result.ok

        results = await asyncio.gather(*(rule(o, r) for o in range(3) for r in range(10)))

    assert all(results) and len(server.requests) == 30
    assert server.peak <= 4


async def test_parallel_runs_share_the_process_limit(server: FakeLlmServer) -> None:
    server.scenario = _slow_ok(0.05)
    chat = _chat(server, Recorder(), run_limit=4, process_limit=5)

    async def run_of(calls: int) -> None:
        async with chat.open_run() as run:

            async def one() -> None:
                async with run.slot() as slot:
                    assert (await slot.chat(_request())).ok

            await asyncio.gather(*(one() for _ in range(calls)))

    await asyncio.gather(run_of(12), run_of(12))
    assert len(server.requests) == 24
    assert server.peak <= 5


async def test_a_cancelled_run_never_starts_its_waiting_calls(server: FakeLlmServer) -> None:
    release = asyncio.Event()

    async def blocked(request: RecordedRequest, writer: Writer) -> None:
        await release.wait()

    server.scenario = blocked
    recorder = Recorder()
    chat = _chat(server, recorder, run_limit=1)

    async def run() -> None:
        async with chat.open_run() as session:

            async def one() -> None:
                async with session.slot() as slot:
                    await slot.chat(_request())

            await asyncio.gather(*(one() for _ in range(5)))

    task = asyncio.create_task(run())
    while not server.requests:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert len(server.requests) == 1
    assert [a.outcome for a in recorder.attempts] == [LlmCallOutcome.CANCELLED]


@pytest.fixture
def all_logs() -> Iterator[list[logging.LogRecord]]:
    captured: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = Handler(level=logging.DEBUG)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield captured
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


async def test_no_prompt_sql_or_response_text_reaches_the_logs(
    server: FakeLlmServer, all_logs: list[logging.LogRecord]
) -> None:
    server.scenario = reply(
        http_response(200, json.dumps({"choices": [{"message": {"content": MARKER}}]}).encode())
    )
    ok = await _one_call(_chat(server, Recorder()))
    server.scenario = reply(http_response(500, MARKER.encode()))
    failed = await _one_call(_chat(server, Recorder()))

    assert ok.text == MARKER and failed.outcome is LlmCallOutcome.UPSTREAM_STATUS
    for record in all_logs:
        rendered = record.getMessage() + repr(getattr(record, "structured_fields", {}))
        rendered += repr(record.args) + repr(record.exc_info)
        assert MARKER not in rendered
