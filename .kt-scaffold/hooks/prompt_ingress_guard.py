#!/usr/bin/env python3
"""Dependency-free, prompt-text-only ingress gate for supported Agent clients."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import hashlib
import json
import re
import runpy
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CLIENTS = (
    "claude-code",
    "codex",
    "github-copilot-vscode",
    "cursor",
)
POLICY_RELATIVE_PATH = Path("agent-platform/policies/prompt-ingress/prompt-ingress-policy.json")
STATE_POLICY_RELATIVE_PATH = Path(
    "agent-platform/policies/local-state/local-governance-state-policy.json"
)
PROJECT_MANIFEST_RELATIVE_PATH = Path(".kt-scaffold/project-manifest.json")
FALLBACK_MAX_EVENT_BYTES = 131_072
MAX_POLICY_BYTES = 262_144
MAX_STATE_POLICY_BYTES = 65_536
MAX_PROJECT_MANIFEST_BYTES = 262_144
MAX_NATIVE_CORRELATION_BYTES = 4_096
PROJECT_ID_RE = re.compile(r"^project-(?!0{32}$)[0-9a-f]{32}$")
EVENT_ID_RE = re.compile(r"^event:(?!0{32}$)[0-9a-f]{32}$")
EXPECTED_STATE_LAYOUT = {
    "macos": "/Users/Shared/kt-scaffold/governance/",
    "windows": "%ProgramData%\\kt-scaffold\\governance\\",
    "linux": "/var/lib/kt-scaffold/governance/",
    "prompt_receipts": "{project_id}/prompt-ingress/",
    "authority_pin": "{project_id}/authority-pin/",
    "review_baselines": "{project_id}/review-baseline/",
    "commit_guard_receipts": "{project_id}/commit-governance/",
}
EXPECTED_STATE_LIMITS = {
    "max_prompt_record_bytes": 262_144,
    "max_authority_receipt_bytes": 65_536,
    "max_review_baseline_file_bytes": 2_097_152,
    "max_commit_guard_event_bytes": 65_536,
}
MAX_IDENTITY_FIELD_LENGTHS = {
    "display_name": 200,
    "email": 320,
    "account_id": 200,
}
SAFE_BLOCK_MESSAGE = (
    "Mesajiniz (prompt) gonderilmedi: icinde paylasilmamasi gereken bir bilgi (ornegin parola, "
    "erisim anahtari, e-posta, T.C. kimlik, IBAN, kart veya telefon numarasi) ya da islenemeyen "
    "bir girdi var. Bu bilgiyi cikarip mesaji yeniden gonderin."
)
SAFE_ERROR_MESSAGE = (
    "Mesajiniz (prompt) gonderilmedi, cunku gonderimden once yapilan veri guvenligi denetimi "
    "tamamlanamadi. Proje klasorunde python3 .kt-scaffold/hooks/governance_records.py preflight "
    "komutuyla Python yorumlayicisinin ve denetim kurallarinin (politika) hazir olup olmadigini "
    "kontrol edin; denetim hatasi cozulmeden mesaji yeniden gondermeyin."
)
RECORD_WARNING = "GOVERNANCE_RECORD_UNAVAILABLE: {code}; prompt karari degismedi."
INTERPRETER_MESSAGE = (
    "Mesajiniz (prompt) gonderilmedi, cunku gonderimden once yapilan veri guvenligi denetimi "
    "tamamlanamadi (python-runtime-mismatch): projenin Python ortami (.venv klasoru) yok ya da "
    "surumu teknoloji profilindeki Python surumuyle uyusmuyor. .venv hazir olana kadar her "
    "mesaj durdurulur. Terminalde proje klasorunde su komutu calistirip yeniden deneyin: "
    "{command}"
)
EXPECTED_PRIVATE_KEY_BEGIN_PATTERN = (
    r"-----BEGIN (?:[A-Z0-9]{1,24}(?: [A-Z0-9]{1,24}){0,3} )?PRIVATE KEY-----"
)
PRIVATE_KEY_BEGIN_MARKER_RE = re.compile(EXPECTED_PRIVATE_KEY_BEGIN_PATTERN)
PRIVATE_KEY_END_MARKER_RE = re.compile(
    r"-----END (?:[A-Z0-9]{1,24}(?: [A-Z0-9]{1,24}){0,3} )?PRIVATE KEY-----"
)
PRIVATE_KEY_BODY_LINE_RE = re.compile(r"[A-Za-z0-9+/]+={0,2}")
MAX_PRIVATE_KEY_BODY_LINES = 256
MAX_PRIVATE_KEY_BODY_LINE_CHARS = 128
MAX_PRIVATE_KEY_BLOCK_CHARS = 32_768
DETECTOR_CLASSES = frozenset(
    {
        "labelled-secret",
        "cloud-access-key",
        "private-key",
        "email",
        "tckn",
        "iban",
        "payment-card",
        "phone-number",
    }
)
WHOLE_PROMPT_REDACTION_CLASSES = frozenset({"labelled-secret", "private-key"})
PROMPT_CAPTURE_KEYS = frozenset(
    {
        "mode",
        "text",
        "sha256",
        "redaction_strategy",
        "redaction_count",
        "redacted_classes",
    }
)
PROHIBITED_RECEIPT_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "raw_sha256",
        "input_sha256",
        "input_digest_kind",
    }
)
EXPECTED_PERSISTENCE_POLICY = {
    "capture_scope": "user-prompt-text-only",
    "clean_prompt": "exact",
    "sensitive_prompt": "risk-class-aware-redacted",
    "invalid_prompt": "unavailable",
    "redaction_strategy": "validated-detector-spans-v1",
    "redaction_token_template": "[REDACTED:{class}]",
    "whole_prompt_redaction_classes": ["labelled-secret", "private-key"],
    "whole_prompt_redaction_strategy": "whole-prompt-redacted-v1",
    "whole_prompt_redaction_token": "[REDACTED:high-risk-prompt]",
    "digest_scope": "persisted-prompt-capture-only",
    "raw_sensitive_digest_allowed": False,
    "excluded_content_persistence": False,
}


class GuardError(ValueError):
    """A safe-to-collapse prompt ingress failure."""


def _error_message(_error: BaseException) -> str:
    return SAFE_ERROR_MESSAGE


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _new_nonzero_hex(byte_count: int) -> str:
    while True:
        value = secrets.token_hex(byte_count)
        if int(value, 16) != 0:
            return value


def _safe_identity_field(value: object, *, field: str) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if len(value) > MAX_IDENTITY_FIELD_LENGTHS[field]:
        return None
    if any(
        ord(character) < 32 or 127 <= ord(character) <= 159 or ord(character) in {0x2028, 0x2029}
        for character in value
    ):
        return None
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        return None
    if field == "email":
        if value.count("@") != 1 or any(character.isspace() for character in value):
            return None
        local_part, domain = value.split("@", maxsplit=1)
        if not local_part or not domain:
            return None
    return value


def _identity_reference(client_id: str, event: dict[str, Any] | None) -> tuple[str, str]:
    supplied: dict[str, Any] | None = None
    if event is not None:
        for key in ("audit_identity", "user"):
            candidate = event.get(key)
            if isinstance(candidate, dict):
                supplied = candidate
                break

    display_name = _safe_identity_field(
        supplied.get("display_name", supplied.get("name")) if supplied else None,
        field="display_name",
    )
    email = _safe_identity_field(supplied.get("email") if supplied else None, field="email")
    account_id = _safe_identity_field(
        supplied.get("account_id", supplied.get("id")) if supplied else None,
        field="account_id",
    )
    if any(value is not None for value in (display_name, email, account_id)):
        source = "client-visible"
    else:
        try:
            os_login: object = getpass.getuser()
        except (KeyError, OSError):
            os_login = None
        display_name = _safe_identity_field(os_login, field="display_name")
        email = None
        account_id = None
        source = "os-fallback" if display_name is not None else "unavailable"

    identity = {
        "schema_version": "1.0",
        "kind": "VibecoderIdentity",
        "client_id": client_id,
        "display_name": display_name,
        "email": email,
        "account_id": account_id,
        "source": source,
    }
    canonical = (
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return f"vibecoder-identity:sha256:{_sha256(canonical)}", source


def _native_correlation_value(
    event: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> str | None:
    if event is None:
        return None
    for key in keys:
        value = event.get(key)
        if not isinstance(value, str) or not value or "\x00" in value:
            continue
        encoded = value.encode("utf-8")
        if len(encoded) <= MAX_NATIVE_CORRELATION_BYTES:
            return _sha256(encoded)
    return None


def _prompt_correlation(
    event: dict[str, Any] | None,
    *,
    invocation_token: str,
) -> dict[str, str]:
    session_digest = _native_correlation_value(
        event,
        ("session_id", "conversation_id", "chat_id"),
    )
    turn_digest = _native_correlation_value(
        event,
        ("prompt_id", "turn_id", "request_id", "message_id", "generation_id"),
    )
    return {
        "prompt_session_id": (
            f"session:client.{session_digest}"
            if session_digest is not None
            else f"session:local.{_new_nonzero_hex(16)}"
        ),
        "prompt_session_id_source": (
            "client-envelope"
            if session_digest is not None
            else "local-generated-client-unavailable"
        ),
        "prompt_turn_id": (
            f"turn:client.{turn_digest}"
            if turn_digest is not None
            else f"turn:local.{invocation_token}"
        ),
        "prompt_turn_id_source": (
            "client-envelope" if turn_digest is not None else "local-generated-client-unavailable"
        ),
    }


UNAVAILABLE_MODEL: dict[str, object] = {"source": "unavailable", "id": None, "effort": None}


def _event_normalizer() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name("llm_call_events.py")
    if path.is_symlink() or not path.is_file():
        raise GuardError("event-normalizer-unavailable")
    return runpy.run_path(str(path))


def _observed_model(client_id: str, event: dict[str, Any] | None) -> dict[str, object]:
    """The model and effort the client reports; observation never changes the prompt decision."""
    try:
        model = _event_normalizer()["observed_model"](event, client_id)
    except Exception:
        return dict(UNAVAILABLE_MODEL)
    return model if isinstance(model, dict) else dict(UNAVAILABLE_MODEL)


def _invocation_context(
    client_id: str,
    event: dict[str, Any] | None,
    *,
    project_id: str,
    state_policy: dict[str, Any],
    state_policy_digest: str,
) -> dict[str, object]:
    event_token = _new_nonzero_hex(16)
    invocation_token = _new_nonzero_hex(16)
    occurred_at = datetime.now(timezone.utc)  # noqa: UP017 - generated hook supports Python 3.9.
    audit_identity_ref, audit_identity_source = _identity_reference(client_id, event)
    return {
        "event_id": f"event:{event_token}",
        "invocation_id": f"invocation:{invocation_token}",
        "occurred_at": occurred_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "project_id": project_id,
        "state_policy_version": state_policy["metadata"]["version"],
        "state_policy_sha256": state_policy_digest,
        "storage_authority": "shared-governance-root",
        "immutable_audit_storage_proof": False,
        "run_id": f"run:{_new_nonzero_hex(16)}",
        "trace_context": {
            "schema_version": "1.0",
            "trace_id": _new_nonzero_hex(16),
            "span_id": _new_nonzero_hex(8),
            "parent_span_id": None,
            "trace_flags": "01",
        },
        **_prompt_correlation(event, invocation_token=invocation_token),
        "audit_identity_ref": audit_identity_ref,
        "audit_identity_source": audit_identity_source,
        "model": _observed_model(client_id, event),
    }


def _read_project_id(project_root: Path) -> str:
    manifest_path = project_root / PROJECT_MANIFEST_RELATIVE_PATH
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise GuardError("project-identity-unavailable")
    try:
        resolved_manifest = manifest_path.resolve(strict=True)
        resolved_root = project_root.resolve(strict=True)
        size = manifest_path.stat().st_size
    except OSError as exc:
        raise GuardError("project-identity-unavailable") from exc
    if not resolved_manifest.is_relative_to(resolved_root):
        raise GuardError("project-identity-outside-project")
    if size <= 0 or size > MAX_PROJECT_MANIFEST_BYTES:
        raise GuardError("project-identity-invalid")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("project-identity-invalid") from exc
    project_id = payload.get("project_id") if isinstance(payload, dict) else None
    if not isinstance(project_id, str) or PROJECT_ID_RE.fullmatch(project_id) is None:
        raise GuardError("project-identity-invalid")
    return project_id


def _read_state_policy(project_root: Path) -> tuple[dict[str, Any], str]:
    policy_path = project_root / STATE_POLICY_RELATIVE_PATH
    if policy_path.is_symlink() or not policy_path.is_file():
        raise GuardError("state-policy-unavailable")
    try:
        resolved_policy = policy_path.resolve(strict=True)
        resolved_root = project_root.resolve(strict=True)
        size = policy_path.stat().st_size
    except OSError as exc:
        raise GuardError("state-policy-unavailable") from exc
    if not resolved_policy.is_relative_to(resolved_root):
        raise GuardError("state-policy-outside-project")
    if size <= 0 or size > MAX_STATE_POLICY_BYTES:
        raise GuardError("state-policy-invalid")
    try:
        raw = policy_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("state-policy-invalid") from exc
    if not isinstance(payload, dict):
        raise GuardError("state-policy-invalid")
    metadata = payload.get("metadata")
    layout = payload.get("layout")
    limits = payload.get("limits")
    retention = payload.get("retention")
    export = payload.get("export")
    assurance = payload.get("assurance")
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("kind") != "LocalGovernanceStatePolicy"
        or not isinstance(metadata, dict)
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(metadata.get("version"))) is None
        or layout != EXPECTED_STATE_LAYOUT
        or retention != {"automatic_delete": False, "delete_requires_export_ack": True}
        or export
        != {
            "enabled": False,
            "endpoint": None,
            "persistent_queue": "collector-file-storage-not-configured",
            "protocol": "otlp/https",
        }
        or assurance
        != {
            "clean_prompt_exact_content_allowed": True,
            "excluded_content_allowed": False,
            "local_spool_immutable": False,
            "production_admission": False,
            "raw_sensitive_content_allowed": False,
        }
    ):
        raise GuardError("state-policy-invalid")
    if limits != EXPECTED_STATE_LIMITS:
        raise GuardError("state-policy-invalid")
    return payload, _sha256(raw)


def _read_policy(project_root: Path) -> tuple[dict[str, Any], str]:
    policy_path = project_root / POLICY_RELATIVE_PATH
    if policy_path.is_symlink() or not policy_path.is_file():
        raise GuardError("policy-unavailable")
    try:
        resolved_policy = policy_path.resolve(strict=True)
        resolved_root = project_root.resolve(strict=True)
    except OSError as exc:
        raise GuardError("policy-unavailable") from exc
    if not resolved_policy.is_relative_to(resolved_root):
        raise GuardError("policy-outside-project")
    try:
        size = policy_path.stat().st_size
    except OSError as exc:
        raise GuardError("policy-unavailable") from exc
    if size <= 0 or size > MAX_POLICY_BYTES:
        raise GuardError("policy-size-invalid")
    try:
        raw = policy_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError("policy-invalid") from exc
    if not isinstance(payload, dict):
        raise GuardError("policy-invalid")
    _validate_policy(payload)
    return payload, _sha256(raw)


def _validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != "2.0" or policy.get("kind") != "PromptIngressPolicy":
        raise GuardError("policy-invalid")
    metadata = policy.get("metadata")
    limits = policy.get("limits")
    persistence = policy.get("persistence")
    detectors = policy.get("detectors")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("version"), str):
        raise GuardError("policy-invalid")
    if not isinstance(limits, dict):
        raise GuardError("policy-invalid")
    if persistence != EXPECTED_PERSISTENCE_POLICY:
        raise GuardError("policy-invalid")
    event_limit = limits.get("max_event_bytes")
    prompt_limit = limits.get("max_prompt_bytes")
    if (
        not isinstance(event_limit, int)
        or isinstance(event_limit, bool)
        or not 1_024 <= event_limit <= 1_048_576
        or not isinstance(prompt_limit, int)
        or isinstance(prompt_limit, bool)
        or not 1 <= prompt_limit <= 524_288
        or prompt_limit > event_limit
    ):
        raise GuardError("policy-invalid")
    if not isinstance(detectors, list) or not detectors:
        raise GuardError("policy-invalid")
    seen: set[str] = set()
    for detector in detectors:
        if not isinstance(detector, dict):
            raise GuardError("policy-invalid")
        detector_id = detector.get("id")
        detector_class = detector.get("class")
        implementation = detector.get("implementation")
        if (
            not isinstance(detector_id, str)
            or detector_id in seen
            or detector_class not in DETECTOR_CLASSES
            or not isinstance(implementation, dict)
            or implementation.get("kind") != "regex"
            or implementation.get("engine") != "python-re"
            or not isinstance(implementation.get("pattern"), str)
            or not isinstance(implementation.get("flags"), list)
            or implementation.get("validator")
            not in {
                None,
                "private-key-pem-block",
                "tckn-checksum",
                "iban-mod97",
                "luhn-checksum",
            }
        ):
            raise GuardError("policy-invalid")
        expected_validator = {
            "private-key": "private-key-pem-block",
            "tckn": "tckn-checksum",
            "iban": "iban-mod97",
            "payment-card": "luhn-checksum",
        }.get(detector_class)
        if implementation.get("validator") != expected_validator:
            raise GuardError("policy-invalid")
        if detector_class == "private-key" and (
            implementation.get("pattern") != EXPECTED_PRIVATE_KEY_BEGIN_PATTERN
            or implementation.get("flags") != []
        ):
            raise GuardError("policy-invalid")
        seen.add(detector_id)
        pattern = _compile_detector(implementation)
        if pattern.search("") is not None:
            raise GuardError("policy-invalid")


def _compile_detector(implementation: dict[str, Any]) -> re.Pattern[str]:
    flag_value = 0
    for flag in implementation["flags"]:
        if flag == "IGNORECASE":
            flag_value |= re.IGNORECASE
        elif flag == "MULTILINE":
            flag_value |= re.MULTILINE
        else:
            raise GuardError("policy-invalid")
    try:
        return re.compile(implementation["pattern"], flag_value)
    except re.error as exc:
        raise GuardError("policy-invalid") from exc


def _read_event(limit: int) -> tuple[bytes, dict[str, Any] | None]:
    raw = sys.stdin.buffer.read(limit + 1)
    if len(raw) > limit:
        return raw, None
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw, None
    return raw, event if isinstance(event, dict) else None


def _valid_tckn(candidate: str) -> bool:
    digits = [int(value) for value in candidate if value.isdigit()]
    if len(digits) != 11 or digits[0] == 0:
        return False
    tenth = ((sum(digits[0:9:2]) * 7) - sum(digits[1:8:2])) % 10
    return digits[9] == tenth and digits[10] == sum(digits[:10]) % 10


def _valid_luhn(candidate: str) -> bool:
    digits = [int(value) for value in candidate if value.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, value in enumerate(digits):
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _valid_iban(candidate: str) -> bool:
    normalized = candidate.replace(" ", "").upper()
    if (
        not normalized.isascii()
        or not normalized.isalnum()
        or not 15 <= len(normalized) <= 34
        or not normalized[:2].isalpha()
        or not normalized[2:4].isdigit()
        or (normalized.startswith("TR") and len(normalized) != 26)
    ):
        return False
    remainder = 0
    for character in normalized[4:] + normalized[:4]:
        expanded = character if character.isdigit() else str(ord(character) - ord("A") + 10)
        for digit in expanded:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def _validated_match(validator: str | None, candidate: str) -> bool:
    if validator == "tckn-checksum":
        return _valid_tckn(candidate)
    if validator == "iban-mod97":
        return _valid_iban(candidate)
    if validator == "luhn-checksum":
        return _valid_luhn(candidate)
    if validator == "private-key-pem-block":
        raise GuardError("private-key-validator-dispatch-invalid")
    return True


def _private_key_pem_spans(prompt: str) -> list[tuple[int, int]]:
    begin_markers = list(PRIVATE_KEY_BEGIN_MARKER_RE.finditer(prompt))
    end_markers = list(PRIVATE_KEY_END_MARKER_RE.finditer(prompt))
    if not begin_markers:
        if end_markers:
            raise GuardError("private-key-pem-malformed")
        return []

    spans: list[tuple[int, int]] = []
    previous_end = -1
    for index, begin in enumerate(begin_markers):
        if begin.start() < previous_end:
            raise GuardError("private-key-pem-malformed")

        marker = begin.group(0)
        label = marker.removeprefix("-----BEGIN ").removesuffix("-----")
        if prompt.startswith("\r\n", begin.end()):
            body_start = begin.end() + 2
        elif prompt.startswith("\n", begin.end()):
            body_start = begin.end() + 1
        else:
            raise GuardError("private-key-pem-malformed")

        end_marker = f"-----END {label}-----"
        end_start = prompt.find(end_marker, body_start)
        if end_start < 0:
            raise GuardError("private-key-pem-unclosed")
        if index + 1 < len(begin_markers) and begin_markers[index + 1].start() < end_start:
            raise GuardError("private-key-pem-malformed")

        block_end = end_start + len(end_marker)
        if block_end - begin.start() > MAX_PRIVATE_KEY_BLOCK_CHARS:
            raise GuardError("private-key-pem-bounds-exceeded")

        body_with_final_newline = prompt[body_start:end_start]
        if body_with_final_newline.endswith("\r\n"):
            body = body_with_final_newline[:-2]
        elif body_with_final_newline.endswith("\n"):
            body = body_with_final_newline[:-1]
        else:
            raise GuardError("private-key-pem-malformed")
        lines = body.splitlines()
        if not 1 <= len(lines) <= MAX_PRIVATE_KEY_BODY_LINES:
            raise GuardError("private-key-pem-bounds-exceeded")
        if any(
            not 1 <= len(line) <= MAX_PRIVATE_KEY_BODY_LINE_CHARS
            or PRIVATE_KEY_BODY_LINE_RE.fullmatch(line) is None
            or (index < len(lines) - 1 and "=" in line)
            for index, line in enumerate(lines)
        ):
            raise GuardError("private-key-pem-malformed")

        spans.append((begin.start(), block_end))
        previous_end = block_end

    if any(
        not any(start <= marker.start() and marker.end() <= end for start, end in spans)
        for marker in end_markers
    ):
        raise GuardError("private-key-pem-malformed")
    return spans


def _scan(
    prompt: str,
    policy: dict[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    counts: list[dict[str, object]] = []
    spans: list[dict[str, object]] = []
    for detector in policy["detectors"]:
        implementation = detector["implementation"]
        pattern = _compile_detector(implementation)
        if implementation["validator"] == "private-key-pem-block":
            validated_spans = _private_key_pem_spans(prompt)
        else:
            validated_spans = [
                (match.start(), match.end())
                for match in pattern.finditer(prompt)
                if _validated_match(implementation["validator"], match.group(0))
            ]
        count = len(validated_spans)
        if count:
            counts.append(
                {
                    "detector_id": detector["id"],
                    "class": detector["class"],
                    "count": count,
                }
            )
            spans.extend(
                {
                    "start": start,
                    "end": end,
                    "detector_id": detector["id"],
                    "class": detector["class"],
                }
                for start, end in validated_spans
            )
    return (
        sorted(counts, key=lambda item: (str(item["detector_id"]), str(item["class"]))),
        sorted(
            spans,
            key=lambda item: (
                int(item["start"]),
                -(int(item["end"]) - int(item["start"])),
                str(item["detector_id"]),
                int(item["end"]),
            ),
        ),
    )


def _non_overlapping_spans(spans: list[dict[str, object]]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    selected_end = -1
    for span in spans:
        start = int(span["start"])
        end = int(span["end"])
        if start < 0 or end <= start:
            raise GuardError("redaction-span-invalid")
        if start < selected_end:
            continue
        selected.append(span)
        selected_end = end
    return selected


def _sanitize_prompt(
    prompt: str,
    spans: list[dict[str, object]],
    policy: dict[str, Any],
) -> tuple[str, list[dict[str, object]]]:
    selected = _non_overlapping_spans(spans)
    if not selected:
        return prompt, []
    cursor = 0
    parts: list[str] = []
    token_template = str(policy["persistence"]["redaction_token_template"])
    for span in selected:
        start = int(span["start"])
        end = int(span["end"])
        if end > len(prompt):
            raise GuardError("redaction-span-invalid")
        parts.append(prompt[cursor:start])
        parts.append(token_template.format_map({"class": str(span["class"])}))
        cursor = end
    parts.append(prompt[cursor:])
    return "".join(parts), selected


def _unavailable_prompt_capture() -> dict[str, object]:
    return {
        "mode": "unavailable",
        "text": None,
        "sha256": None,
        "redaction_strategy": "none",
        "redaction_count": 0,
        "redacted_classes": [],
    }


def _prompt_capture(
    prompt: str,
    spans: list[dict[str, object]],
    policy: dict[str, Any],
) -> dict[str, object]:
    for span in spans:
        start = int(span["start"])
        end = int(span["end"])
        if start < 0 or end <= start or end > len(prompt):
            raise GuardError("redaction-span-invalid")
    redacted_classes = sorted({str(span["class"]) for span in spans})
    if WHOLE_PROMPT_REDACTION_CLASSES.intersection(redacted_classes):
        sanitized_prompt = str(policy["persistence"]["whole_prompt_redaction_token"])
        return {
            "mode": "sensitive-whole-prompt-redacted",
            "text": sanitized_prompt,
            "sha256": _sha256(sanitized_prompt.encode("utf-8")),
            "redaction_strategy": str(policy["persistence"]["whole_prompt_redaction_strategy"]),
            "redaction_count": 1,
            "redacted_classes": redacted_classes,
        }

    sanitized_prompt, selected = _sanitize_prompt(prompt, spans, policy)
    return {
        "mode": "sensitive-span-redacted" if selected else "clean-exact",
        "text": sanitized_prompt,
        "sha256": _sha256(sanitized_prompt.encode("utf-8")),
        "redaction_strategy": (
            str(policy["persistence"]["redaction_strategy"]) if selected else "none"
        ),
        "redaction_count": len(selected),
        "redacted_classes": sorted({str(span["class"]) for span in selected}),
    }


def _event_name(client_id: str) -> str:
    return "beforeSubmitPrompt" if client_id == "cursor" else "UserPromptSubmit"


def _decision_output(
    client_id: str, blocked: bool, *, message: str = SAFE_BLOCK_MESSAGE
) -> dict[str, object]:
    if client_id == "cursor":
        result: dict[str, object] = {"continue": not blocked}
        if blocked:
            result["user_message"] = message
        return result
    if client_id == "github-copilot-vscode":
        result = {"continue": not blocked}
        if blocked:
            result.update(
                {
                    "stopReason": message,
                    "systemMessage": message,
                }
            )
        return result
    return {"decision": "block", "reason": message} if blocked else {}


def _records() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name("governance_records.py")
    if path.is_symlink() or not path.is_file():
        raise GuardError("record-writer-unavailable")
    return runpy.run_path(str(path))


def _record_location() -> Any:
    """The shared governance root; ``None`` selects the fixed operating-system location."""
    return None


def _native(record: dict[str, object], field: str) -> str | None:
    """A record carries a session or turn only when the client supplied it; never a local one."""
    value = record.get(field)
    if record.get(f"{field}_source") != "client-envelope" or not isinstance(value, str):
        return None
    return value


def _write_receipt(receipt: dict[str, object]) -> str | None:
    """Persist the receipt in the shared root; return a warning code instead of blocking."""

    _validate_receipt_for_persistence(receipt)
    client_id = str(receipt["client_id"])
    event_id = str(receipt["event_id"])
    if client_id not in CLIENTS or EVENT_ID_RE.fullmatch(event_id) is None:
        raise GuardError("receipt-identity-invalid")
    project_id = str(receipt["project_id"])
    context = {
        "client": client_id,
        "client_source": "command",
        "session_hash": _native(receipt, "prompt_session_id"),
        "turn_hash": _native(receipt, "prompt_turn_id"),
        "identity_source": (
            "client-envelope"
            if _native(receipt, "prompt_session_id") and _native(receipt, "prompt_turn_id")
            else "unavailable"
        ),
    }
    try:
        writer = _records()
        location = _record_location()
        writer["write_event"](
            "prompt-ingress",
            project_id,
            receipt,
            record_id=event_id.removeprefix("event:"),
            context=context,
            location=location,
        )
        if receipt["decision"] == "allow":
            normalizer_path = Path(__file__).resolve().with_name("llm_call_events.py")
            record = runpy.run_path(str(normalizer_path))["event_from_prompt_receipt"](receipt)
            if record is not None:
                writer["write_event"](
                    "llm-call-events",
                    project_id,
                    record,
                    record_id=str(record["event_id"]).removeprefix("event:"),
                    context=context,
                    location=location,
                )
    except Exception as exc:  # A missing record never changes the prompt decision.
        code = getattr(exc, "code", None)
        return (
            code
            if isinstance(code, str) and re.fullmatch(r"[a-z-]{1,64}", code)
            else ("record-write-failed")
        )
    return None


def prompt_source_ref(project_id: str, event_token: str) -> str:
    return f"record:v1:{project_id}:prompt-ingress:{event_token}"


def prompt_metadata(record: dict[str, Any]) -> dict[str, object]:
    """Project a stored prompt-ingress record to its content-free metadata; never a verdict."""

    body = record.get("body")
    if not isinstance(body, dict) or record.get("kind") != "prompt-ingress":
        raise GuardError("prompt-record-invalid")
    _validate_receipt_for_persistence(body)
    token = record.get("record_id")
    if (
        not isinstance(token, str)
        or body.get("event_id") != f"event:{token}"
        or body.get("project_id") != record.get("project_id")
    ):
        raise GuardError("prompt-record-invalid")
    capture = body["prompt_capture"]
    payload = (json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return {
        "schema_version": "2.0",
        "kind": "PromptIngressMetadata",
        "source_receipt_path": prompt_source_ref(str(body["project_id"]), token),
        "source_receipt_sha256": _sha256(payload),
        "prompt_capture_sha256": capture["sha256"],
        **{
            key: body[key]
            for key in (
                "project_id",
                "client_id",
                "event",
                "event_id",
                "occurred_at",
                "prompt_session_id",
                "prompt_session_id_source",
                "prompt_turn_id",
                "prompt_turn_id_source",
                "decision",
                "outcome",
                "model",
            )
        },
    }


def _validate_receipt_for_persistence(receipt: dict[str, object]) -> None:
    if (
        receipt.get("schema_version") != "2.0"
        or receipt.get("kind") != "PromptIngressReceipt"
        or receipt.get("phase") != "sanitized-user-prompt-audit-phase-1"
        or receipt.get("capture_scope") != "user-prompt-text-only"
        or receipt.get("raw_sensitive_content_recorded") is not False
        or receipt.get("excluded_content_recorded") is not False
        or PROHIBITED_RECEIPT_KEYS.intersection(receipt)
    ):
        raise GuardError("receipt-invalid")

    try:
        _event_normalizer()["validate_model"](receipt.get("model"))
    except Exception:
        raise GuardError("receipt-invalid") from None

    capture = receipt.get("prompt_capture")
    detector_counts = receipt.get("detector_counts")
    if (
        not isinstance(capture, dict)
        or set(capture) != PROMPT_CAPTURE_KEYS
        or not isinstance(detector_counts, list)
    ):
        raise GuardError("receipt-invalid")
    for detector_count in detector_counts:
        if (
            not isinstance(detector_count, dict)
            or set(detector_count) != {"detector_id", "class", "count"}
            or detector_count.get("class") not in DETECTOR_CLASSES
            or not isinstance(detector_count.get("count"), int)
            or isinstance(detector_count.get("count"), bool)
            or int(detector_count["count"]) < 1
        ):
            raise GuardError("receipt-invalid")

    outcome = receipt.get("outcome")
    decision = receipt.get("decision")
    mode = capture.get("mode")
    text = capture.get("text")
    digest = capture.get("sha256")
    strategy = capture.get("redaction_strategy")
    count = capture.get("redaction_count")
    classes = capture.get("redacted_classes")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or not isinstance(classes, list)
        or classes != sorted(set(classes))
        or any(item not in DETECTOR_CLASSES for item in classes)
    ):
        raise GuardError("receipt-invalid")

    if isinstance(text, str):
        if digest != _sha256(text.encode("utf-8")):
            raise GuardError("receipt-invalid")
    elif text is not None or digest is not None:
        raise GuardError("receipt-invalid")

    if outcome == "clean":
        valid = (
            decision == "allow"
            and detector_counts == []
            and mode == "clean-exact"
            and isinstance(text, str)
            and strategy == "none"
            and count == 0
            and classes == []
        )
    elif outcome == "matched":
        detector_classes = sorted(
            {str(item["class"]) for item in detector_counts if isinstance(item, dict)}
        )
        common_valid = (
            decision == "block"
            and bool(detector_counts)
            and isinstance(text, str)
            and count >= 1
            and bool(classes)
            and classes == detector_classes
        )
        if mode == "sensitive-span-redacted":
            valid = (
                common_valid
                and strategy == "validated-detector-spans-v1"
                and not WHOLE_PROMPT_REDACTION_CLASSES.intersection(classes)
            )
        elif mode == "sensitive-whole-prompt-redacted":
            valid = (
                common_valid
                and text == "[REDACTED:high-risk-prompt]"
                and strategy == "whole-prompt-redacted-v1"
                and count == 1
                and bool(WHOLE_PROMPT_REDACTION_CLASSES.intersection(classes))
            )
        else:
            valid = False
    elif outcome in {"input-invalid", "guard-error"}:
        valid = (
            decision == "block"
            and detector_counts == []
            and mode == "unavailable"
            and text is None
            and digest is None
            and strategy == "none"
            and count == 0
            and classes == []
        )
    else:
        valid = False
    if not valid:
        raise GuardError("receipt-invalid")


def _receipt(
    *,
    client_id: str,
    policy: dict[str, Any] | None,
    policy_digest: str | None,
    decision: str,
    outcome: str,
    prompt_capture: dict[str, object],
    detector_counts: list[dict[str, object]],
    invocation_context: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "kind": "PromptIngressReceipt",
        "phase": "sanitized-user-prompt-audit-phase-1",
        **invocation_context,
        "client_id": client_id,
        "event": _event_name(client_id),
        "decision": decision,
        "outcome": outcome,
        "policy_availability": "available" if policy is not None else "unavailable",
        "policy_version": policy["metadata"]["version"] if policy is not None else None,
        "policy_sha256": policy_digest,
        "capture_scope": "user-prompt-text-only",
        "prompt_capture": prompt_capture,
        "detector_counts": detector_counts,
        "raw_sensitive_content_recorded": False,
        "excluded_content_recorded": False,
    }


_WARNINGS: list[str | None] = []


def _record_context(project_root: Path) -> tuple[str, dict[str, Any], str] | None:
    """Project identity and state policy only label the record; they never decide the prompt."""
    try:
        project_id = _read_project_id(project_root)
        state_policy, state_policy_digest = _read_state_policy(project_root)
    except GuardError as exc:
        code = str(exc)
        _WARNINGS.append(code if re.fullmatch(r"[a-z-]{1,64}", code) else "record-context-invalid")
        return None
    return project_id, state_policy, state_policy_digest


def _finish(
    client_id: str,
    context: tuple[str, dict[str, Any], str] | None,
    event: dict[str, Any] | None,
    *,
    policy: dict[str, Any] | None,
    policy_digest: str | None,
    outcome: str,
    prompt_capture: dict[str, object],
    detector_counts: list[dict[str, object]],
    message: str = SAFE_BLOCK_MESSAGE,
) -> tuple[dict[str, object], dict[str, object] | None]:
    blocked = outcome != "clean"
    receipt: dict[str, object] | None = None
    if context is not None:
        project_id, state_policy, state_policy_digest = context
        receipt = _receipt(
            client_id=client_id,
            policy=policy,
            policy_digest=policy_digest,
            decision="block" if blocked else "allow",
            outcome=outcome,
            prompt_capture=prompt_capture,
            detector_counts=detector_counts,
            invocation_context=_invocation_context(
                client_id,
                event,
                project_id=project_id,
                state_policy=state_policy,
                state_policy_digest=state_policy_digest,
            ),
        )
        _WARNINGS.append(_write_receipt(receipt))
    return _decision_output(client_id, blocked, message=message), receipt


def _run(client_id: str) -> tuple[dict[str, object], dict[str, object] | None]:
    script_path = Path(__file__)
    if script_path.is_symlink():
        raise GuardError("script-symlink-rejected")
    project_root = script_path.resolve(strict=True).parents[2]
    context = _record_context(project_root)
    unavailable = _unavailable_prompt_capture()
    try:
        policy, policy_digest = _read_policy(project_root)
    except GuardError:
        _, event = _read_event(FALLBACK_MAX_EVENT_BYTES)
        return _finish(
            client_id,
            context,
            event,
            policy=None,
            policy_digest=None,
            outcome="guard-error",
            prompt_capture=unavailable,
            detector_counts=[],
            message=SAFE_ERROR_MESSAGE,
        )
    _, event = _read_event(policy["limits"]["max_event_bytes"])
    expected_event = _event_name(client_id)
    supplied_event = event.get("hook_event_name") if event is not None else None
    if client_id == "cursor":
        event_name_valid = supplied_event in {None, "beforeSubmitPrompt"}
    else:
        event_name_valid = supplied_event == expected_event
    prompt = event.get("prompt") if event is not None else None
    if (
        event is None
        or not event_name_valid
        or not isinstance(prompt, str)
        or "\x00" in prompt
        or len(prompt.encode("utf-8")) > policy["limits"]["max_prompt_bytes"]
    ):
        return _finish(
            client_id,
            context,
            event,
            policy=policy,
            policy_digest=policy_digest,
            outcome="input-invalid",
            prompt_capture=unavailable,
            detector_counts=[],
        )
    try:
        counts, spans = _scan(prompt, policy)
        prompt_capture = _prompt_capture(prompt, spans, policy)
    except GuardError:
        return _finish(
            client_id,
            context,
            event,
            policy=policy,
            policy_digest=policy_digest,
            outcome="guard-error",
            prompt_capture=unavailable,
            detector_counts=[],
            message=SAFE_ERROR_MESSAGE,
        )
    return _finish(
        client_id,
        context,
        event,
        policy=policy,
        policy_digest=policy_digest,
        outcome="matched" if counts else "clean",
        prompt_capture=prompt_capture,
        detector_counts=counts,
    )


def _interpreter_status() -> str | None:
    """Move to the project's profile Python; a remaining mismatch stops the prompt."""
    script = Path(__file__)
    try:
        status: str | None = _records()["ensure_profile_interpreter"](
            script.resolve(strict=True).parents[2], script, sys.argv[1:]
        )
    except Exception:
        return "python-runtime-mismatch"
    return status


