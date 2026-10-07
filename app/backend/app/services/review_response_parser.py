"""Model reply parsing, merging and line-reference inference (sql-review 003 Requirement 10-12).

Ported from the previous application's ``services/llm_review.py`` (``_loads_llm_json_first``,
``parse_review_response``, ``_merge_violations_format``, ``_merge_rule_results``,
``_merge_two_part_single_rule``, ``_line_ref_from_violation_item`` and their helpers) with the
same decisions. Two deliberate differences: the findings of the legacy root-array reply carry the
reviewed rule's code (the store accepts only KuralNN codes), and statuses and severities are
domain enums. Nothing here touches the network, a database or a file (Requirement 20).
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.review import (
    FINDING_TEXT_MAX_LENGTH,
    RULE_RESULT_TEXT_MAX_LENGTH,
    Finding,
    RuleCheck,
    RulePriorityGroup,
    RuleResultStatus,
    Severity,
    severity_for_tier,
)

_NO_VIOLATION = "İhlal bulunmadı."
_DECISION_BASES = ("direct_evidence", "absence_of_evidence", "not_applicable")
_VALID_SEVERITIES = ("LOW", "MEDIUM", "HIGH")
_VALID_VERDICTS = ("PASS", "FAIL", "NOT_APPLICABLE")
_RULE_RESULT_KEYS = (
    "rule_results",
    "rule_checks",
    "results",
    "rules",
    "checks",
    "ruleResults",
    "review_results",
    "RuleResults",
)
_NESTED_KEYS = ("data", "response", "output", "result", "payload", "message")


@dataclass(frozen=True, slots=True)
class RuleRef:
    """A rule the reply is matched against: its code and priority group, in request order."""

    code: str
    tier: RulePriorityGroup


@dataclass(frozen=True, slots=True)
class ParsedReply:
    checks: list[RuleCheck]
    findings: list[Finding]
    warning: str | None


def loads_first_json(text: str) -> Any:
    """The first JSON value in the text; prose before or after it is ignored.

    Every ``{`` and ``[`` is tried as a start, because models sometimes put invalid example
    fragments before the real reply.
    """

    candidate = text.strip()
    if not candidate:
        raise json.JSONDecodeError("Expecting value", candidate, 0)
    if candidate.startswith("﻿"):
        candidate = candidate.lstrip("﻿").strip()
    decoder = json.JSONDecoder()
    starts = [index for index, char in enumerate(candidate) if char in "{["]
    if not starts:
        raise json.JSONDecodeError("Expecting value", candidate, 0)
    last_error: json.JSONDecodeError | None = None
    for start in starts:
        try:
            return decoder.raw_decode(candidate, start)[0]
        except json.JSONDecodeError as error:
            last_error = error
    assert last_error is not None
    raise last_error


def _try_loads_first_json(text: str) -> object | None:
    try:
        value: object = loads_first_json(text)
    except json.JSONDecodeError:
        return None
    return value


def _coerce_violations_list_value(value: object) -> list[Any] | None:
    """``violations`` may be a list or the text of a JSON array."""

    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = loads_first_json(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def format_line_range(numbers: list[int]) -> str:
    if not numbers:
        return ""
    unique = sorted(set(numbers))
    if len(unique) == 1:
        return f"Satır {unique[0]}"
    if unique == list(range(unique[0], unique[-1] + 1)):
        return f"Satır {unique[0]}–{unique[-1]}"
    return "Satır " + ", ".join(str(number) for number in unique)


def infer_line_reference_from_snippet(source_sql: str, snippet: str) -> str:
    """The first source line (or range) matching the snippet's first five non-blank lines."""

    if not source_sql or not (snippet or "").strip():
        return ""
    lines = source_sql.splitlines()
    if not lines:
        return ""
    snippet = snippet.strip()
    snippet_lines = [line.strip() for line in snippet.splitlines() if line.strip()]
    if not snippet_lines:
        return ""
    found: list[int] = []
    for target in snippet_lines[:5]:
        needle = re.sub(r"\s+", " ", target)
        if len(needle) < 6:
            continue
        for number, line in enumerate(lines, start=1):
            haystack = re.sub(r"\s+", " ", line.strip())
            if needle in haystack or (len(needle) > 12 and needle[:48] in haystack):
                found.append(number)
                break
    if not found:
        collapsed = re.sub(r"\s+", " ", snippet)
        if len(collapsed) >= 12:
            head = collapsed[: min(80, len(collapsed))]
            for number, line in enumerate(lines, start=1):
                haystack = re.sub(r"\s+", " ", line.strip())
                if head in haystack or head[:40] in haystack:
                    found.append(number)
                    break
    if not found:
        return ""
    low, high = min(found), max(found)
    if low == high:
        return f"Satır {low}"
    return f"Satır {low}–{high}"


def normalize_line_reference(value: str) -> str:
    """``L012`` becomes "Satır 12" and ``L012–L015`` "Satır 12–15"; other text is kept."""

    stripped = value.strip()
    if not stripped:
        return ""
    match = re.match(r"^L\s*0*(\d+)\s*[–-]\s*L?\s*0*(\d+)$", stripped, re.IGNORECASE)
    if match:
        return f"Satır {int(match.group(1))}–{int(match.group(2))}"
    match = re.match(r"^L\s*0*(\d+)$", stripped, re.IGNORECASE)
    if match:
        return f"Satır {int(match.group(1))}"
    return stripped


def line_reference_for_item(item: dict[str, Any], source_sql: str | None, snippet: str) -> str:
    """Requirement 11 order: line_reference, line_numbers, line_number, then the snippet."""

    for key in ("line_reference", "lineReference"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_line_reference(value)[:500]
    raw_numbers = item.get("line_numbers")
    if isinstance(raw_numbers, list):
        numbers: list[int] = []
        for entry in raw_numbers:
            if isinstance(entry, int) and entry > 0:
                numbers.append(entry)
            elif isinstance(entry, str) and entry.strip().isdigit():
                numbers.append(int(entry.strip()))
        if numbers:
            return format_line_range(numbers)
    line_number = item.get("line_number")
    if line_number is not None:
        try:
            number = int(line_number)
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            return f"Satır {number}"
    if source_sql and snippet.strip():
        inferred = infer_line_reference_from_snippet(source_sql, snippet)
        if inferred:
            return inferred
    return ""


def _severity(value: str) -> Severity:
    return Severity(value) if value in _VALID_SEVERITIES else Severity.LOW


def _parse_legacy_array(raw: str) -> tuple[list[dict[str, Any]], str | None]:
    """The oldest reply shape: a bare array of findings."""

    text = strip_code_fences(raw)
    if not text:
        return [], "Model yanıtında JSON dizi bulunamadı."
    try:
        data = loads_first_json(text)
    except json.JSONDecodeError as error:
        return [], f"Geçersiz JSON: {error}"
    if not isinstance(data, list):
        return [], "Çözülen JSON bir dizi değil."
    return [item for item in data if isinstance(item, dict)], None


def merge_rule_results(items: list[Any], rules: Sequence[RuleRef]) -> ParsedReply:
    """The ``rule_results`` shape: one entry per rule with its own status."""

    by_code: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_code = item.get("rule_id")
        if raw_code is None:
            raw_code = item.get("ruleId")
        if raw_code is None:
            continue
        code = str(raw_code).strip()
        if code:
            by_code[code] = item

    warnings: list[str] = []
    checks: list[RuleCheck] = []
    findings: list[Finding] = []
    for rule in rules:
        item = by_code.get(rule.code)
        if item is None:
            checks.append(
                RuleCheck(
                    rule.code,
                    rule.tier,
                    RuleResultStatus.UNKNOWN,
                    description="Model yanıtında bu kural için sonuç yok.",
                )
            )
            continue
        verdict = str(item.get("status", "")).upper().strip().replace(" ", "_").replace("-", "_")
        if verdict not in _VALID_VERDICTS:
            verdict = "UNKNOWN"
            warnings.append(f"{rule.code}: geçersiz status")
        raw_severity = item.get("severity")
        severity: Severity | None = None
        if verdict == "FAIL":
            if raw_severity is not None and str(raw_severity).strip():
                label = str(raw_severity).upper().strip()
                if label not in _VALID_SEVERITIES:
                    warnings.append(f"{rule.code}: geçersiz severity")
                severity = _severity(label)
            else:
                severity = Severity.LOW
        elif raw_severity is not None and str(raw_severity).strip():
            warnings.append(f"{rule.code}: PASS/NOT_APPLICABLE için severity yok sayıldı")
        raw_basis = item.get("decision_basis") or item.get("decisionBasis")
        basis = str(raw_basis or "").strip().lower().replace("-", "_")
        if basis and basis not in _DECISION_BASES:
            warnings.append(f"{rule.code}: geçersiz decision_basis")
            basis = ""
        if basis == "absence_of_evidence" and verdict in ("PASS", "NOT_APPLICABLE"):
            basis = ""
        description = str(item.get("description", "") or "")
        line_reference = str(item.get("line_reference", "") or "")
        snippet = str(item.get("code_snippet", "") or "")
        checks.append(
            RuleCheck(
                rule.code,
                rule.tier,
                RuleResultStatus(verdict),
                severity,
                basis,
                description,
                line_reference,
                snippet,
            )
        )
        if verdict == "FAIL":
            findings.append(
                Finding(
                    rule.code,
                    severity or Severity.LOW,
                    description or "(açıklama yok)",
                    line_reference,
                    snippet,
                )
            )
    extra = set(by_code) - {rule.code for rule in rules}
    if extra:
        warnings.append(f"Yanıtta fazladan rule_id (yok sayıldı): {sorted(extra)}")
    return ParsedReply(checks, findings, "; ".join(warnings) if warnings else None)


def _entry_applies_to_rule(
    item: dict[str, Any], code: str, rule_count: int, warnings: list[str]
) -> bool:
    """An entry without rule_code applies only when the request carried a single rule."""

    entry_code = str(item.get("rule_code") or item.get("rule_id") or "").strip()
    if not entry_code:
        if rule_count == 1:
            return True
        warnings.append("violations içinde rule_code boş; çoklu kural bağlamında yok sayıldı")
        return False
    return entry_code == code


def looks_like_non_violation(reason: str, snippet: str) -> bool:
    """Entries whose reason says the use is not a violation are dropped (Requirement 10)."""

    text = f"{reason}\n{snippet}".strip()
    if not text:
        return False
    lowered = text.lower()
    if "ihlal değil" in lowered or "ihlal değildir" in lowered:
        return True
    if (
        "dolayısıyla" in lowered
        and "ihlal" in lowered
        and ("değil" in lowered or "değildir" in lowered)
    ):
        return True
    if (
        "ihlal sayılmaz" in lowered
        or "ihlal oluşturmaz" in lowered
        or "ihlal olarak değerlendirilmez" in lowered
    ):
        return True
    if "kapsam dışı" in lowered and (
        "değil" in lowered or "uygulanmaz" in lowered or "sayılmaz" in lowered
    ):
        return True
    return "bu nedenle ihlal değil" in lowered or "bu yüzden ihlal değil" in lowered


def _passed(rule: RuleRef) -> RuleCheck:
    return RuleCheck(rule.code, rule.tier, RuleResultStatus.PASS, description=_NO_VIOLATION)


def merge_violations(
    entries: object, rules: Sequence[RuleRef], source_sql: str | None = None
) -> ParsedReply:
    """The ``{"violations": [...]}`` contract of the system prompt."""

    warnings: list[str] = []
    if not isinstance(entries, list):
        return ParsedReply([], [], "violations bir dizi değil.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(entries):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            warnings.append(f"violations[{index}] nesne değil")

    checks: list[RuleCheck] = []
    findings: list[Finding] = []
    for rule in rules:
        severity = severity_for_tier(rule.tier)
        relevant = [
            item
            for item in normalized
            if _entry_applies_to_rule(item, rule.code, len(rules), warnings)
        ]
        kept = [
            item
            for item in relevant
            if not looks_like_non_violation(
                str(item.get("reason") or ""), str(item.get("snippet") or "")
            )
        ]
        if not kept:
            checks.append(_passed(rule))
            continue
        for item in kept:
            object_name = str(item.get("object_name") or "").strip()
            reason = str(item.get("reason") or "").strip()
            snippet = str(item.get("snippet") or "")
            if object_name and reason:
                description = f"{object_name}: {reason}"
            else:
                description = object_name or reason or "(ihlal)"
            findings.append(
                Finding(
                    rule.code,
                    severity,
                    description[:FINDING_TEXT_MAX_LENGTH],
                    line_reference_for_item(item, source_sql, snippet),
                    snippet[:FINDING_TEXT_MAX_LENGTH],
                )
            )
        first = kept[0]
        first_reason = str(first.get("reason") or "").strip()
        first_snippet = str(first.get("snippet") or "")
        checks.append(
            RuleCheck(
                rule.code,
                rule.tier,
                RuleResultStatus.FAIL,
                severity,
                "direct_evidence",
                (first_reason or "İhlal tespit edildi.")[:RULE_RESULT_TEXT_MAX_LENGTH],
                line_reference_for_item(first, source_sql, first_snippet),
                first_snippet[:RULE_RESULT_TEXT_MAX_LENGTH],
            )
        )

    seen_codes = {
        str(item.get("rule_code") or item.get("rule_id") or "").strip() for item in normalized
    } - {""}
    extra = seen_codes - {rule.code for rule in rules}
    if extra:
        warnings.append(f"Bilinmeyen rule_code (yok sayıldı): {sorted(extra)}")
    return ParsedReply(checks, findings, "; ".join(warnings) if warnings else None)


def _looks_like_rule_result_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    code = entry.get("rule_id")
    if code is None:
        code = entry.get("ruleId")
    return code is not None and str(code).strip() != ""


def _looks_like_violation_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if str(entry.get("status", "")).strip():
        return False
    return bool(str(entry.get("rule_code") or "").strip())


def _coerce_json_list(value: object) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped.startswith("["):
            return None
        try:
            parsed = loads_first_json(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _rule_results_list(data: dict[str, Any]) -> list[Any] | None:
    for key in _RULE_RESULT_KEYS:
        found = _coerce_json_list(data.get(key))
        if found is not None:
            return found
    for key in _NESTED_KEYS:
        nested = data.get(key)
        if isinstance(nested, dict):
            inner = _rule_results_list(nested)
            if inner is not None:
                return inner
    for value in data.values():
        found = _coerce_json_list(value)
        if not isinstance(found, list) or not found:
            continue
        if not all(isinstance(entry, dict) for entry in found):
            continue
        if any(_looks_like_rule_result_entry(entry) for entry in found):
            return found
    return None


def parse_review_response(
    raw: str, rules: Sequence[RuleRef], source_sql: str | None = None
) -> ParsedReply:
    """Turn one model reply into rule checks and findings (Requirement 10)."""

    text = strip_code_fences(raw)
    data = _try_loads_first_json(text)
    if isinstance(data, list) and all(isinstance(entry, dict) for entry in data):
        if not data:
            return merge_violations([], rules, source_sql)
        if any(_looks_like_rule_result_entry(entry) for entry in data):
            return merge_rule_results(data, rules)
        if any(_looks_like_violation_entry(entry) for entry in data):
            return merge_violations(data, rules, source_sql)
    if isinstance(data, dict):
        violations = _coerce_violations_list_value(data.get("violations"))
        if violations is not None:
            return merge_violations(violations, rules, source_sql)
        results = _rule_results_list(data)
        if isinstance(results, list):
            return merge_rule_results(results, rules)
        return ParsedReply([], [], "JSON içinde violations veya rule_results bekleniyor.")

    if text.startswith("[") or re.search(r"\[[\s\S]*\]", text):
        return _legacy_array_reply(raw, rules)
    return ParsedReply([], [], "Model yanıtı JSON olarak çözülemedi.")


def _legacy_array_reply(raw: str, rules: Sequence[RuleRef]) -> ParsedReply:
    """A bare array of findings maps onto the first rule; its warnings are never shown."""

    items, warning = _parse_legacy_array(raw)
    rule = rules[0] if rules else RuleRef("", RulePriorityGroup.NORMAL)
    if warning and not items:
        return ParsedReply(
            [RuleCheck(rule.code, rule.tier, RuleResultStatus.UNKNOWN, description=warning[:2000])],
            [],
            None,
        )
    findings = [
        Finding(
            rule.code,
            _severity(str(item.get("severity", "LOW")).upper()),
            str(item.get("description", "")),
            str(item.get("line_reference", "")),
            str(item.get("code_snippet", "")),
        )
        for item in items
    ]
    if findings:
        first = findings[0]
        return ParsedReply(
            [
                RuleCheck(
                    rule.code,
                    rule.tier,
                    RuleResultStatus.FAIL,
                    first.severity,
                    "direct_evidence",
                    (first.description or "İhlal tespit edildi.")[:RULE_RESULT_TEXT_MAX_LENGTH],
                    first.line_reference,
                    first.code_snippet[:RULE_RESULT_TEXT_MAX_LENGTH],
                )
            ],
            findings,
            None,
        )
    return ParsedReply([_passed(rule)], [], None)


def merge_two_part_rule(
    rule: RuleRef,
    *,
    error_a: str | None,
    raw_a: str | None,
    error_b: str | None,
    raw_b: str | None,
    source_sql: str,
) -> tuple[RuleCheck, list[Finding], str | None]:
    """Combine the two part replies of one rule into one verdict (Requirement 9)."""

    single = (rule,)

    def parse(raw: str | None) -> ParsedReply:
        if not raw or not raw.strip():
            return ParsedReply([], [], None)
        return parse_review_response(raw, single, source_sql)

    if error_a and error_b:
        message = f"Parça 1/2: {error_a}; Parça 2/2: {error_b}"
        return (
            RuleCheck(rule.code, rule.tier, RuleResultStatus.UNKNOWN, description=message[:2000]),
            [],
            message,
        )
    for failed_error, failed_part, surviving_raw, surviving_part in (
        (error_a, 1, raw_b, 2),
        (error_b, 2, raw_a, 1),
    ):
        if not failed_error:
            continue
        note = (
            f"Parça {failed_part}/2 LLM isteği başarısız; "
            f"yalnızca parça {surviving_part} değerlendirildi."
        )
        surviving = parse(surviving_raw)
        if not surviving.checks:
            return (
                RuleCheck(
                    rule.code,
                    rule.tier,
                    RuleResultStatus.UNKNOWN,
                    description=(failed_error[:1500] + " " + (surviving.warning or "")).strip(),
                ),
                [],
                f"{note} {failed_error}",
            )
        combined = "; ".join(part for part in (surviving.warning, note) if part)
        return surviving.checks[0], surviving.findings, combined or None

    first_part, second_part = parse(raw_a), parse(raw_b)
    if not first_part.checks and not second_part.checks:
        warning = "; ".join(part for part in (first_part.warning, second_part.warning) if part)
        return (
            RuleCheck(
                rule.code,
                rule.tier,
                RuleResultStatus.UNKNOWN,
                description=warning or "Çözümleme sonucu boş.",
            ),
            [],
            warning,
        )
    if not first_part.checks:
        return second_part.checks[0], second_part.findings, second_part.warning
    if not second_part.checks:
        return first_part.checks[0], first_part.findings, first_part.warning

    status_a, status_b = first_part.checks[0].status, second_part.checks[0].status
    warnings = [part for part in (first_part.warning, second_part.warning) if part]
    joined = "; ".join(warnings) if warnings else None
    seen: set[tuple[str, str]] = set()
    merged: list[Finding] = []
    for finding in (*first_part.findings, *second_part.findings):
        key = (finding.code_snippet[:200], finding.description[:200])
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
    if merged:
        first = merged[0]
        return (
            RuleCheck(
                rule.code,
                rule.tier,
                RuleResultStatus.FAIL,
                first.severity or severity_for_tier(rule.tier),
                "direct_evidence",
                (first.description or "İhlal tespit edildi.")[:RULE_RESULT_TEXT_MAX_LENGTH],
                first.line_reference,
                first.code_snippet[:RULE_RESULT_TEXT_MAX_LENGTH],
            ),
            merged,
            joined,
        )
    unknown = RuleResultStatus.UNKNOWN
    if unknown in (status_a, status_b):
        description = first_part.checks[0].description or second_part.checks[0].description
        return (
            RuleCheck(rule.code, rule.tier, unknown, description=description),
            [],
            joined,
        )
    if RuleResultStatus.FAIL in (status_a, status_b):
        picked = first_part if status_a is RuleResultStatus.FAIL else second_part
        return picked.checks[0], [], joined
    if status_a is status_b is RuleResultStatus.NOT_APPLICABLE:
        return first_part.checks[0], [], joined
    return _passed(rule), [], joined
