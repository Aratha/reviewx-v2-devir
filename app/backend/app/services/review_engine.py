"""Review of one SQL text against the pinned rules (sql-review 003 Requirement 7-12 and 17).

Ported from the previous application's ``review_sql``: one LLM call per rule, critical rules
first; above the two-part threshold each rule is asked twice, once per half, inside the same
concurrency slot, and the replies are merged. Unlike the source, concurrency is not per object:
every call takes a slot of the run's ``LlmRunSession`` (Decision 4), so the run-wide and
process-wide limits of 006-llm-connection hold across all objects. LLM failures reach the
reviewer only as the fixed Turkish class messages of that capability.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace

from app.domain.llm import (
    LlmCallSlot,
    LlmCallTarget,
    LlmChatRequest,
    LlmChatResult,
    LlmRunSession,
    LlmStreamProgress,
)
from app.domain.review import (
    FINDING_TEXT_MAX_LENGTH,
    LINE_REFERENCE_MAX_LENGTH,
    RULE_RESULT_TEXT_MAX_LENGTH,
    Finding,
    MetadataContext,
    ReviewRule,
    RuleCheck,
    RulePriorityGroup,
    RuleResultStatus,
    TextReview,
)
from app.services.review_prompts import (
    SYSTEM_PROMPT,
    numbered_sql,
    split_into_two_parts,
    two_part_scope_notices,
    user_prompt,
)
from app.services.review_response_parser import (
    RuleRef,
    merge_two_part_rule,
    parse_review_response,
)

_NO_REPLY = "LLM yanıtı alınamadı."
_EMPTY_PARSE = "Çözümleme sonucu boş."
# Warnings of the oldest reply format are folded into rule results and never shown.
_LEGACY_MARKERS = ("PASS/FAIL", "Eski çıktı biçimi", "Eski", "çıktı biçimi")


@dataclass(frozen=True, slots=True)
class RulesBatchStarted:
    rules_total: int


@dataclass(frozen=True, slots=True)
class RuleStarted:
    rule_code: str
    tier: RulePriorityGroup
    rule_index: int
    rules_total: int
    two_part: bool


@dataclass(frozen=True, slots=True)
class RuleStreamed:
    rule_code: str
    completion_tokens: int | None
    total_chars: int


@dataclass(frozen=True, slots=True)
class RuleFinished:
    rule_code: str
    tier: RulePriorityGroup
    rule_index: int
    rules_total: int
    ok: bool
    two_part: bool
    completion_tokens: int | None
    total_chars: int | None


RuleEvent = RulesBatchStarted | RuleStarted | RuleStreamed | RuleFinished
RuleEventSink = Callable[[RuleEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ReviewScope:
    """What the calls of one text belong to; recorded in the content-free call summaries."""

    tenant_id: int
    object_label: str
    review_run_id: int
    review_run_public_id: str


@dataclass(frozen=True, slots=True)
class _RuleOutcome:
    check: RuleCheck
    findings: list[Finding]
    warning: str | None = field(default=None, repr=False)
    # The rule's LLM call(s) failed; equal failures of several rules share one warning line.
    llm_failure: bool = False


def _sum(first: int | None, second: int | None) -> int | None:
    if first is None:
        return second
    if second is None:
        return first
    return first + second


def _unknown(rule: ReviewRule, description: str) -> RuleCheck:
    return RuleCheck(rule.code, rule.tier, RuleResultStatus.UNKNOWN, description=description)


def _bounded_check(check: RuleCheck) -> RuleCheck:
    return replace(
        check,
        description=check.description[:RULE_RESULT_TEXT_MAX_LENGTH],
        line_reference=check.line_reference[:LINE_REFERENCE_MAX_LENGTH],
        code_snippet=check.code_snippet[:RULE_RESULT_TEXT_MAX_LENGTH],
    )


def _bounded_finding(finding: Finding) -> Finding:
    return replace(
        finding,
        description=finding.description[:FINDING_TEXT_MAX_LENGTH],
        line_reference=finding.line_reference[:LINE_REFERENCE_MAX_LENGTH],
        code_snippet=finding.code_snippet[:FINDING_TEXT_MAX_LENGTH],
    )


def merge_object_warnings(
    rules: Sequence[ReviewRule], outcomes: Sequence[_RuleOutcome], leading_note: str | None
) -> str | None:
    """Requirement 12: "[KuralNN] warning" lines; equal LLM failures share one line."""

    grouped: dict[str, list[str]] = {}
    others: list[str] = []
    for rule, outcome in zip(rules, outcomes, strict=True):
        warning = outcome.warning
        if not warning or any(marker in warning for marker in _LEGACY_MARKERS):
            continue
        if outcome.llm_failure:
            grouped.setdefault(warning, []).append(rule.code)
        else:
            others.append(f"[{rule.code}] {warning}")
    parts = [f"[{', '.join(codes)}] {warning}" for warning, codes in grouped.items()]
    parts.extend(others)
    merged = "; ".join(parts) if parts else None
    if merged and ("PASS/FAIL" in merged or "çıktı biçimi" in merged):
        merged = None
    lines = [line for line in (leading_note, merged) if line]
    return "; ".join(lines) if lines else None


class TextReviewer:
    """Reviews one text; the caller owns truncation, metadata and object-level events."""

    def __init__(self, *, two_part_threshold_chars: int) -> None:
        self._threshold = two_part_threshold_chars

    @property
    def threshold(self) -> int:
        """Texts longer than this many characters are reviewed in two parts."""

        return self._threshold

    async def review(
        self,
        session: LlmRunSession,
        *,
        sql: str,
        rules: Sequence[ReviewRule],
        metadata: MetadataContext,
        scope: ReviewScope,
        emit: RuleEventSink,
        leading_note: str | None = None,
    ) -> TextReview:
        if not rules:
            return TextReview((), (), leading_note)
        await emit(RulesBatchStarted(len(rules)))
        numbered = numbered_sql(sql)
        first_part, second_part, second_start = split_into_two_parts(sql)
        two_part = len(sql) > self._threshold and bool(second_part.strip())
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    self._rule(
                        session,
                        rule=rule,
                        index=index,
                        rules_total=len(rules),
                        sql=sql,
                        numbered=numbered,
                        parts=(first_part, second_part, second_start) if two_part else None,
                        metadata=metadata,
                        scope=scope,
                        emit=emit,
                    )
                )
                for index, rule in enumerate(rules, start=1)
            ]
        outcomes = [task.result() for task in tasks]
        return TextReview(
            checks=tuple(_bounded_check(outcome.check) for outcome in outcomes),
            findings=tuple(
                _bounded_finding(finding) for outcome in outcomes for finding in outcome.findings
            ),
            warning=merge_object_warnings(rules, outcomes, leading_note),
        )

    async def _rule(
        self,
        session: LlmRunSession,
        *,
        rule: ReviewRule,
        index: int,
        rules_total: int,
        sql: str,
        numbered: str,
        parts: tuple[str, str, int] | None,
        metadata: MetadataContext,
        scope: ReviewScope,
        emit: RuleEventSink,
    ) -> _RuleOutcome:
        async with session.slot() as slot:
            await emit(RuleStarted(rule.code, rule.tier, index, rules_total, parts is not None))
            if parts is None:
                return await self._single(
                    slot, rule, index, rules_total, sql, numbered, metadata, scope, emit
                )
            return await self._two_part(
                slot, rule, index, rules_total, sql, parts, metadata, scope, emit
            )

    async def _call(
        self,
        slot: LlmCallSlot,
        rule: ReviewRule,
        content: str,
        scope: ReviewScope,
        emit: RuleEventSink,
        *,
        part_index: int | None = None,
        offset: tuple[int | None, int] = (None, 0),
    ) -> LlmChatResult:
        target = LlmCallTarget(
            tenant_id=scope.tenant_id,
            object_label=scope.object_label,
            rule_code=rule.code,
            review_run_id=scope.review_run_id,
            review_run_public_id=scope.review_run_public_id,
            part_index=part_index,
        )

        async def progress(update: LlmStreamProgress) -> None:
            await emit(
                RuleStreamed(
                    rule.code,
                    _sum(offset[0], update.completion_tokens),
                    offset[1] + update.total_chars,
                )
            )

        return await slot.chat(LlmChatRequest(target, SYSTEM_PROMPT, content), progress=progress)

    async def _single(
        self,
        slot: LlmCallSlot,
        rule: ReviewRule,
        index: int,
        rules_total: int,
        sql: str,
        numbered: str,
        metadata: MetadataContext,
        scope: ReviewScope,
        emit: RuleEventSink,
    ) -> _RuleOutcome:
        content = user_prompt(rule, numbered=numbered, metadata=metadata)
        result = await self._call(slot, rule, content, scope, emit)
        reply = result.text if result.ok else None
        usage = result.usage
        await emit(
            RuleFinished(
                rule.code,
                rule.tier,
                index,
                rules_total,
                ok=bool(reply and reply.strip()),
                two_part=False,
                completion_tokens=None if usage is None else usage.completion_tokens,
                total_chars=None if usage is None else usage.total_chars,
            )
        )
        if not reply:
            error = result.failure_message or _NO_REPLY
            return _RuleOutcome(_unknown(rule, error), [], error, llm_failure=True)
        parsed = parse_review_response(reply, (RuleRef(rule.code, rule.tier),), sql)
        if not parsed.checks:
            return _RuleOutcome(_unknown(rule, parsed.warning or _EMPTY_PARSE), [], parsed.warning)
        return _RuleOutcome(parsed.checks[0], parsed.findings, parsed.warning)

    async def _two_part(
        self,
        slot: LlmCallSlot,
        rule: ReviewRule,
        index: int,
        rules_total: int,
        sql: str,
        parts: tuple[str, str, int],
        metadata: MetadataContext,
        scope: ReviewScope,
        emit: RuleEventSink,
    ) -> _RuleOutcome:
        first_part, second_part, second_start = parts
        first_notice, second_notice = two_part_scope_notices(sql, second_start)
        first = await self._call(
            slot,
            rule,
            user_prompt(
                rule,
                numbered=numbered_sql(first_part, 1),
                metadata=metadata,
                scope_notice=first_notice,
            ),
            scope,
            emit,
            part_index=1,
        )
        first_tokens = None if first.usage is None else first.usage.completion_tokens
        first_chars = 0 if first.usage is None else first.usage.total_chars
        second = await self._call(
            slot,
            rule,
            user_prompt(
                rule,
                numbered=numbered_sql(second_part, second_start),
                metadata=metadata,
                scope_notice=second_notice,
            ),
            scope,
            emit,
            part_index=2,
            offset=(first_tokens, first_chars),
        )
        error_a = None if first.ok else (first.failure_message or _NO_REPLY)
        error_b = None if second.ok else (second.failure_message or _NO_REPLY)
        raw_a = first.text if first.ok else None
        raw_b = second.text if second.ok else None
        await emit(
            RuleFinished(
                rule.code,
                rule.tier,
                index,
                rules_total,
                ok=error_a is None
                and error_b is None
                and bool((raw_a or "").strip() or (raw_b or "").strip()),
                two_part=True,
                completion_tokens=_sum(
                    first_tokens, None if second.usage is None else second.usage.completion_tokens
                ),
                total_chars=_sum(
                    None if first.usage is None else first.usage.total_chars,
                    None if second.usage is None else second.usage.total_chars,
                ),
            )
        )
        check, findings, warning = merge_two_part_rule(
            RuleRef(rule.code, rule.tier),
            error_a=error_a,
            raw_a=raw_a,
            error_b=error_b,
            raw_b=raw_b,
            source_sql=sql,
        )
        if check.status is RuleResultStatus.UNKNOWN and (error_a or error_b):
            reason = warning or error_a or error_b or _NO_REPLY
            return _RuleOutcome(
                _unknown(rule, (check.description or reason)[:2000]),
                [],
                reason,
                llm_failure=bool(error_a and error_b),
            )
        return _RuleOutcome(check, findings, warning)