def _repair_command() -> str:
    """The distributed `.venv` preparation command pinned to the profile's Python."""
    try:
        records = _records()
        required = records["profile_python_version"](Path(__file__).resolve().parents[2])
        if isinstance(required, str):
            return str(records["repair_command"](required))
    except Exception:
        pass
    # Without a readable profile the script itself reports which Python it needs.
    return "python3 .kt-scaffold/hooks/python_environment.py hazirla"


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--client", choices=CLIENTS, required=True)
    arguments = parser.parse_args()
    if _interpreter_status() is not None:
        with contextlib.suppress(OSError):
            sys.stdin.buffer.read(FALLBACK_MAX_EVENT_BYTES + 1)
        output = _decision_output(
            arguments.client, True, message=INTERPRETER_MESSAGE.format(command=_repair_command())
        )
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        return 0
    try:
        output, _receipt_payload = _run(arguments.client)
    except Exception as exc:  # The hook must never disclose input or policy internals.
        with contextlib.suppress(OSError):
            sys.stdin.buffer.read(FALLBACK_MAX_EVENT_BYTES + 1)
        output = _decision_output(arguments.client, True, message=_error_message(exc))
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    for code in dict.fromkeys(code for code in _WARNINGS if code is not None):
        print(RECORD_WARNING.format(code=code), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
