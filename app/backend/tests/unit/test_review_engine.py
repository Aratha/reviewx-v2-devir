"""Per-rule review of one text through the LLM port (sql-review 003 Requirement 6-9, 12, 17).

``ScriptedLlm`` is a signature-constrained ``LlmChatPort``; the concurrency tests also drive the
real httpx adapter against the real-TCP fake endpoint, so the run-wide and process-wide limits
are observed at the network boundary (Acceptance 2).
"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.domain.llm import LlmChatRequest, LlmEndpoint
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.domain.review import (
    MetadataContext,
    MetadataSource,
    ReviewRule,
    RulePriorityGroup,
    RuleResultStatus,
    Severity,
)
from app.infrastructure.llm.http_chat import HttpLlmChat
from app.services.review_engine import (
    ReviewScope,
    RuleEvent,
    RuleFinished,
    RulesBatchStarted,
    RuleStarted,
    RuleStreamed,
    TextReviewer,
)
from app.services.review_prompts import SYSTEM_PROMPT
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    Writer,
    http_response,
    write_pki,
)
from tests.fakes.review_ports import ScriptedLlm, failed, ok, rule_code_of

pytestmark = pytest.mark.unit

CRITICAL = RulePriorityGroup.CRITICAL
NORMAL = RulePriorityGroup.NORMAL
MARKER = f"GIZLI-{uuid4().hex}"
SQL = "\n".join(
    [
        "CREATE PROCEDURE dbo.usp_Load",
        "AS",
        "BEGIN",
        f"    SELECT * FROM dbo.Musteri -- {MARKER}",
        "    WHERE Kimlik IS NULL",
        "END",
    ]
)
RULES = (
    ReviewRule("Kural03", CRITICAL, "Yıldız kullanma.", requires_metadata=True),
    ReviewRule("Kural01", CRITICAL, "NULL karşılaştırmasını denetle."),
    ReviewRule("Kural02", NORMAL, "Şema adı yaz.", requires_metadata=True),
)
SCOPE = ReviewScope(
    tenant_id=7,
    object_label="[DWH] dbo.usp_Load (PROCEDURE)",
    review_run_id=41,
    review_run_public_id="koşum-41",
)


class Events:
    def __init__(self) -> None:
        self.items: list[RuleEvent] = []

    async def __call__(self, event: RuleEvent) -> None:
        self.items.append(event)


async def _review(
    llm: ScriptedLlm,
    *,
    sql: str = SQL,
    rules: tuple[ReviewRule, ...] = RULES,
    metadata: MetadataContext | None = None,
    threshold: int = 45_000,
    events: Events | None = None,
    note: str | None = None,
) -> Any:
    reviewer = TextReviewer(two_part_threshold_chars=threshold)
    async with llm.open_run() as session:
        return await reviewer.review(
            session,
            sql=sql,
            rules=rules,
            metadata=metadata or MetadataContext(MetadataSource.FETCHED, "dbo.Musteri(Kimlik)"),
            scope=SCOPE,
            emit=events or Events(),
            leading_note=note,
        )


def _violation_for(code: str, snippet: str = "SELECT * FROM dbo.Musteri") -> str:
    return json.dumps(
        {"violations": [{"rule_code": code, "snippet": snippet, "reason": f"{code} ihlali"}]}
    )


async def test_one_call_per_rule_in_published_order_with_the_run_targets() -> None:
    llm = ScriptedLlm(responder=lambda request: ok(_violation_for(rule_code_of(request))))
    review = await _review(llm)

    assert [check.rule_code for check in review.checks] == ["Kural03", "Kural01", "Kural02"]
    assert [check.status for check in review.checks] == [RuleResultStatus.FAIL] * 3
    assert [check.severity for check in review.checks] == [
        Severity.HIGH,
        Severity.HIGH,
        Severity.LOW,
    ]
    assert sorted(rule_code_of(call.request) for call in llm.calls) == [
        "Kural01",
        "Kural02",
        "Kural03",
    ]
    assert llm.runs_opened == 1
    for call in llm.calls:
        assert call.request.system_prompt == SYSTEM_PROMPT
        assert call.target.tenant_id == 7
        assert call.target.object_label == "[DWH] dbo.usp_Load (PROCEDURE)"
        assert call.target.review_run_id == 41
        assert call.target.review_run_public_id == "koşum-41"
        assert call.target.part_index is None
        assert "L004      SELECT * FROM dbo.Musteri" in call.request.user_content
    assert [finding.line_reference for finding in review.findings] == ["Satır 4"] * 3


def _prompt_for(llm: ScriptedLlm, code: str) -> str:
    return next(c.request.user_content for c in llm.calls if rule_code_of(c.request) == code)


async def test_metadata_goes_only_to_flagged_rules() -> None:
    llm = ScriptedLlm()
    await _review(llm)
    assert "dbo.Musteri(Kimlik)" in _prompt_for(llm, "Kural03")
    assert "dbo.Musteri(Kimlik)" in _prompt_for(llm, "Kural02")
    assert "KATALOG METADATASI" not in _prompt_for(llm, "Kural01")


@pytest.mark.parametrize(
    ("metadata", "note"),
    [
        (MetadataContext(MetadataSource.FAILED), "özeti alınamadı; yalnızca SQL metnine güven"),
        (
            MetadataContext(MetadataSource.NOT_AVAILABLE_FOR_SCRIPT),
            "yapıştırılan SQL veya bağlantı olmadığı",
        ),
        (MetadataContext(MetadataSource.FETCHED, "  "), "nesne çözülemedi veya bağımlı tablo"),
    ],
)
async def test_flagged_rules_get_a_note_when_no_metadata_exists(
    metadata: MetadataContext, note: str
) -> None:
    llm = ScriptedLlm()
    await _review(llm, metadata=metadata)
    assert note in _prompt_for(llm, "Kural03")
    assert "KATALOG METADATASI" not in _prompt_for(llm, "Kural01")


async def test_above_the_threshold_each_rule_is_asked_twice_in_one_slot() -> None:
    llm = ScriptedLlm(run_limit=1)
    events = Events()
    review = await _review(llm, threshold=len(SQL) - 1, events=events)

    assert len(llm.calls) == 6
    assert llm.peak == 1
    for code in ("Kural01", "Kural02", "Kural03"):
        parts = [c for c in llm.calls if rule_code_of(c.request) == code]
        assert [c.target.part_index for c in parts] == [1, 2]
        assert "ÖNEMLİ — PARÇA 1/2: Aşağıdaki kod yalnızca nesnenin satır 1–3" in (
            parts[0].request.user_content
        )
        assert "L001  CREATE PROCEDURE" in parts[0].request.user_content
        assert "L004      SELECT" in parts[1].request.user_content
        assert "L001  CREATE" not in parts[1].request.user_content
    assert all(check.status is RuleResultStatus.PASS for check in review.checks)
    started = [event for event in events.items if isinstance(event, RuleStarted)]
    assert all(event.two_part for event in started)


async def test_a_single_line_text_below_the_threshold_is_one_call() -> None:
    llm = ScriptedLlm()
    await _review(llm, sql="SELECT 1", threshold=8)
    assert len(llm.calls) == 3


async def test_llm_failures_are_unknown_with_the_fixed_message_and_one_warning_line() -> None:
    def responder(request: LlmChatRequest) -> Any:
        if rule_code_of(request) == "Kural02":
            return ok('{"violations": []}')
        return failed(LlmCallOutcome.CONNECT_ERROR)

    review = await _review(ScriptedLlm(responder=responder))
    unknown = [check for check in review.checks if check.status is RuleResultStatus.UNKNOWN]
    assert [check.rule_code for check in unknown] == ["Kural03", "Kural01"]
    assert {check.description for check in unknown} == {"LLM sunucusuna bağlanılamadı."}
    assert review.warning == "[Kural03, Kural01] LLM sunucusuna bağlanılamadı."
    assert review.checks[2].status is RuleResultStatus.PASS


async def test_an_upstream_status_shows_only_the_http_code() -> None:
    review = await _review(
        ScriptedLlm(responder=lambda request: failed(LlmCallOutcome.UPSTREAM_STATUS, 502)),
        rules=RULES[1:2],
    )
    assert review.checks[0].description == "LLM sunucusu hata döndürdü (HTTP 502)."
    assert HOST_NAME not in (review.warning or "")


async def test_a_two_part_rule_with_one_failed_part_uses_the_other_part() -> None:
    def responder(request: LlmChatRequest) -> Any:
        if request.target.part_index == 1:
            return failed(LlmCallOutcome.TIMEOUT)
        return ok(_violation_for(rule_code_of(request), "WHERE Kimlik IS NULL"))

    review = await _review(
        ScriptedLlm(responder=responder), rules=RULES[1:2], threshold=len(SQL) - 1
    )
    assert review.checks[0].status is RuleResultStatus.FAIL
    assert review.findings[0].line_reference == "Satır 5"
    assert review.warning == (
        "[Kural01] Parça 1/2 LLM isteği başarısız; yalnızca parça 2 değerlendirildi."
    )


async def test_a_two_part_rule_with_both_parts_failed_is_unknown() -> None:
    review = await _review(
        ScriptedLlm(responder=lambda request: failed(LlmCallOutcome.TIMEOUT)),
        rules=RULES[1:3],
        threshold=len(SQL) - 1,
    )
    message = "LLM sunucusu yanıt vermedi (zaman aşımı)."
    both = f"Parça 1/2: {message}; Parça 2/2: {message}"
    assert [check.status for check in review.checks] == [RuleResultStatus.UNKNOWN] * 2
    assert review.checks[0].description == both
    assert review.warning == f"[Kural01, Kural02] {both}"


async def test_an_unreadable_reply_is_unknown_with_the_parser_warning() -> None:
    review = await _review(ScriptedLlm(responder=lambda request: ok("yanıt yok")), rules=RULES[1:2])
    assert review.checks[0].status is RuleResultStatus.UNKNOWN
    assert review.checks[0].description == "Model yanıtı JSON olarak çözülemedi."


async def test_the_truncation_note_leads_the_object_warning() -> None:
    note = "Metnin yalnız ilk 120.000 karakteri incelendi."
    review = await _review(ScriptedLlm(), note=note)
    assert review.warning == note


async def test_rule_events_carry_counters_only() -> None:
    llm = ScriptedLlm(progress_steps=2)
    events = Events()
    await _review(llm, rules=RULES[1:2], events=events)
    assert [type(event) for event in events.items] == [
        RulesBatchStarted,
        RuleStarted,
        RuleStreamed,
        RuleStreamed,
        RuleFinished,
    ]
    streamed = [event for event in events.items if isinstance(event, RuleStreamed)]
    assert [(e.completion_tokens, e.total_chars) for e in streamed] == [(1, 10), (2, 20)]
    finished = events.items[-1]
    assert isinstance(finished, RuleFinished)
    assert finished.ok and finished.rule_index == 1 and finished.rules_total == 1
    assert finished.completion_tokens == 3


async def test_two_part_stream_counters_keep_growing_across_parts() -> None:
    llm = ScriptedLlm(progress_steps=1)
    events = Events()
    await _review(llm, rules=RULES[1:2], threshold=len(SQL) - 1, events=events)
    streamed = [event for event in events.items if isinstance(event, RuleStreamed)]
    assert [(e.completion_tokens, e.total_chars) for e in streamed] == [(1, 10), (4, 28)]
    finished = events.items[-1]
    assert isinstance(finished, RuleFinished)
    assert finished.two_part and finished.completion_tokens == 6


async def test_texts_of_one_run_share_the_run_limit() -> None:
    gate = asyncio.Event()
    llm = ScriptedLlm(run_limit=2, gate=gate)
    reviewer = TextReviewer(two_part_threshold_chars=45_000)
    async with llm.open_run() as session:
        tasks = [
            asyncio.create_task(
                reviewer.review(
                    session,
                    sql=SQL,
                    rules=RULES,
                    metadata=MetadataContext(MetadataSource.FETCHED),
                    scope=SCOPE,
                    emit=Events(),
                )
            )
            for _ in range(3)
        ]
        await asyncio.sleep(0.05)
        assert llm.active == 2
        gate.set()
        await asyncio.gather(*tasks)
    assert llm.peak == 2
    assert len(llm.calls) == 9


# --- The real adapter: the limits hold at the network boundary ---------------------------------


async def _private(host: str, port: int) -> list[str]:
    assert host == HOST_NAME
    return ["127.0.0.1"]


class _Recorder:
    def __init__(self) -> None:
        self.attempts: list[Any] = []

    async def record(self, attempt: Any) -> None:
        self.attempts.append(attempt)


def _adapter(server: FakeLlmServer, recorder: _Recorder, *, run: int, process: int) -> HttpLlmChat:
    endpoint = LlmEndpoint(LlmChatApi.API_V1_CHAT, server.url("/api/v1/chat"), "test-model")
    return HttpLlmChat(
        endpoint=lambda: endpoint,
        recorder=recorder,
        ca_bundle=str(server.pki.ca_path),
        read_timeout_seconds=5.0,
        request_retries=0,
        run_max_concurrent_calls=run,
        process_max_concurrent_calls=process,
        user_agent="test",
        resolver=_private,
    )


async def _slow_reply(request: RecordedRequest, writer: Writer) -> None:
    await asyncio.sleep(0.05)
    body = json.dumps({"output": [{"type": "message", "content": '{"violations": []}'}]})
    writer.write(http_response(200, body.encode("utf-8")))
    await writer.drain()


@pytest.fixture
async def llm_server(tmp_path: Path) -> Any:
    server = await FakeLlmServer(write_pki(tmp_path / "pki"), scenario=_slow_reply).start()
    try:
        yield server
    finally:
        await server.close()


async def _object_run(chat: HttpLlmChat, objects: int, threshold: int = 45_000) -> list[Any]:
    reviewer = TextReviewer(two_part_threshold_chars=threshold)
    async with chat.open_run() as session:
        return await asyncio.gather(
            *[
                reviewer.review(
                    session,
                    sql=SQL,
                    rules=RULES + (ReviewRule("Kural04", NORMAL, "dört"),),
                    metadata=MetadataContext(MetadataSource.FETCHED),
                    scope=SCOPE,
                    emit=Events(),
                )
                for _ in range(objects)
            ]
        )


async def test_the_run_limit_holds_across_objects_at_the_endpoint(
    llm_server: FakeLlmServer,
) -> None:
    recorder = _Recorder()
    reviews = await _object_run(_adapter(llm_server, recorder, run=3, process=12), objects=3)

    assert len(llm_server.requests) == 12
    assert llm_server.peak == 3
    assert all(check.status is RuleResultStatus.PASS for r in reviews for check in r.checks)
    assert {attempt.target.review_run_id for attempt in recorder.attempts} == {41}
    for request in llm_server.requests:
        assert MARKER in request.json()["input"]


async def test_two_part_calls_are_recorded_with_their_part(llm_server: FakeLlmServer) -> None:
    recorder = _Recorder()
    await _object_run(
        _adapter(llm_server, recorder, run=2, process=12), objects=1, threshold=len(SQL) - 1
    )
    assert len(llm_server.requests) == 8
    assert llm_server.peak <= 2
    assert sorted(attempt.target.part_index for attempt in recorder.attempts) == [1] * 4 + [2] * 4


async def test_the_process_limit_holds_across_runs_at_the_endpoint(
    llm_server: FakeLlmServer,
) -> None:
    chat = _adapter(llm_server, _Recorder(), run=3, process=4)
    await asyncio.gather(_object_run(chat, objects=2), _object_run(chat, objects=2))
    assert len(llm_server.requests) == 16
    assert llm_server.peak == 4
