"""Signature-constrained stand-ins for the LLM chat port and the SQL Server catalog port.

``ScriptedLlm`` implements ``LlmChatPort`` exactly (run -> slot -> chat) with the run-wide and
process-wide slot limits of the real adapter, records every request with its target, and answers
through a responder the test installs. ``FakeCatalog`` implements ``SqlCatalogPort`` with the
system database check, typed failures and recorded calls.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.domain.llm import (
    LlmCallTarget,
    LlmChatPort,
    LlmChatRequest,
    LlmChatResult,
    LlmNotConfigured,
    LlmStreamProgress,
    LlmUsage,
    ProgressCallback,
)
from app.domain.models.llm_call import LlmCallOutcome
from app.domain.sql_server import (
    CatalogObject,
    DatabaseNotAllowed,
    SqlCatalogPort,
    is_system_database,
)

Responder = Callable[[LlmChatRequest], Awaitable[LlmChatResult] | LlmChatResult]
_RULE_CODE = re.compile(
    r"KURAL KODU \(bu istekte tek kural; rule_code alanında aynen kullan\):\n(\S+)"
)


def rule_code_of(request: LlmChatRequest) -> str:
    match = _RULE_CODE.search(request.user_content)
    assert match is not None, "the user prompt always names its single rule"
    return match.group(1)


def ok(text: str, completion_tokens: int | None = 3) -> LlmChatResult:
    return LlmChatResult(
        LlmCallOutcome.OK,
        text=text,
        http_status=200,
        usage=LlmUsage(completion_tokens, 11, len(text)),
    )


def failed(outcome: LlmCallOutcome, http_status: int | None = None) -> LlmChatResult:
    return LlmChatResult(outcome, http_status=http_status, usage=LlmUsage(None, None, 0))


def no_violations(_request: LlmChatRequest) -> LlmChatResult:
    return ok('{"violations": []}')


@dataclass
class CallRecord:
    target: LlmCallTarget
    request: LlmChatRequest
    cancelled: bool = False


@dataclass
class ScriptedLlm:
    responder: Responder = no_violations
    run_limit: int = 6
    process_limit: int = 12
    configured: bool = True
    progress_steps: int = 0
    calls: list[CallRecord] = field(default_factory=list)
    runs_opened: int = 0
    active: int = 0
    peak: int = 0
    gate: asyncio.Event | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    _process_slots: asyncio.Semaphore | None = None

    def _process(self) -> asyncio.Semaphore:
        if self._process_slots is None:
            self._process_slots = asyncio.Semaphore(self.process_limit)
        return self._process_slots

    @asynccontextmanager
    async def open_run(self) -> AsyncIterator["_Run"]:
        self.runs_opened += 1
        yield _Run(self, asyncio.Semaphore(self.run_limit))

    async def _chat(
        self, request: LlmChatRequest, progress: ProgressCallback | None
    ) -> LlmChatResult:
        if not self.configured:
            raise LlmNotConfigured()
        record = CallRecord(request.target, request)
        self.calls.append(record)
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.started.set()
        try:
            if self.gate is not None:
                await self.gate.wait()
            else:
                await asyncio.sleep(0)
            for step in range(1, self.progress_steps + 1):
                if progress is not None:
                    await progress(LlmStreamProgress(request.target.rule_code, step, step * 10))
            answer = self.responder(request)
            if not isinstance(answer, LlmChatResult):
                answer = await answer
            return answer
        except asyncio.CancelledError:
            record.cancelled = True
            raise
        finally:
            self.active -= 1


class _Run:
    def __init__(self, llm: ScriptedLlm, slots: asyncio.Semaphore) -> None:
        self._llm = llm
        self._slots = slots

    @asynccontextmanager
    async def slot(self) -> AsyncIterator["_Slot"]:
        async with self._slots, self._llm._process():
            yield _Slot(self._llm)


class _Slot:
    def __init__(self, llm: ScriptedLlm) -> None:
        self._llm = llm

    async def chat(
        self, request: LlmChatRequest, *, progress: ProgressCallback | None = None
    ) -> LlmChatResult:
        return await self._llm._chat(request, progress)


@dataclass
class FakeCatalog:
    """Definitions keyed by (database, schema, name); raises what the test puts in ``errors``."""

    definitions: dict[tuple[str, str, str], str | None] = field(default_factory=dict)
    metadata: dict[tuple[str, str, str], str] = field(default_factory=dict)
    errors: dict[tuple[str, str, str], Exception] = field(default_factory=dict)
    metadata_errors: dict[tuple[str, str, str], Exception] = field(default_factory=dict)
    databases: list[str] = field(default_factory=list)
    objects: dict[str, list[CatalogObject]] = field(default_factory=dict)
    failure: Exception | None = None
    calls: list[tuple[str, ...]] = field(default_factory=list)
    # Definition and metadata calls running at the same moment, and the highest value seen.
    active: int = 0
    peak: int = 0

    def is_allowed(self, database: str) -> bool:
        return not is_system_database(database)

    async def list_databases(self) -> list[str]:
        self.calls.append(("list_databases",))
        if self.failure is not None:
            raise self.failure
        return [name for name in self.databases if self.is_allowed(name)]

    async def list_objects(
        self, database: str, *, query: str | None = None, from_date: date | None = None
    ) -> list[CatalogObject]:
        self.calls.append(("list_objects", database, query or "", str(from_date or "")))
        if not self.is_allowed(database):
            raise DatabaseNotAllowed()
        if self.failure is not None:
            raise self.failure
        needle = (query or "").strip().lower()
        cutoff = datetime.combine(from_date, datetime.min.time()) if from_date else None
        return [
            row
            for row in self.objects.get(database, [])
            if (not needle or needle in f"{row.schema} {row.name} {row.type}".lower())
            and (
                cutoff is None
                or (row.created_at is not None and row.created_at >= cutoff)
                or (row.last_modified is not None and row.last_modified >= cutoff)
            )
        ]

    async def fetch_definition(
        self, database: str, schema: str, name: str, type_code: str
    ) -> str | None:
        self.calls.append(("fetch_definition", database, schema, name, type_code))
        if not self.is_allowed(database):
            raise DatabaseNotAllowed()
        key = (database, schema, name)
        async with self._in_flight():
            if key in self.errors:
                raise self.errors[key]
            return self.definitions.get(key)

    async def fetch_object_metadata(self, database: str, schema: str, name: str) -> str:
        self.calls.append(("fetch_object_metadata", database, schema, name))
        key = (database, schema, name)
        async with self._in_flight():
            if key in self.metadata_errors:
                raise self.metadata_errors[key]
            return self.metadata.get(key, "")

    @asynccontextmanager
    async def _in_flight(self) -> AsyncIterator[None]:
        """A catalog call takes a turn of the event loop, like the real adapter's thread hop."""

        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0)
            yield
        finally:
            self.active -= 1


if TYPE_CHECKING:

    def _implements_llm(llm: ScriptedLlm) -> LlmChatPort:
        return llm

    def _implements_catalog(catalog: FakeCatalog) -> SqlCatalogPort:
        return catalog
