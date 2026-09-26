"""Rule-set rules that need no persistence (sql-review/PRDs/001-rule-management).

Normalization and identifier checks of a submitted draft, the canonical content digest that
decides whether a publish creates a new version, and the published rule set that review runs
pin when they start. Rule text is never logged; the dataclasses keep it out of their repr.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.domain.models.rule_set import (
    RULE_CODE_PATTERN,
    RULE_SET_MAX_RULES,
    RULE_TEXT_MAX_LENGTH,
    RulePriorityGroup,
)

_RULE_CODE = re.compile(RULE_CODE_PATTERN)


@dataclass(frozen=True, slots=True)
class Rule:
    """One review rule: its KuralNN code, text and the object-metadata flag."""

    code: str
    text: str = field(repr=False)
    requires_metadata: bool = False


@dataclass(frozen=True, slots=True)
class RuleGroups:
    """Rules of a draft or version in their two priority groups, in LLM order."""

    critical: tuple[Rule, ...] = ()
    normal: tuple[Rule, ...] = ()

    def grouped(self) -> Iterable[tuple[RulePriorityGroup, tuple[Rule, ...]]]:
        yield RulePriorityGroup.CRITICAL, self.critical
        yield RulePriorityGroup.NORMAL, self.normal

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(rule.code for rule in (*self.critical, *self.normal))

    @property
    def is_empty(self) -> bool:
        return not self.critical and not self.normal


@dataclass(frozen=True, slots=True)
class PublishedRuleSet:
    """The latest published version a review run pins once, at its start (Requirement 7)."""

    version_id: int
    number: int
    rules: RuleGroups


class RuleSetValidationError(Exception):
    """A rejected draft; the code and Turkish message form the 422 error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def format_rule_code(number: int) -> str:
    """Kural01 ... Kural99, then Kural100 ...; numbers start at 1."""

    if number < 1:
        raise ValueError("rule numbers start at 1")
    return f"Kural{number:02d}"


def rule_number(code: str) -> int | None:
    """The number of a well-formed KuralNN code, otherwise None."""

    match = _RULE_CODE.fullmatch(code)
    return int(match.group(1)) if match else None


def normalize_draft(critical: Sequence[Rule], normal: Sequence[Rule]) -> RuleGroups:
    """Trim texts, drop blank rules and enforce the format, uniqueness and size limits.

    Requirement 2 and the format/duplicate half of Requirement 3; whether a new code was used
    before needs the stored history and is checked by ``next_rule_number_after``.
    """

    groups: list[tuple[Rule, ...]] = []
    seen: set[str] = set()
    for submitted in (critical, normal):
        kept: list[Rule] = []
        for rule in submitted:
            text = rule.text.strip()
            if not text:
                continue
            if rule_number(rule.code) is None:
                raise RuleSetValidationError(
                    "rule_id_invalid", "Kural kimliği KuralNN biçiminde olmalıdır."
                )
            if rule.code in seen:
                raise RuleSetValidationError(
                    "rule_id_duplicate", "Aynı kural kimliği birden çok kurala verilemez."
                )
            if len(text) > RULE_TEXT_MAX_LENGTH:
                raise RuleSetValidationError(
                    "rule_text_too_long", "Kural metni en çok 8.000 karakter olabilir."
                )
            seen.add(rule.code)
            kept.append(Rule(rule.code, text, rule.requires_metadata))
        groups.append(tuple(kept))
    if len(seen) > RULE_SET_MAX_RULES:
        raise RuleSetValidationError("rule_set_too_large", "Taslak en çok 200 kural içerebilir.")
    return RuleGroups(critical=groups[0], normal=groups[1])


def next_rule_number_after(
    draft: RuleGroups,
    *,
    current_codes: frozenset[str],
    used_codes: frozenset[str],
    next_rule_number: int,
) -> int:
    """Validate the new codes of a normalized draft and return the updated first free number.

    A code already in the current draft keeps its rule. Any other code is a new rule and must be
    at least the first free number and never used in any draft or version of the tenant
    (Requirement 3); numbers below the first free one count as used.
    """

    highest = next_rule_number - 1
    for code in draft.codes - current_codes:
        number = rule_number(code)
        if number is None:  # pragma: no cover - normalize_draft rejects malformed codes first
            raise RuleSetValidationError(
                "rule_id_invalid", "Kural kimliği KuralNN biçiminde olmalıdır."
            )
        if code in used_codes or number < next_rule_number:
            raise RuleSetValidationError(
                "rule_id_reused",
                "Bu kural kimliği daha önce kullanıldı; yeni bir kurala verilemez.",
            )
        highest = max(highest, number)
    return highest + 1


def content_sha256(rules: RuleGroups) -> str:
    """Lower-case SHA-256 of the canonical content: groups, order, codes, texts and flags."""

    canonical = {
        group.value: [[rule.code, rule.text, rule.requires_metadata] for rule in members]
        for group, members in rules.grouped()
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
