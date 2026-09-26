"""Golden tests of reply parsing, merging, numbering and splitting.

sql-review/PRDs/003-object-review Requirement 8-13 (Acceptance 1). The first eleven tests are
carried over unchanged in meaning from the previous application's
``backend/tests/test_parse_review_response.py`` (same inputs, same expected outputs); the rest
are the additional golden tests the PRD lists.
"""

import json

import pytest

from app.domain.review import (
    Finding,
    RuleCheck,
    RulePriorityGroup,
    RuleResultStatus,
    Severity,
)
from app.services.review_engine import merge_object_warnings
from app.services.review_prompts import numbered_sql, split_into_two_parts
from app.services.review_response_parser import (
    RuleRef,
    line_reference_for_item,
    loads_first_json,
    merge_two_part_rule,
    parse_review_response,
)

pytestmark = pytest.mark.unit

CRITICAL = RulePriorityGroup.CRITICAL
NORMAL = RulePriorityGroup.NORMAL
KURAL01 = (RuleRef("Kural01", CRITICAL),)
PASS = RuleResultStatus.PASS
FAIL = RuleResultStatus.FAIL
UNKNOWN = RuleResultStatus.UNKNOWN


# --- Carried over from the previous application ------------------------------------------------


def test_object_with_trailing_prose() -> None:
    assert loads_first_json('{"violations": []}\n\nAçıklama: ihlal yok.') == {"violations": []}


def test_array_with_trailing() -> None:
    assert loads_first_json("[]\nextra") == []


def test_prefix_before_json() -> None:
    assert loads_first_json('Tamam, işte sonuç: {"violations": []}') == {"violations": []}


def test_violations_empty_plus_extra_text_yields_pass() -> None:
    parsed = parse_review_response(
        '{"violations": []}\n\nNot: SQL uygun görünüyor.', KURAL01, source_sql="SELECT 1"
    )
    assert len(parsed.checks) == 1
    assert parsed.checks[0].rule_code == "Kural01"
    assert parsed.checks[0].status is PASS
    assert parsed.findings == []
    assert parsed.warning is None


def test_violations_string_json() -> None:
    parsed = parse_review_response(json.dumps({"violations": "[]"}), KURAL01, source_sql="SELECT 1")
    assert parsed.checks[0].status is PASS
    assert parsed.warning is None


def test_markdown_fence_then_extra() -> None:
    parsed = parse_review_response(
        '```json\n{"violations": []}\n```\n\nEk not.', KURAL01, source_sql="SELECT 1"
    )
    assert parsed.checks[0].status is PASS
    assert parsed.warning is None


def test_root_array_rule_code_same_as_violations_object() -> None:
    raw = json.dumps(
        [{"rule_code": "Kural01", "object_name": "", "snippet": "SELECT 1", "reason": "örnek"}]
    )
    parsed = parse_review_response(raw, KURAL01, source_sql="SELECT 1")
    assert len(parsed.checks) == 1
    assert parsed.checks[0].rule_code == "Kural01"
    assert parsed.checks[0].status is FAIL
    assert len(parsed.findings) == 1
    assert parsed.warning is None


def test_root_empty_array_is_all_pass() -> None:
    parsed = parse_review_response("[]", KURAL01, source_sql="SELECT 1")
    assert parsed.checks[0].status is PASS
    assert parsed.findings == []
    assert parsed.warning is None


def test_numbered_sql_start_line() -> None:
    numbered = numbered_sql("a\nb", start_line=5)
    assert "L005" in numbered
    assert "L006" in numbered


def test_split_multiline_halves() -> None:
    first, second, second_start = split_into_two_parts("L1\nL2\nL3\nL4")
    assert first == "L1\nL2"
    assert second == "L3\nL4"
    assert second_start == 3


def test_merge_two_parts_both_pass() -> None:
    check, findings, _ = merge_two_part_rule(
        KURAL01[0],
        error_a=None,
        raw_a='{"violations": []}',
        error_b=None,
        raw_b='{"violations": []}',
        source_sql="SELECT 1",
    )
    assert check.status is PASS
    assert findings == []


