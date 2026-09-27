"""LLM call summaries in PostgreSQL: recording, the rule manager's API, leaks and retention.

sql-review/PRDs/006-llm-connection Requirement 10, 11, 12 and 14 (Acceptance 2).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.db.session import async_session_factory, engine
from app.domain.llm import LlmCallAttempt, LlmCallTarget, LlmChatRequest, LlmEndpoint
from app.domain.models.llm_call import LlmCallOutcome, LlmChatApi
from app.domain.models.mixins import new_public_id
from app.infrastructure.llm.http_chat import HttpLlmChat
from app.infrastructure.repositories.llm_call_summary_repository import (
    RETENTION_LOCK_KEY,
)
from app.services.llm_call_summary_service import (
    LlmCallSummaryRecorder,
    purge_expired_llm_call_summaries,
)
from tests.fakes.llm_server import (
    HOST_NAME,
    FakeLlmServer,
    RecordedRequest,
    Writer,
    http_response,
    write_pki,
)
from tests.integration.conftest import AuthHarness, RoleSessions, SuperAdmin

pytestmark = pytest.mark.integration

MARKER = f"SIZINTI-{uuid4().hex}"
SUMMARY_FIELDS = {
    "public_id",
    "started_at",
    "review_run_id",
    "object_label",
    "rule_id",
    "part_index",
    "attempt",
    "chat_api",
    "model",
    "endpoint_host",
    "streamed",
    "outcome",
    "http_status",
    "duration_ms",
    "completion_tokens",
    "prompt_tokens",
    "response_chars",
}


async def _platform_tenant_id() -> int:
    async with async_session_factory() as session:
        value = await session.scalar(text("SELECT tenant_id FROM tenant WHERE code = 'platform'"))
    return int(value)


@pytest.fixture
def llm_logs() -> Iterator[list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Handler(level=logging.DEBUG)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


@pytest.fixture
async def fake_llm(tmp_path: Path) -> AsyncIterator[FakeLlmServer]:
    server = await FakeLlmServer(write_pki(tmp_path / "pki")).start()
    try:
        yield server
    finally:
        await server.close()


async def _review_run(tenant_id: int, owner_public_id: str) -> tuple[int, str]:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text(
                    "INSERT INTO review_run (public_id, tenant_id, owner_user_id, kind, "
                    "rule_set_version_id, object_count, status, started_at) "
                    "SELECT gen_random_uuid()::text, :tenant, u.user_id, 'object', "
                    "(SELECT rule_set_version_id FROM rule_set_version WHERE tenant_id = :tenant "
                    " ORDER BY number DESC LIMIT 1), 1, 'running', now() "
                    "FROM app_user u WHERE u.public_id = :owner "
                    "RETURNING review_run_id, public_id"
                ),
                {"tenant": tenant_id, "owner": owner_public_id},
            )
        ).one()
        await session.commit()
    return int(row[0]), str(row[1])


async def test_real_calls_leave_only_metadata_in_database_logs_and_api(
    auth: AuthHarness,
    role_sessions: RoleSessions,
    fake_llm: FakeLlmServer,
    llm_logs: list[logging.LogRecord],
) -> None:
    manager = await role_sessions.rule_manager()
    tenant_id = await _platform_tenant_id()
    run_id, run_public_id = await _review_run(tenant_id, manager.public_id)

    async def scenario(request: RecordedRequest, writer: Writer) -> None:
        if len(fake_llm.requests) == 1:
            body = {
                "choices": [{"message": {"content": f"sonuç {MARKER}"}}],
                "usage": {"completion_tokens": 9, "prompt_tokens": 40},
            }
            writer.write(http_response(200, json.dumps(body).encode()))
        else:
            writer.write(http_response(500, f"hata gövdesi {MARKER}".encode()))
        await writer.drain()

    fake_llm.scenario = scenario

    async def resolver(host: str, port: int) -> list[str]:
        return ["127.0.0.1"]

    endpoint = LlmEndpoint(LlmChatApi.OPENAI, fake_llm.url("/v1/chat/completions"), "model-x")
    chat = HttpLlmChat(
        endpoint=lambda: endpoint,
        recorder=LlmCallSummaryRecorder(async_session_factory),
        ca_bundle=str(fake_llm.pki.ca_path),
        read_timeout_seconds=5,
        request_retries=2,
        run_max_concurrent_calls=2,
        process_max_concurrent_calls=2,
        user_agent="DWHCodeReview-Backend/1.0 (internal SQL review; httpx)",
        resolver=resolver,
    )
    results = []
    async with chat.open_run() as run:
        for part in (1, 2):
            target = LlmCallTarget(
                tenant_id=tenant_id,
                object_label="[DWH] dbo.usp_Load (PROCEDURE)",
                rule_code="Kural05",
                review_run_id=run_id,
                review_run_public_id=run_public_id,
                part_index=part,
            )
            async with run.slot() as slot:
                results.append(
                    await slot.chat(LlmChatRequest(target, f"istem {MARKER}", f"SELECT '{MARKER}'"))
                )

    assert results[0].ok and MARKER in (results[0].text or "")
    assert results[1].outcome is LlmCallOutcome.UPSTREAM_STATUS
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        "SELECT row_to_json(s)::text FROM llm_call_summary s "
                        "WHERE review_run_id = :run ORDER BY part_index"
                    ),
                    {"run": run_id},
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 2 and all(MARKER not in row for row in rows)

    listed = await auth.client.get(
        f"{auth.prefix}/llm-calls", params={"limit": 500}, headers=manager.headers
    )
    assert listed.status_code == 200, listed.text
    ours = [item for item in listed.json()["items"] if item["review_run_id"] == run_public_id]
    assert [item["part_index"] for item in ours] == [2, 1]
    first = next(item for item in ours if item["part_index"] == 1)
    assert set(first) == SUMMARY_FIELDS
    assert first["outcome"] == "ok" and first["http_status"] == 200
    assert (first["completion_tokens"], first["prompt_tokens"]) == (9, 40)
    assert first["endpoint_host"] == HOST_NAME and first["model"] == "model-x"
    assert first["rule_id"] == "Kural05" and first["attempt"] == 1
    single = await auth.client.get(
        f"{auth.prefix}/llm-calls/{first['public_id']}", headers=manager.headers
    )
    assert single.json() == first
    assert MARKER not in listed.text and MARKER not in single.text

    events = [r for r in llm_logs if r.getMessage() == "llm.call"]
    assert len(events) == 2
    for event in events:
        fields = dict(event.structured_fields)  # type: ignore[attr-defined]
        assert set(fields) == SUMMARY_FIELDS | {"event"}
    for record in llm_logs:
        rendered = record.getMessage() + repr(getattr(record, "structured_fields", {}))
        assert MARKER not in rendered + repr(record.args)


async def test_the_list_is_newest_first_limited_and_validated(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    tenant_id = await _platform_tenant_id()
    recorder = LlmCallSummaryRecorder(async_session_factory)
    now = datetime.now(UTC) + timedelta(days=1)
    for offset in range(3):
        await recorder.record(
            _attempt(tenant_id, now - timedelta(minutes=offset), f"Kural{90 + offset}")
        )

    newest = await auth.client.get(
        f"{auth.prefix}/llm-calls", params={"limit": 2}, headers=manager.headers
    )
    default = await auth.client.get(f"{auth.prefix}/llm-calls", headers=manager.headers)

    assert [item["rule_id"] for item in newest.json()["items"]] == ["Kural90", "Kural91"]
    assert newest.json()["limit"] == 2 and newest.json()["total"] >= 3
    assert default.json()["limit"] == 100
    for limit in (0, 501, "x"):
        invalid = await auth.client.get(
            f"{auth.prefix}/llm-calls", params={"limit": limit}, headers=manager.headers
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "invalid_request"
    for missing in (str(uuid4()), "not-a-uuid"):
        response = await auth.client.get(
            f"{auth.prefix}/llm-calls/{missing}", headers=manager.headers
        )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "llm_call_not_found"


async def test_other_tenants_see_none_of_the_summaries(
    auth: AuthHarness, super_admin: SuperAdmin
) -> None:
    tenant_id = await _platform_tenant_id()
    attempt = _attempt(tenant_id, datetime.now(UTC), "Kural77")
    await LlmCallSummaryRecorder(async_session_factory).record(attempt)
    async with async_session_factory() as session:
        other = await session.scalar(
            text(
                "INSERT INTO tenant (public_id, code, name) VALUES "
                "(gen_random_uuid()::text, :code, 'Başka') RETURNING public_id"
            ),
            {"code": f"t-{uuid4().hex[:10]}"},
        )
        await session.commit()
    login = await auth.login(super_admin.username, super_admin.password)
    headers = auth.auth_headers(login.json())
    headers[auth.settings.tenant_header] = str(other)

    listed = await auth.client.get(f"{auth.prefix}/llm-calls", headers=headers)
    single = await auth.client.get(f"{auth.prefix}/llm-calls/{attempt.public_id}", headers=headers)

    assert listed.json()["items"] == [] and listed.json()["total"] == 0
    assert single.status_code == 404


def _attempt(tenant_id: int, started_at: datetime, rule_code: str) -> LlmCallAttempt:
    return LlmCallAttempt(
        public_id=new_public_id(),
        target=LlmCallTarget(
            tenant_id=tenant_id, object_label="deneme (SCRIPT)", rule_code=rule_code
        ),
        started_at=started_at,
        attempt=1,
        chat_api=LlmChatApi.API_V1_CHAT,
        model="m",
        endpoint_host="llm.corp.example.test",
        streamed=False,
        outcome=LlmCallOutcome.TIMEOUT,
        http_status=None,
        duration_ms=10,
        completion_tokens=None,
        prompt_tokens=None,
        response_chars=None,
    )


async def _exists(public_id: str) -> bool:
    async with async_session_factory() as session:
        return bool(
            await session.scalar(
                text("SELECT count(*) FROM llm_call_summary WHERE public_id = :p"),
                {"p": public_id},
            )
        )


async def test_retention_deletes_only_summaries_older_than_90_days(
    migrated_database: None, llm_logs: list[logging.LogRecord]
) -> None:
    tenant_id = await _platform_tenant_id()
    now = datetime.now(UTC)
    old = _attempt(tenant_id, now - timedelta(days=90, minutes=1), "Kural80")
    recent = _attempt(tenant_id, now - timedelta(days=89, hours=23), "Kural81")
    recorder = LlmCallSummaryRecorder(async_session_factory)
    await recorder.record(old)
    await recorder.record(recent)

    run = await purge_expired_llm_call_summaries(async_session_factory, now=now)

    assert run.outcome == "ok" and run.deleted >= 1
    assert not await _exists(old.public_id) and await _exists(recent.public_id)
    (event,) = [r for r in llm_logs if r.getMessage() == "llm_call_summary.retention_run"]
    fields: dict[str, Any] = event.structured_fields  # type: ignore[attr-defined]
    assert fields["outcome"] == "ok" and fields["deleted"] == run.deleted
    assert isinstance(fields["duration_ms"], int)


async def test_only_one_copy_deletes_at_a_time(migrated_database: None) -> None:
    tenant_id = await _platform_tenant_id()
    now = datetime.now(UTC)
    expired = _attempt(tenant_id, now - timedelta(days=120), "Kural82")
    await LlmCallSummaryRecorder(async_session_factory).record(expired)

    async with engine.connect() as holder:
        transaction = await holder.begin()
        await holder.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": RETENTION_LOCK_KEY})
        blocked = await purge_expired_llm_call_summaries(async_session_factory, now=now)
        await transaction.rollback()

    assert (blocked.outcome, blocked.deleted) == ("skipped", 0)
    assert await _exists(expired.public_id)

    runs = await asyncio.gather(
        purge_expired_llm_call_summaries(async_session_factory, now=now),
        purge_expired_llm_call_summaries(async_session_factory, now=now),
    )
    assert sum(run.deleted for run in runs) >= 1
    assert {run.outcome for run in runs} <= {"ok", "skipped"}
    assert not await _exists(expired.public_id)