# --- Added golden tests (Requirement 8-12) -----------------------------------------------------

SOURCE = (
    "CREATE PROCEDURE dbo.usp_Load\nAS\nBEGIN\n    SELECT * FROM dbo.Musteri\n"
    "    WHERE Kimlik IS NULL\nEND"
)


def _violation(**fields: object) -> str:
    entry = {"rule_code": "Kural01", "object_name": "", "snippet": "", "reason": "neden"}
    entry.update(fields)
    return json.dumps({"violations": [entry]})


def test_numbering_is_zero_padded_to_at_least_three_digits_and_grows() -> None:
    assert numbered_sql("a\nb") == "L001  a\nL002  b"
    assert numbered_sql("x\ny", start_line=999) == "L0999  x\nL1000  y"


def test_a_single_line_is_split_in_the_middle_of_its_characters() -> None:
    assert split_into_two_parts("abcdef") == ("abc", "def", 1)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"line_reference": "L012"}, "Satır 12"),
        ({"line_reference": "L012–L015"}, "Satır 12–15"),
        ({"line_reference": "l7-L9"}, "Satır 7–9"),
        ({"line_numbers": [4, 5, 6]}, "Satır 4–6"),
        ({"line_numbers": [6, "2", 4]}, "Satır 2, 4, 6"),
        ({"line_number": 5}, "Satır 5"),
        ({"snippet": "SELECT * FROM dbo.Musteri\nWHERE Kimlik IS NULL"}, "Satır 4–5"),
        ({"snippet": "tamamen   başka bir metin burada"}, ""),
        ({"line_reference": "Satır 3 civarı"}, "Satır 3 civarı"),
    ],
)
def test_line_reference_order_and_formats(fields: dict[str, object], expected: str) -> None:
    item: dict[str, object] = {"snippet": ""} | fields
    snippet = str(item["snippet"])
    assert line_reference_for_item(item, SOURCE, snippet) == expected


def test_findings_take_line_references_from_the_original_text() -> None:
    parsed = parse_review_response(
        _violation(snippet="WHERE Kimlik IS NULL", reason="NULL karşılaştırması"),
        KURAL01,
        SOURCE,
    )
    assert parsed.findings[0].line_reference == "Satır 5"
    assert parsed.checks[0].line_reference == "Satır 5"


@pytest.mark.parametrize(
    "reason",
    [
        "Bu kullanım ihlal değil.",
        "Tablo geçici olduğu için ihlal sayılmaz.",
        "Kapsam dışı; kural uygulanmaz.",
        "Dolayısıyla bir ihlal değildir.",
        "Bu nedenle ihlal değil",
    ],
)
def test_entries_saying_no_violation_are_not_findings(reason: str) -> None:
    parsed = parse_review_response(_violation(reason=reason), KURAL01, SOURCE)
    assert parsed.checks[0].status is PASS
    assert parsed.findings == []


def test_a_real_violation_is_kept_next_to_a_spurious_one() -> None:
    raw = json.dumps(
        {
            "violations": [
                {"rule_code": "Kural01", "snippet": "SELECT *", "reason": "ihlal değil"},
                {"rule_code": "Kural01", "snippet": "SELECT *", "reason": "Yıldız kullanılmış"},
            ]
        }
    )
    parsed = parse_review_response(raw, KURAL01, SOURCE)
    assert [finding.description for finding in parsed.findings] == ["Yıldız kullanılmış"]
    assert parsed.checks[0].description == "Yıldız kullanılmış"


def test_empty_rule_code_applies_only_to_a_single_rule_request() -> None:
    raw = json.dumps({"violations": [{"rule_code": "", "snippet": "x", "reason": "neden"}]})
    single = parse_review_response(raw, KURAL01, SOURCE)
    assert single.checks[0].status is FAIL
    assert single.warning is None

    two_rules = (RuleRef("Kural01", CRITICAL), RuleRef("Kural02", NORMAL))
    many = parse_review_response(raw, two_rules, SOURCE)
    assert [check.status for check in many.checks] == [PASS, PASS]
    assert many.warning is not None
    assert "rule_code boş; çoklu kural bağlamında yok sayıldı" in many.warning


def test_unknown_rule_codes_are_ignored_with_a_warning() -> None:
    raw = json.dumps(
        {"violations": [{"rule_code": "Kural77", "snippet": "x", "reason": "başka kural"}]}
    )
    parsed = parse_review_response(raw, KURAL01, SOURCE)
    assert parsed.checks[0].status is PASS
    assert parsed.warning == "Bilinmeyen rule_code (yok sayıldı): ['Kural77']"


def test_severity_follows_the_rule_group_in_the_violations_contract() -> None:
    raw = _violation(snippet="SELECT *")
    critical = parse_review_response(raw, KURAL01, SOURCE)
    normal = parse_review_response(raw, (RuleRef("Kural01", NORMAL),), SOURCE)
    assert critical.findings[0].severity is Severity.HIGH
    assert normal.findings[0].severity is Severity.LOW
    assert normal.checks[0].severity is Severity.LOW


def test_object_name_prefixes_the_finding_description() -> None:
    parsed = parse_review_response(_violation(object_name="usp_Load", reason="neden"), KURAL01)
    assert parsed.findings[0].description == "usp_Load: neden"


def test_rule_results_shape_invalid_status_and_severity() -> None:
    rules = (RuleRef("Kural01", CRITICAL), RuleRef("Kural02", NORMAL), RuleRef("Kural03", NORMAL))
    raw = json.dumps(
        {
            "data": {
                "rule_results": [
                    {"rule_id": "Kural01", "status": "belki", "description": "?"},
                    {"rule_id": "Kural02", "status": "fail", "severity": "KRİTİK"},
                    {"rule_id": "Kural09", "status": "PASS"},
                ]
            }
        }
    )
    parsed = parse_review_response(raw, rules, SOURCE)
    assert [check.status for check in parsed.checks] == [UNKNOWN, FAIL, UNKNOWN]
    assert parsed.checks[1].severity is Severity.LOW
    assert parsed.checks[2].description == "Model yanıtında bu kural için sonuç yok."
    assert parsed.findings == [Finding("Kural02", Severity.LOW, "(açıklama yok)", "", "")]
    assert parsed.warning == (
        "Kural01: geçersiz status; Kural02: geçersiz severity; "
        "Yanıtta fazladan rule_id (yok sayıldı): ['Kural09']"
    )


def test_a_root_array_of_rule_results_is_the_rule_results_shape() -> None:
    raw = json.dumps([{"rule_id": "Kural01", "status": "NOT_APPLICABLE", "severity": "HIGH"}])
    parsed = parse_review_response(raw, KURAL01, SOURCE)
    assert parsed.checks[0].status is RuleResultStatus.NOT_APPLICABLE
    assert parsed.checks[0].severity is None
    assert parsed.warning == "Kural01: PASS/NOT_APPLICABLE için severity yok sayıldı"


def test_an_unparsable_reply_leaves_no_result_and_a_warning() -> None:
    parsed = parse_review_response("Üzgünüm, yardımcı olamam.", KURAL01, SOURCE)
    assert parsed.checks == []
    assert parsed.warning == "Model yanıtı JSON olarak çözülemedi."


def test_an_object_without_known_keys_is_rejected_with_a_warning() -> None:
    parsed = parse_review_response('{"sonuc": "tamam"}', KURAL01, SOURCE)
    assert parsed.checks == []
    assert parsed.warning == "JSON içinde violations veya rule_results bekleniyor."


def test_the_legacy_array_maps_onto_the_reviewed_rule_without_a_warning() -> None:
    raw = 'Sonuç: [{"description": "eski", "severity": "medium", "code_snippet": "x"}] bitti'
    parsed = parse_review_response(raw, KURAL01, SOURCE)
    assert parsed.checks[0].status is FAIL
    assert parsed.findings == [Finding("Kural01", Severity.MEDIUM, "eski", "", "x")]
    assert parsed.warning is None


def _merge(**kwargs: object) -> tuple[RuleCheck, list[Finding], str | None]:
    values: dict[str, object] = {"error_a": None, "raw_a": None, "error_b": None, "raw_b": None}
    values.update(kwargs)
    return merge_two_part_rule(KURAL01[0], source_sql=SOURCE, **values)  # type: ignore[arg-type]


def test_two_parts_one_failed_part_uses_the_other_with_a_warning() -> None:
    check, findings, warning = _merge(
        error_a="LLM sunucusu yanıt vermedi (zaman aşımı).",
        raw_b=_violation(snippet="WHERE Kimlik IS NULL", reason="NULL"),
    )
    assert check.status is FAIL
    assert len(findings) == 1
    assert warning == "Parça 1/2 LLM isteği başarısız; yalnızca parça 2 değerlendirildi."

    check, _, warning = _merge(raw_a='{"violations": []}', error_b="LLM yanıtı çözümlenemedi.")
    assert check.status is PASS
    assert warning == "Parça 2/2 LLM isteği başarısız; yalnızca parça 1 değerlendirildi."


def test_two_parts_both_failed_is_unknown() -> None:
    check, findings, warning = _merge(error_a="A hatası", error_b="B hatası")
    assert check.status is UNKNOWN
    assert findings == []
    assert warning == "Parça 1/2: A hatası; Parça 2/2: B hatası"


def test_two_parts_findings_are_deduplicated_and_fail() -> None:
    same = _violation(snippet="SELECT * FROM dbo.Musteri", reason="Yıldız")
    other = _violation(snippet="WHERE Kimlik IS NULL", reason="NULL")
    check, findings, _ = _merge(
        raw_a=same,
        raw_b=json.dumps(
            {"violations": [json.loads(same)["violations"][0], json.loads(other)["violations"][0]]}
        ),
    )
    assert check.status is FAIL
    assert [finding.description for finding in findings] == ["Yıldız", "NULL"]


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ([{"rule_id": "Kural01", "status": "UNKNOWN"}], '{"violations": []}', UNKNOWN),
        ([{"rule_id": "Kural01", "status": "FAIL"}], '{"violations": []}', FAIL),
        (
            [{"rule_id": "Kural01", "status": "NOT_APPLICABLE"}],
            json.dumps([{"rule_id": "Kural01", "status": "NOT_APPLICABLE"}]),
            RuleResultStatus.NOT_APPLICABLE,
        ),
        ([{"rule_id": "Kural01", "status": "NOT_APPLICABLE"}], '{"violations": []}', PASS),
    ],
)
def test_two_parts_without_findings_combine_statuses(
    first: list[dict[str, str]], second: str, expected: RuleResultStatus
) -> None:
    check, _, _ = _merge(raw_a=json.dumps(first), raw_b=second)
    assert check.status is expected


def test_object_warning_groups_equal_llm_failures_and_hides_legacy_warnings() -> None:
    from app.domain.review import ReviewRule
    from app.services.review_engine import _RuleOutcome

    rules = [ReviewRule(f"Kural0{n}", NORMAL, "metin") for n in range(1, 6)]
    unknown = RuleCheck("Kural01", NORMAL, UNKNOWN)
    outcomes = [
        _RuleOutcome(unknown, [], "LLM sunucusuna bağlanılamadı.", llm_failure=True),
        _RuleOutcome(unknown, [], "Bilinmeyen rule_code (yok sayıldı): ['Kural99']"),
        _RuleOutcome(unknown, [], "LLM sunucusuna bağlanılamadı.", llm_failure=True),
        _RuleOutcome(unknown, [], "Eski çıktı biçimi uyarısı"),
        _RuleOutcome(unknown, [], None),
    ]
    assert merge_object_warnings(rules, outcomes, None) == (
        "[Kural01, Kural03] LLM sunucusuna bağlanılamadı.; "
        "[Kural02] Bilinmeyen rule_code (yok sayıldı): ['Kural99']"
    )
    note = "Metnin yalnız ilk 120.000 karakteri incelendi."
    assert merge_object_warnings(rules[:1], outcomes[:1], note) == (
        f"{note}; [Kural01] LLM sunucusuna bağlanılamadı."
    )
    assert merge_object_warnings(rules[4:], outcomes[4:], None) is None
