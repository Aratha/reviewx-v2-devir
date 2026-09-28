#!/usr/bin/env python3
"""Dependency-free governance commands over the shared, repository-free governance root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import secrets
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn, cast

# Started with the host's python3 before moving to the project's `.venv`; keep 3.9 syntax.
UTC = timezone.utc  # noqa: UP017
MAX_REQUEST_BYTES = 16 * 1024 * 1024 + 4096
PROMPT_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "source_receipt_path",
        "source_receipt_sha256",
        "prompt_capture_sha256",
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
    }
)
CLIENT_SESSION_ENVIRONMENT = {
    "claude-code": ("CLAUDE_CODE_SESSION_ID",),
    "codex": ("CODEX_SESSION_ID", "CODEX_THREAD_ID"),
    "cursor": ("CURSOR_SESSION_ID", "CURSOR_CONVERSATION_ID"),
    "github-copilot-vscode": ("VSCODE_SESSION_ID",),
}
# Codex runs a project hook only after the user trusts its exact definition. Project creation and
# a hook-changing update record that trust; a copied project or an edited hook file needs the
# user's own step on the VS Code extension's Hooks settings page, which has no `/hooks` command.
PROMPT_HOOK_TRUST_GUIDANCE = {
    "codex": (
        "Codex bu projenin kancalarını (mesaj gönderince kendiliğinden çalışan denetimler) büyük "
        "olasılıkla onaylı bulmadığı için çalıştırmadı. Proje bu bilgisayarda proje fabrikasıyla "
        "oluşturulduysa veya güncellendiyse onay kendiliğinden yazılmıştır; bu projede yeni bir "
        "sohbet açıp isteğinizi orada gönderin. Proje başka yerden kopyalandıysa ya da kancalar "
        "sonradan değiştiyse onayı bir kez siz verin: VS Code'da Codex kenar çubuğundaki dişli "
        "simgesinden Codex Settings'i açın; Hooks bölümünde bu projenin kancalarını tek tek Trust "
        "ile onaylayın. Liste boşsa önce bu projede bir sohbet açın, sonra Reload hooks'a basın. "
        "Onaydan sonra isteğinizi yeni bir mesajla gönderin."
    ),
}
PROJECT_ID_RE = re.compile(r"project-(?!0{32}$)[0-9a-f]{32}")
SESSION_ID_RE = re.compile(r"session:client\.[0-9a-f]{64}")
TURN_ID_RE = re.compile(r"turn:(?:client\.[0-9a-f]{64}|local\.(?!0{32}$)[0-9a-f]{32})")
EVENT_ID_RE = re.compile(r"event:(?!0{32}$)[0-9a-f]{32}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
MAX_PROMPT_METADATA_BYTES = 16 * 1024
MAX_PROMPT_METADATA_FILES = 512
MAX_REVIEW_ARTIFACT_BYTES = 16 * 1024 * 1024
# Mirrors policies/aggregation/governed-review.yml#security_critical_veto; a factory parity
# test binds both.  A covered Agent's accepted critical finding removes PASS whatever the
# weighted score is.
SECURITY_CRITICAL_VETO_AGENTS = frozenset(
    {"agent:bilgi-guvenligi", "agent:uygulama-guvenligi", "agent:gizlilik-kvkk"}
)
RUN_ID_RE = re.compile(r"run-[A-Za-z0-9][A-Za-z0-9._-]{3,119}")
AGENT_SLUG_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
# The only observation fields a specialist evaluates; every other field comes from the run's
# bindings input, so no Agent transcribes identifiers or digests.
EVALUATED_FIELDS = (
    "agent_id",
    "error_code",
    "error_summary",
    "findings",
    "scanned_files",
    "status",
)
GUARD_REASON_RE = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
# One `standard_refs` entry of an Agent policy pack; the only controls a finding may cite.
POLICY_STANDARD_REF_RE = re.compile(
    r"^\s*- standard_id: \"?([^\s\"]+)\"?\n"
    r"\s+control_id: \"?([^\s\"]+)\"?\n"
    r"\s+version: \"?([^\s\"]+)\"?$",
    re.MULTILINE,
)
GIT_TIMEOUT_SECONDS = 30
MAX_JSON_BYTES = 4 * 1024 * 1024
CLIENT_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
TEST_AUTOMATION_AGENT = "agent:test-otomasyonu"
RUN_CONTEXT_CANONICALIZATION = "kt-governed-review-run-context-json-v1"
RULE_PATH = "rules/13-tamamlanma-tanimi.md"
ORCHESTRATION_PATH = "agent-platform/orchestrations/governed-review.yml"
AGGREGATION_POLICY_PATH = "agent-platform/policies/aggregation/governed-review.yml"
AGGREGATION_INSTRUCTIONS_PATH = (
    "agent-platform/policies/aggregation/governed-review-instructions.md"
)
EVALUATOR_POLICY_PATH = "agent-platform/policies/aggregation/governed-review-agentic-evaluation.yml"
EXPLANATION_TEMPLATES_PATH = (
    "agent-platform/policies/aggregation/decision-explanation-templates.yml"
)


class GovernanceClientError(ValueError):
    """A fixed public error code, never a filesystem path or raw exception text."""

    def __init__(
        self,
        code: str,
        *,
        reason_code: str | None = None,
        violation: dict[str, object] | None = None,
        guidance: str | None = None,
    ) -> None:
        super().__init__(code)
        self.reason_code = (
            reason_code
            if reason_code is not None and GUARD_REASON_RE.fullmatch(reason_code)
            else None
        )
        self.violation = violation
        # A fixed hook remedy for the reason code, such as the draft PRD version line.
        self.guidance = guidance or None


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise GovernanceClientError("invalid-request")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise GovernanceClientError("invalid-request")
        result[key] = value
    return result


def _invalid_constant(_: str) -> object:
    raise GovernanceClientError("invalid-request")


def _decode(payload: bytes) -> Any:
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (ValueError, UnicodeError, RecursionError):
        raise GovernanceClientError("invalid-request") from None


def preflight() -> dict[str, object]:
    """Report the shared root and interpreter readiness; read and write no record."""
    try:
        result = _hook_module("governance_records.py")["preflight"](Path.cwd(), _record_location())
    except Exception:
        return {"ok": False, "root_status": "record-writer-unavailable"}
    return cast(dict[str, object], result)


def record_consultation(raw: bytes) -> dict[str, object]:
    """Store one advisory single-agent consultation; it never carries a decision or permission."""

    if len(raw) > MAX_REQUEST_BYTES:
        raise GovernanceClientError("request-too-large")
    project_root = Path.cwd().resolve(strict=True)
    record = _decode(raw)
    guard = _hook_module("agentic_review_receipt_guard.py")
    try:
        guard["_validate_against_schema"](
            record,
            "agentic-agent-consultation.schema.json",
            guard["_schema_registry"](project_root),
        )
    except Exception:
        raise GovernanceClientError("consultation-invalid") from None
    if not isinstance(record, dict) or record.get("project_id") != _project_id(project_root):
        raise GovernanceClientError("consultation-invalid")
    writer = _hook_module("governance_records.py")
    try:
        path = writer["write_event"](
            "agent-consultation",
            record["project_id"],
            record,
            context={"client_source": "command"},
            location=_record_location(),
        )
    except writer["RecordError"]:
        raise GovernanceClientError("consultation-unrecorded") from None
    return {"status": "recorded", "record_id": Path(path).stem, "commit_authority": False}


def _read_regular_json(path: Path, *, maximum: int) -> dict[str, object]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_size > maximum
            ):
                raise GovernanceClientError("prompt-metadata-invalid")
            raw = handle.read(maximum + 1)
        value = _decode(raw)
    except GovernanceClientError:
        raise
    except OSError:
        raise GovernanceClientError("prompt-metadata-invalid") from None
    if not isinstance(value, dict):
        raise GovernanceClientError("prompt-metadata-invalid")
    return value


def _canonical_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise GovernanceClientError("review-artifact-invalid") from None


def _canonical_sha256(value: object, *, excluding: str | None = None) -> str:
    if excluding is not None:
        if not isinstance(value, dict) or excluding not in value:
            raise GovernanceClientError("review-artifact-invalid")
        value = {key: item for key, item in value.items() if key != excluding}
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _read_review_json(path: Path) -> tuple[bytes, dict[str, object]]:
    try:
        if path.is_symlink():
            raise GovernanceClientError("review-artifact-invalid")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_size > MAX_REVIEW_ARTIFACT_BYTES
            ):
                raise GovernanceClientError("review-artifact-invalid")
            raw = handle.read(MAX_REVIEW_ARTIFACT_BYTES + 1)
        value = _decode(raw)
    except GovernanceClientError:
        raise
    except OSError:
        raise GovernanceClientError("review-artifact-invalid") from None
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise GovernanceClientError("review-artifact-invalid")
    return raw, value


def _utc_second(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GovernanceClientError("review-artifact-invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise GovernanceClientError("review-artifact-invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise GovernanceClientError("review-artifact-invalid")
    return parsed


def _mtime_second(path: Path) -> datetime:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        raise GovernanceClientError("review-artifact-invalid") from None
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise GovernanceClientError("review-artifact-invalid")
    return datetime.fromtimestamp(info.st_mtime_ns // 1_000_000_000, UTC)


def _iso_utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _review_event(
    *,
    receipt: dict[str, object],
    decision: dict[str, object],
    position: int,
    observed_at: datetime,
    previous_sha256: str,
    result: dict[str, object] | None,
) -> dict[str, object]:
    execution = receipt.get("execution")
    evidence = receipt.get("decision_evidence")
    snapshot = receipt.get("snapshot")
    if not all(isinstance(value, dict) for value in (execution, evidence, snapshot)):
        raise GovernanceClientError("review-artifact-invalid")
    client = execution.get("client")
    audit_replay = evidence.get("audit_replay")
    if not isinstance(client, dict) or not isinstance(audit_replay, dict):
        raise GovernanceClientError("review-artifact-invalid")
    prompt_binding = audit_replay.get("prompt_binding")
    if not isinstance(prompt_binding, dict) or not isinstance(prompt_binding.get("envelope"), dict):
        raise GovernanceClientError("review-artifact-invalid")
    envelope = prompt_binding["envelope"]
    if not isinstance(envelope, dict):
        raise GovernanceClientError("review-artifact-invalid")
    if position == 0:
        event_name, reason_code = "review_started", "REVIEW_STARTED"
    elif position == 13:
        reasons = decision.get("reason_codes")
        if not isinstance(reasons, list) or not reasons or not isinstance(reasons[0], str):
            raise GovernanceClientError("review-artifact-invalid")
        event_name, reason_code = "review_completed", reasons[0]
    else:
        event_name, reason_code = "agent_completed", "AGENT_OK"
    event: dict[str, object] = {
        "schema_version": "1.1",
        "kind": "AgenticGovernedReviewAuditEvent",
        "evidence_profile": "phase1-agentic-advisory",
        "receipt_id": receipt.get("receipt_id"),
        "project_id": receipt.get("project_id"),
        "client_id": client.get("id"),
        "prompt_session_id": execution.get("session_id"),
        "prompt_turn_id": envelope.get("source_prompt_turn_id"),
        "event": event_name,
        "chain_position": position,
        "event_canonicalization": "kt-agentic-review-audit-event-json-v1",
        "run_id": receipt.get("run_id"),
        "trace_id": receipt.get("trace_id"),
        "span_id": (
            decision.get("span_id")
            if position == 13
            else result.get("span_id")
            if result is not None
            else receipt.get("trace_id", "")[:16]
        ),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "agentic_evaluator": receipt.get("agentic_evaluator"),
        "agent_id": result.get("agent_id") if result is not None else None,
        "invocation_id": result.get("invocation_id") if result is not None else None,
        "status": result.get("status") if result is not None else None,
        "decision": decision.get("decision") if position == 13 else None,
        "reason_code": reason_code,
        "report_sha256": result.get("report_sha256") if result is not None else None,
        "decision_sha256": receipt.get("decision_sha256") if position == 13 else None,
        "decision_evidence_sha256": evidence.get("evidence_sha256"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "previous_event_sha256": previous_sha256,
        "event_sha256": "0" * 64,
        "native_result": None,
        "claim_boundary": {
            "immutable_audit": False,
            "otel_exported": False,
            "production_authority": False,
            "native_hook_result_recorded": False,
            "commit_retry_recorded": False,
        },
        "data_handling": {
            "raw_prompt_stored": False,
            "source_content_stored": False,
            "pii_stored": False,
            "secret_stored": False,
        },
        "observed_at": _iso_utc(observed_at),
    }
    event["event_sha256"] = _canonical_sha256(event, excluding="event_sha256")
    return event


def _build_review_audit_events(
    run_root: Path,
    receipt_path: Path,
    receipt: dict[str, object],
    decision_raw: bytes,
    decision: dict[str, object],
) -> list[dict[str, object]]:
    if (
        receipt.get("decision") != "PASS"
        or decision.get("decision") != "PASS"
        or receipt.get("run_id") != run_root.name
        or receipt.get("decision_sha256") != hashlib.sha256(decision_raw).hexdigest()
        or receipt.get("receipt_sha256") != _canonical_sha256(receipt, excluding="receipt_sha256")
    ):
        raise GovernanceClientError("review-artifact-invalid")
    results = receipt.get("agent_results")
    evidence = receipt.get("decision_evidence")
    if not isinstance(results, list) or len(results) != 12 or not isinstance(evidence, dict):
        raise GovernanceClientError("review-artifact-invalid")
    audit_replay = evidence.get("audit_replay")
    if not isinstance(audit_replay, dict) or not isinstance(
        audit_replay.get("primary_evaluation"), dict
    ):
        raise GovernanceClientError("review-artifact-invalid")
    primary_started = _utc_second(audit_replay["primary_evaluation"].get("started_at"))
    timed_results: list[tuple[datetime, str, dict[str, object]]] = []
    report_root = run_root / "reports"
    for item in results:
        if not isinstance(item, dict) or not isinstance(item.get("agent_id"), str):
            raise GovernanceClientError("review-artifact-invalid")
        slug = item["agent_id"].removeprefix("agent:")
        expected_relative = f"governed-review/{run_root.name}/reports/{slug}.json"
        if item.get("report_path") != expected_relative or item.get("status") != "ok":
            raise GovernanceClientError("review-artifact-invalid")
        report_path = report_root / f"{slug}.json"
        report_raw, _ = _read_review_json(report_path)
        if item.get("report_sha256") != hashlib.sha256(report_raw).hexdigest():
            raise GovernanceClientError("review-artifact-invalid")
        timed_results.append((_mtime_second(report_path), item["agent_id"], item))
    timed_results.sort(key=lambda item: (item[0], item[1]))
    if timed_results[-1][0] > primary_started:
        raise GovernanceClientError("artifact-chronology-invalid")
    receipt_created = _utc_second(receipt.get("created_at"))
    completed = _mtime_second(receipt_path)
    if completed < receipt_created or completed > datetime.now(UTC):
        raise GovernanceClientError("artifact-chronology-invalid")
    previous = str(receipt["receipt_sha256"])
    events = [
        _review_event(
            receipt=receipt,
            decision=decision,
            position=0,
            observed_at=timed_results[0][0],
            previous_sha256=previous,
            result=None,
        )
    ]
    previous = str(events[-1]["event_sha256"])
    for position, (observed_at, _agent_id, result) in enumerate(timed_results, start=1):
        event = _review_event(
            receipt=receipt,
            decision=decision,
            position=position,
            observed_at=observed_at,
            previous_sha256=previous,
            result=result,
        )
        events.append(event)
        previous = str(event["event_sha256"])
    events.append(
        _review_event(
            receipt=receipt,
            decision=decision,
            position=13,
            observed_at=completed,
            previous_sha256=previous,
            result=None,
        )
    )
    return events


def _review_run(project_root: Path, run_id: str) -> tuple[str, Path]:
    if RUN_ID_RE.fullmatch(run_id) is None:
        raise GovernanceClientError("invalid-request")
    project_id = _project_id(project_root)
    writer = _hook_module("governance_records.py")
    try:
        run_root = writer["review_area"](project_id, location=_record_location()) / run_id
    except writer["RecordError"]:
        raise GovernanceClientError("review-artifact-invalid") from None
    if run_root.is_symlink() or not run_root.is_dir():
        raise GovernanceClientError("review-artifact-invalid")
    return project_id, run_root


def _read_run_input(path: Path) -> dict[str, object]:
    """One run input or evaluation: a regular, unlinked JSON object owned by this user."""

    try:
        if path.is_symlink():
            raise GovernanceClientError("review-artifact-invalid")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
                or info.st_size > MAX_REVIEW_ARTIFACT_BYTES
            ):
                raise GovernanceClientError("review-artifact-invalid")
            raw = handle.read(MAX_REVIEW_ARTIFACT_BYTES + 1)
    except GovernanceClientError:
        raise
    except OSError:
        raise GovernanceClientError("review-artifact-invalid") from None
    value = _decode(raw)
    if not isinstance(value, dict):
        raise GovernanceClientError("review-artifact-invalid")
    return value


def _policy_controls(project_root: Path, agent: str) -> set[tuple[str, str, str]]:
    """The `{standard_id, control_id, version}` triples the Agent's policy pack declares."""

    path = project_root / "agent-platform" / "agents" / agent / "policy.yml"
    try:
        if path.is_symlink() or not path.is_file():
            raise GovernanceClientError("evaluation-invalid", reason_code="POLICY_UNAVAILABLE")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise GovernanceClientError(
            "evaluation-invalid", reason_code="POLICY_UNAVAILABLE"
        ) from None
    return {match.groups() for match in POLICY_STANDARD_REF_RE.finditer(text)}


def _staged_paths(project_root: Path, error: str = "evaluation-invalid") -> set[str]:
    """Repository-relative paths the staged candidate adds, changes or deletes."""

    executable = shutil.which("git")
    if executable is None:
        raise GovernanceClientError(error, reason_code="CANDIDATE_UNAVAILABLE")
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            [
                executable,
                "-C",
                str(project_root),
                "diff",
                "--cached",
                "--name-only",
                "--no-renames",
                "-z",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=environment,
        )
        if completed.returncode != 0:
            raise GovernanceClientError(error, reason_code="CANDIDATE_UNAVAILABLE")
        return {item for item in completed.stdout.decode("utf-8").split("\0") if item}
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise GovernanceClientError(error, reason_code="CANDIDATE_UNAVAILABLE") from None


def _validate_evaluation_scope(
    project_root: Path, agent: str, evaluation: dict[str, object]
) -> None:
    """Mechanically bind a specialist answer to its policy controls and the staged candidate.

    A rejected answer writes no report, so the main Agent asks the same specialist again with
    the returned reason instead of repeating the whole review.
    """

    findings = evaluation.get("findings")
    scanned = evaluation.get("scanned_files")
    if not isinstance(findings, list) or not isinstance(scanned, list):
        raise GovernanceClientError("evaluation-invalid")
    if findings:
        allowed = _policy_controls(project_root, agent)
        for finding in findings:
            controls = finding.get("controls") if isinstance(finding, dict) else None
            if not isinstance(controls, list) or any(
                not isinstance(control, dict)
                or (
                    str(control.get("standard_id")),
                    str(control.get("control_id")),
                    str(control.get("version")),
                )
                not in allowed
                for control in controls
            ):
                raise GovernanceClientError(
                    "evaluation-invalid", reason_code="CONTROL_NOT_IN_POLICY"
                )
    if scanned:
        candidate = _staged_paths(project_root)
        if any(path not in candidate for path in scanned):
            raise GovernanceClientError("evaluation-invalid", reason_code="SCANNED_FILE_NOT_STAGED")
    covered = set(scanned)
    for finding in findings:
        locations = finding.get("locations") if isinstance(finding, dict) else None
        if isinstance(locations, list) and any(
            isinstance(location, dict) and location.get("path") not in covered
            for location in locations
        ):
            raise GovernanceClientError("evaluation-invalid", reason_code="LOCATION_NOT_SCANNED")


def record_observation(run_id: str, agent: str) -> dict[str, object]:
    """Write one specialist report from its bindings input and its returned evaluation.

    The specialist evaluates; this command copies every identifier and digest byte for byte
    from the bindings input `review-start` wrote. A rejected evaluation writes no report; a
    schema violation names its JSON pointer, keyword and schema constraint so the main Agent
    can return it to the same specialist once.
    """

    if AGENT_SLUG_RE.fullmatch(agent) is None:
        raise GovernanceClientError("invalid-request")
    project_root = Path.cwd().resolve(strict=True)
    project_id, run_root = _review_run(project_root, run_id)
    guard = _hook_module("agentic_review_receipt_guard.py")
    agent_id = f"agent:{agent}"
    if agent_id not in guard["AGENTS"]:
        raise GovernanceClientError("invalid-request")
    bindings = _read_run_input(run_root / "inputs" / f"{agent}.bindings.json")
    evaluation = _read_run_input(run_root / "work" / f"{agent}-evaluation.json")
    missing = sorted(set(EVALUATED_FIELDS) - set(evaluation))
    unexpected = sorted(set(evaluation) - set(EVALUATED_FIELDS))
    if missing or unexpected:
        raise GovernanceClientError(
            "evaluation-invalid",
            reason_code="EVALUATION_SCHEMA_INVALID",
            violation={
                "pointer": "",
                "keyword": "required" if missing else "additionalProperties",
                "constraint": missing or unexpected,
            },
        )
    if evaluation.get("agent_id") != agent_id:
        raise GovernanceClientError("evaluation-invalid")
    bound_fields = set(guard["OBSERVATION_KEYS"]) - set(EVALUATED_FIELDS) | {"agent_id"}
    if (
        set(bindings) != bound_fields
        or bindings.get("agent_id") != agent_id
        or bindings.get("run_id") != run_id
        or bindings.get("project_id") != project_id
    ):
        raise GovernanceClientError("bindings-invalid")
    schemas = guard["_schema_registry"](project_root)
    schema = "agentic-governance-observation.schema.json"
    # A clean evaluation separates a bindings fault from the specialist's answer, which only the
    # specialist corrects.
    clean = {
        "agent_id": agent_id,
        "error_code": None,
        "error_summary": None,
        "findings": [],
        "scanned_files": [],
        "status": "ok",
    }
    try:
        guard["_validate_against_schema"]({**bindings, **clean}, schema, schemas)
    except Exception:
        raise GovernanceClientError("bindings-invalid") from None
    observation = {**bindings, **evaluation}
    try:
        guard["_validate_against_schema"](observation, schema, schemas)
    except Exception:
        raise GovernanceClientError(
            "evaluation-invalid",
            reason_code="EVALUATION_SCHEMA_INVALID",
            violation=guard["schema_violation"](observation, schema, schemas),
        ) from None
    _validate_evaluation_scope(project_root, agent, evaluation)
    payload = _canonical_bytes(observation)
    writer = _hook_module("governance_records.py")
    try:
        path, created = writer["write_review_report"](
            project_id, run_id, agent, payload, location=_record_location()
        )
    except writer["RecordError"]:
        raise GovernanceClientError("report-write-failed") from None
    if not created and _read_review_json(path)[0] != payload:
        raise GovernanceClientError("report-exists")
    findings = observation["findings"]
    return {
        "agent_id": agent_id,
        "finding_count": len(findings) if isinstance(findings, list) else 0,
        "report": "written" if created else "reused",
        "report_path": f"governed-review/{run_id}/reports/{agent}.json",
        "report_sha256": hashlib.sha256(payload).hexdigest(),
        "status": observation["status"],
    }


def _policy_standard_refs(project_root: Path, agent: str) -> list[dict[str, str]]:
    """The Agent's policy controls in file order, as a specialist invocation must cite them."""

    path = project_root / "agent-platform" / "agents" / agent / "policy.yml"
    try:
        if path.is_symlink() or not path.is_file():
            raise GovernanceClientError("review-start-invalid", reason_code="POLICY_UNAVAILABLE")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise GovernanceClientError(
            "review-start-invalid", reason_code="POLICY_UNAVAILABLE"
        ) from None
    references: list[dict[str, str]] = []
    for standard_id, control_id, version in POLICY_STANDARD_REF_RE.findall(text):
        reference = {"standard_id": standard_id, "control_id": control_id, "version": version}
        if reference not in references:
            references.append(reference)
    return references


def _component_bindings(
    project_root: Path, guard: dict[str, Any], client_id: str
) -> dict[str, Any]:
    """Every authority, policy, harness and Agent binding of a run, read from the project files."""

    def read(relative: str) -> bytes:
        return cast(bytes, guard["_regular_file"](project_root, relative, limit=MAX_JSON_BYTES)[1])

    def digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    version = guard["_yaml_metadata_version"]
    mapping = guard["_yaml_direct_mapping"]
    manifest_raw = read(".kt-scaffold/project-manifest.json")
    manifest = _decode(manifest_raw)
    if not isinstance(manifest, dict):
        raise GovernanceClientError("review-start-invalid", reason_code="PROJECT_MANIFEST_INVALID")
    orchestration_raw = read(ORCHESTRATION_PATH)
    aggregation_raw = read(AGGREGATION_POLICY_PATH)
    evaluator_raw = read(EVALUATOR_POLICY_PATH)
    lineage = mapping(aggregation_raw, "lineage")
    evaluation = mapping(evaluator_raw, "evaluation")
    evaluator_metadata = mapping(evaluator_raw, "metadata")
    blueprint_version = manifest.get("blueprint_version")
    harness: dict[str, Any] = {
        "protocol_id": "protocol:mandatory-governed-execution-phase1",
        "version": "1.3.0",
        "canonicalization": "kt-mandatory-governed-execution-json-v1",
        "sha256": "",
        "mandatory": True,
        "rule": {
            "ref": RULE_PATH,
            "version_source": "project-manifest.blueprint_version",
            "version": blueprint_version,
            "sha256": digest(read(RULE_PATH)),
        },
        "skill": {
            "ref": guard["CLIENT_SKILLS"][client_id],
            "version_source": "project-manifest.blueprint_version",
            "version": blueprint_version,
            "sha256": digest(read(guard["CLIENT_SKILLS"][client_id])),
        },
        "stage_order": list(guard["STAGE_ORDER"]),
        "missing_or_stale_result": "BLOCKED_INCOMPLETE",
    }
    harness["sha256"] = _canonical_sha256(harness, excluding="sha256")
    agents: dict[str, Any] = {}
    for agent_id in guard["AGENTS"]:
        slug = agent_id.removeprefix("agent:")
        component: dict[str, Any] = {}
        for name, filename in (
            ("agent", "agent.yml"),
            ("policy", "policy.yml"),
            ("detectors", "detectors.yml"),
            ("instructions", "instructions.md"),
        ):
            raw = read(f"agent-platform/agents/{slug}/{filename}")
            component[name] = {
                "version": "unavailable" if name == "instructions" else version(raw),
                "sha256": digest(raw),
            }
        projection_path = guard["CLIENT_PROJECTION_PATHS"][client_id].format(agent=slug)
        component["projection"] = {
            "client_id": client_id,
            "path": projection_path,
            "version": "unavailable",
            "sha256": digest(read(projection_path)),
        }
        agents[agent_id] = component
    return {
        "authority": {
            "authority_generation": manifest.get("authority_generation"),
            "version": manifest.get("governance_version"),
            "sha256": manifest.get("governance_digest"),
            "manifest_sha256": digest(manifest_raw),
        },
        "orchestration": {
            "ref": "orchestration:governed-review",
            "version": version(orchestration_raw),
            "sha256": digest(orchestration_raw),
            "required_agents": list(guard["AGENTS"]),
            "separate_invocations_observed": True,
        },
        "aggregation_policy": {
            "ref": "policy:governed-review-aggregation",
            "version": version(aggregation_raw),
            "sha256": digest(aggregation_raw),
            "instructions_ref": guard["_yaml_top_level_scalar"](
                aggregation_raw, "instructions_ref"
            ),
            "instructions_sha256": digest(read(AGGREGATION_INSTRUCTIONS_PATH)),
            "weights": mapping(aggregation_raw, "weights"),
            "thresholds": mapping(aggregation_raw, "thresholds"),
            "calibration_status": lineage.get("calibration_status"),
            "runtime_admission": lineage.get("runtime_admission"),
        },
        "agentic_evaluator": {
            "policy_ref": evaluator_metadata.get("id"),
            "evaluator_id": evaluator_metadata.get("evaluator_id"),
            "version": version(evaluator_raw),
            "sha256": digest(evaluator_raw),
            "mode": evaluation.get("mode"),
            "authority": evaluation.get("authority"),
            "runtime_admission": False,
            "deterministic": False,
            "production_authority": False,
        },
        "mandatory_governed_execution": harness,
        "agents": agents,
        "severity_scores": guard["severity_scores"](aggregation_raw),
        "hard_fail_detectors": {
            agent_id: guard["detector_hard_fail_lists"](
                read(f"agent-platform/agents/{agent_id.removeprefix('agent:')}/detectors.yml")
            )
            for agent_id in guard["AGENTS"]
        },
        "explanations": read(EXPLANATION_TEMPLATES_PATH),
    }


def _observation_bindings(
    context: dict[str, Any], components: dict[str, Any], agent_id: str
) -> dict[str, object]:
    """Every observation field of one specialist report except the six it evaluates."""

    identity = context["agents"][agent_id]
    return {
        "schema_version": "1.1",
        "kind": "AgenticGovernanceObservation",
        "evidence_profile": "phase1-agentic-advisory",
        "receipt_id": context["receipt_id"],
        "project_id": context["project_id"],
        "agent_id": agent_id,
        "run_id": context["run_id"],
        "trace_id": context["trace_id"],
        "span_id": identity["span_id"],
        "invocation_id": identity["invocation_id"],
        "snapshot_sha256": context["snapshot_sha256"],
        "agentic_evaluator": components["agentic_evaluator"],
        "component_binding": components["agents"][agent_id],
        "acceptance_criteria": (
            context["acceptance_criteria"] if agent_id == TEST_AUTOMATION_AGENT else None
        ),
        "claim_boundary": {
            "deterministic_evidence": False,
            "canonical_conformance": False,
            "runtime_admission": False,
            "production_decision": False,
            "immutable_audit": False,
        },
        "data_handling": _data_handling(),
    }


def _data_handling() -> dict[str, bool]:
    return {
        "raw_prompt_stored": False,
        "source_content_stored": False,
        "pii_stored": False,
        "secret_stored": False,
    }


def _identity(prefix: str, used: set[str]) -> dict[str, str]:
    """A fresh invocation id and a 16-hex span id no other call of the run carries."""

    while True:
        span_id = secrets.token_hex(8)
        if span_id not in used:
            used.add(span_id)
            return {
                "invocation_id": f"invocation:{prefix}:{secrets.token_hex(6)}",
                "span_id": span_id,
            }


def _write_artifact(
    project_id: str, run_id: str, name: str, value: object
) -> tuple[Path, bytes, bool]:
    """Write one canonical run artifact once; an existing one must hold the same bytes."""

    payload = _canonical_bytes(value)
    writer = _hook_module("governance_records.py")
    try:
        path, created = writer["write_review_artifact"](
            project_id, run_id, name, payload, location=_record_location()
        )
    except writer["RecordError"]:
        raise GovernanceClientError("review-artifact-write-failed") from None
    if not created and _read_review_json(path)[0] != payload:
        raise GovernanceClientError("run-conflict")
    return path, payload, created


def review_start(
    run_id: str, client_id: str, client_version: str, criteria_path: str
) -> dict[str, object]:
    """Open or resume a governed-review run: snapshot, run context and twelve bindings inputs.

    The main Agent supplies only what it observes or judges: the running client's version and
    the accepted or draft PRD that frames the Test Automation Agent.  Every identifier, digest,
    binding and the PRD's lifecycle come from the project files, the staged index and the prompt
    record.
    """

    if (
        RUN_ID_RE.fullmatch(run_id) is None
        or client_id not in CLIENT_SESSION_ENVIRONMENT
        or CLIENT_VERSION_RE.fullmatch(client_version) is None
    ):
        raise GovernanceClientError("invalid-request")
    project_root = Path.cwd().resolve(strict=True)
    project_id = _project_id(project_root)
    guard = _hook_module("agentic_review_receipt_guard.py")
    try:
        snapshot = guard["_capture_snapshot"](project_root, "git")
        components = _component_bindings(project_root, guard, client_id)
        criteria = guard["acceptance_criteria"](project_root, criteria_path, "git")
    except guard["GuardError"] as exc:
        raise GovernanceClientError(
            "review-start-invalid", reason_code=exc.code, guidance=exc.diagnostic
        ) from None
    writer = _hook_module("governance_records.py")
    try:
        run_root = writer["prepare_review_run"](project_id, run_id, location=_record_location())
    except writer["RecordError"]:
        raise GovernanceClientError("review-directory-unavailable") from None
    context_path = run_root / "inputs" / "run.json"
    identity = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    if context_path.exists() or context_path.is_symlink():
        _, context = _read_review_json(context_path)
        if (
            context.get("snapshot_sha256") != snapshot["snapshot_sha256"]
            or cast(dict[str, object], context.get("client", {})).get("id") != client_id
            or cast(dict[str, object], context.get("client", {})).get("version") != client_version
            or context.get("acceptance_criteria") != criteria
        ):
            raise GovernanceClientError("run-conflict")
        status = "resumed"
    else:
        metadata = current_prompt_metadata(client_id)
        used: set[str] = set()
        client = {
            "source": "native-event-observed" if client_id == "cursor" else "agent-self-observed",
            "id": client_id,
            "version": client_version,
            "sha256": _canonical_sha256({"id": client_id, "version": client_version}),
        }
        context = {
            "canonicalization": RUN_CONTEXT_CANONICALIZATION,
            "project_id": project_id,
            "run_id": run_id,
            "receipt_id": f"receipt:{run_id}",
            "trace_id": secrets.token_hex(16),
            "started_at": _iso_utc(datetime.now(UTC)),
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "client": client,
            "session_id": metadata["prompt_session_id"],
            "model": metadata["model"],
            "prompt_source_ref": metadata["source_receipt_path"],
            "acceptance_criteria": criteria,
            "evaluator": _identity("evaluator-primary", used),
            "second_pass": _identity("evaluator-second-pass", used),
            "agents": {
                agent_id: _identity(agent_id.removeprefix("agent:"), used)
                for agent_id in guard["AGENTS"]
            },
        }
        status = "started"
    _write_artifact(project_id, run_id, "inputs/snapshot", identity)
    _write_artifact(project_id, run_id, "inputs/run", context)
    schemas = guard["_schema_registry"](project_root)
    agents: list[dict[str, object]] = []
    for agent_id in guard["AGENTS"]:
        slug = agent_id.removeprefix("agent:")
        bindings = _observation_bindings(context, components, agent_id)
        clean = {
            "error_code": None,
            "error_summary": None,
            "findings": [],
            "scanned_files": [],
            "status": "ok",
        }
        try:
            guard["_validate_against_schema"](
                {**bindings, **clean}, "agentic-governance-observation.schema.json", schemas
            )
        except guard["GuardError"]:
            raise GovernanceClientError("bindings-invalid") from None
        path, _, _ = _write_artifact(project_id, run_id, f"inputs/{slug}.bindings", bindings)
        agents.append(
            {
                "agent_id": agent_id,
                "bindings_path": str(path),
                "report": "written"
                if (run_root / "reports" / f"{slug}.json").exists()
                else "missing",
                "standard_refs": _policy_standard_refs(project_root, slug),
            }
        )
    return {
        "status": status,
        "run_id": run_id,
        "review_directory": str(run_root),
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "staged_paths": sorted(_staged_paths(project_root, "review-start-invalid")),
        "acceptance_criteria": criteria,
        "agents": agents,
        "next_action": (
            "finalize-review"
            if all(item["report"] == "written" for item in agents)
            else "dispatch-specialists"
        ),
    }


def _verify_review_run(
    project_root: Path,
    receipt_raw: bytes,
    receipt: dict[str, object],
    events: list[dict[str, object]],
) -> None:
    """Run every commit-hook check on the run before its audit is written or it is published.

    A rejection names the hook's reason code, writes nothing and leaves the agent's decision and
    receipt correctable; a published run is never corrected in place.
    """

    guard = _hook_module("agentic_review_receipt_guard.py")
    validate = guard["validate_review_run"]
    # The hook resolves the shared root through its own module; use the client's location.
    validate.__globals__["_record_location"] = _record_location
    execution = receipt.get("execution")
    client = execution.get("client") if isinstance(execution, dict) else None
    client_id = client.get("id") if isinstance(client, dict) else None
    if client_id not in guard["CLIENTS"]:
        raise GovernanceClientError("review-artifact-invalid")
    try:
        validate(
            project_root,
            client_id,
            receipt_raw,
            receipt,
            datetime.now(UTC),
            "git",
            audit_raw=_audit_bytes(events),
        )
    except guard["GuardError"] as exc:
        raise GovernanceClientError("review-run-invalid", reason_code=exc.code) from None
    except Exception:
        raise GovernanceClientError("review-run-invalid") from None


def _audit_bytes(events: list[dict[str, object]]) -> bytes:
    return "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    ).encode("utf-8")


def _weight_micros(value: object) -> int:
    if type(value) not in {int, float}:
        raise GovernanceClientError("review-artifact-invalid")
    try:
        scaled = Decimal(str(value)) * 1_000_000
    except (InvalidOperation, ValueError):
        raise GovernanceClientError("review-artifact-invalid") from None
    if scaled != scaled.to_integral_value() or scaled <= 0:
        raise GovernanceClientError("review-artifact-invalid")
    return int(scaled)


def _percent_basis_points(value: object) -> int:
    if type(value) not in {int, float}:
        raise GovernanceClientError("review-artifact-invalid")
    scaled = Decimal(str(value)) * 100
    if scaled != scaled.to_integral_value() or scaled < 0:
        raise GovernanceClientError("review-artifact-invalid")
    return int(scaled)


def _hard_fail_state(
    guard: dict[str, Any],
    components: dict[str, Any],
    observation: dict[str, object],
    finding: dict[str, object],
) -> str:
    """``hard-fail`` for a verified authoritative detector binding, otherwise a blocking reason."""

    agent_id = str(observation["agent_id"])
    try:
        guard["_validate_hard_fail_binding"](observation, finding, agent_id.removeprefix("agent:"))
    except guard["GuardError"]:
        return "AGG_DETECTOR_EVIDENCE_INVALID"
    binding = cast(dict[str, object], finding["hard_fail_binding"])
    authoritative, unresolved = components["hard_fail_detectors"][agent_id]
    if binding.get("detector_id") in authoritative:
        return "hard-fail"
    if binding.get("detector_id") in unresolved:
        return "AGG_AUTHORITATIVE_CONFLICT"
    return "AGG_DETECTOR_EVIDENCE_INVALID"


def _policy_outcome(
    guard: dict[str, Any],
    components: dict[str, Any],
    observations: list[dict[str, object]],
) -> tuple[dict[str, object], list[int]]:
    """Apply the versioned aggregation policy to the twelve reports; return outcome and scores.

    Specialists classify their findings; this code maps severities to the policy's score bands,
    takes each Agent's maximum, applies the weights and thresholds and resolves precedence
    ``BLOCKED_INCOMPLETE > HARD-FAIL > FAIL > PASS``.
    """

    policy = components["aggregation_policy"]
    thresholds = policy["thresholds"]
    floor = thresholds.get("confidence_floor")
    if type(floor) not in {int, float}:
        raise GovernanceClientError("review-artifact-invalid")
    scores = components["severity_scores"]
    blocking: set[str] = set()
    hard_fail = False
    vetoed = False
    agent_scores: list[int] = []
    weighted_sum = 0
    total_weight = 0
    status_reasons = {"failed": "AGG_AGENT_FAILED", "timeout": "AGG_TIMEOUT"}
    for observation in observations:
        agent_id = str(observation["agent_id"])
        if observation.get("status") != "ok":
            blocking.add(status_reasons.get(str(observation.get("status")), "AGG_INVALID_SCHEMA"))
        maximum = 0
        for finding in cast(list[dict[str, object]], observation.get("findings", [])):
            severity = str(finding.get("severity"))
            confidence = finding.get("confidence")
            if severity not in scores or type(confidence) not in {int, float}:
                raise GovernanceClientError("review-artifact-invalid")
            maximum = max(maximum, int(scores[severity]))
            if cast(float, confidence) < floor:
                blocking.add("AGG_LOW_CONFIDENCE")
            if str(finding.get("source", "")).startswith("source-conflict:"):
                blocking.add("AGG_AUTHORITATIVE_CONFLICT")
            if finding.get("hard_fail_binding") is not None:
                state = _hard_fail_state(guard, components, observation, finding)
                if state == "hard-fail":
                    hard_fail = True
                else:
                    blocking.add(state)
            if (
                agent_id in SECURITY_CRITICAL_VETO_AGENTS
                and severity == "critical"
                and cast(float, confidence) >= floor
            ):
                vetoed = True
        agent_scores.append(maximum)
        weight = _weight_micros(policy["weights"].get(agent_id))
        weighted_sum += maximum * weight
        total_weight += weight
    risk = (weighted_sum + total_weight // 2) // total_weight
    compliance = max(0, _percent_basis_points(thresholds.get("compliance_baseline")) - risk)
    if blocking:
        verdict, reasons = "BLOCKED_INCOMPLETE", sorted(blocking)
    elif hard_fail:
        verdict, reasons = "HARD-FAIL", ["AGG_HARD_FAIL"]
    elif vetoed:
        verdict, reasons = "FAIL", ["AGG_SECURITY_CRITICAL_VETO"]
    elif risk >= _percent_basis_points(thresholds.get("fail_score")):
        verdict, reasons = "FAIL", ["AGG_THRESHOLD_FAIL"]
    elif risk >= _percent_basis_points(thresholds.get("warning_score")):
        verdict, reasons = "PASS", ["AGG_THRESHOLD_WARNING"]
    else:
        verdict, reasons = "PASS", ["AGG_THRESHOLD_PASS"]
    outcome: dict[str, object] = {
        "verdict": verdict,
        "reason_codes": reasons,
        "weighted_risk_score_basis_points": risk,
        "compliance_score_basis_points": compliance,
    }
    return outcome, agent_scores


def _explanation_templates(raw: bytes) -> dict[tuple[str, str], str]:
    """``templates.<decision>.<reason_code>.text`` of the versioned explanation catalog."""

    templates: dict[tuple[str, str], str] = {}
    decision: str | None = None
    reason: str | None = None
    try:
        lines = raw.decode("utf-8").splitlines()
        start = lines.index("templates:") + 1
    except (UnicodeError, ValueError):
        raise GovernanceClientError("review-artifact-invalid") from None
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.startswith("  "):
            break
        matched = re.fullmatch(r"  ([A-Z][A-Z_-]+):", line)
        if matched is not None:
            decision, reason = matched.group(1), None
            continue
        matched = re.fullmatch(r"    ([A-Z][A-Z0-9_]+):", line)
        if matched is not None:
            reason = matched.group(1)
            continue
        matched = re.fullmatch(r"      text: (\".*\")", line)
        if matched is not None and decision is not None and reason is not None:
            templates[(decision, reason)] = str(_decode(matched.group(1).encode("utf-8")))
    return templates


def _rationale(components: dict[str, Any], outcome: dict[str, object]) -> str:
    """The decision's summary from the versioned template of its first reason code."""

    reasons = cast(list[str], outcome["reason_codes"])
    template = _explanation_templates(components["explanations"]).get(
        (str(outcome["verdict"]), reasons[0])
    )
    if template is None:
        raise GovernanceClientError("review-artifact-invalid")
    text = template.format(decision=outcome["verdict"], reason_code=reasons[0])
    if len(reasons) > 1:
        text += f" Ek gerekçe kodları: {', '.join(reasons[1:])}."
    return text


def _empty_manifest(canonicalization: str) -> dict[str, object]:
    return {
        "canonicalization": canonicalization,
        "availability": "not-used",
        "reason_code": "NOT_USED",
        "item_count": 0,
        "sha256": _canonical_sha256({"canonicalization": canonicalization, "items": []}),
    }


def _model_rerun(model: dict[str, object]) -> dict[str, object]:
    """Best-effort rerun metadata; only the reported model id and effort are ever known."""

    def unavailable(reason: str) -> dict[str, object]:
        return {
            "availability": "unavailable",
            "reason_code": reason,
            "id": None,
            "version": None,
            "sha256": None,
        }

    effort = model.get("effort")
    parameter: dict[str, object] = (
        {"name": "effort", "availability": "available", "reason_code": None, "value": effort}
        if effort is not None
        else {
            "name": "effort",
            "availability": "unavailable",
            "reason_code": "INFERENCE_PARAMETER_UNAVAILABLE",
            "value": None,
        }
    )
    return {
        "capability": "model_rerun",
        "requirement": "best-effort",
        "status": "unavailable",
        "reason_codes": ["MODEL_METADATA_UNAVAILABLE"],
        "exact_output_guaranteed": False,
        "provider": unavailable("PROVIDER_METADATA_UNAVAILABLE"),
        "deployment": unavailable("DEPLOYMENT_METADATA_UNAVAILABLE"),
        "model": unavailable("MODEL_VERSION_UNAVAILABLE"),
        "inference_parameters": {
            "availability": "partial" if effort is not None else "unavailable",
            "parameters": [parameter],
        },
        "controlled_evidence_reference": {
            "status": "unavailable",
            "reason_code": "CONTROLLED_EVIDENCE_NOT_CONFIGURED",
            "reference": None,
            "content_sha256": None,
            "access_controlled": False,
            "time_bounded": False,
            "expires_at": None,
        },
    }


def _decision_evidence(
    guard: dict[str, Any],
    context: dict[str, Any],
    components: dict[str, Any],
    results: list[dict[str, object]],
    primary_outcome: dict[str, object],
    second_outcome: dict[str, object],
    started_at: str,
    decided_at: str,
) -> dict[str, object]:
    """The single versioned evidence object; every digest is recomputed from its sources."""

    harness = components["mandatory_governed_execution"]
    evaluator = components["agentic_evaluator"]
    client = context["client"]
    metadata = prompt_metadata_by_ref(str(context["prompt_source_ref"]))
    envelope: dict[str, object] = {
        "kind": "redacted-digest-only-prompt-envelope",
        "version": "1.0.0",
        "source_event_id": metadata["event_id"],
        "source_prompt_turn_id": metadata["prompt_turn_id"],
        "source_receipt_sha256": metadata["source_receipt_sha256"],
        "prompt_capture_sha256": metadata["prompt_capture_sha256"],
        "raw_content_stored": False,
    }
    envelope["sha256"] = _canonical_sha256(envelope)
    component_binding = {
        "authority": {
            "ref": "authority:project-manifest",
            "version": components["authority"]["version"],
            "sha256": components["authority"]["sha256"],
        },
        "orchestration": {
            key: components["orchestration"][key] for key in ("ref", "version", "sha256")
        },
        "aggregation_policy": {
            key: components["aggregation_policy"][key] for key in ("ref", "version", "sha256")
        },
        "agentic_evaluator": {
            "ref": evaluator["policy_ref"],
            "version": evaluator["version"],
            "sha256": evaluator["sha256"],
        },
        "harness": {
            "ref": harness["protocol_id"],
            "version": harness["version"],
            "sha256": harness["sha256"],
        },
        "rule": {key: harness["rule"][key] for key in ("ref", "version", "sha256")},
        "skill": {key: harness["skill"][key] for key in ("ref", "version", "sha256")},
        "agent_manifest": {
            "canonicalization": "kt-agentic-agent-component-manifest-json-v1",
            "agent_count": len(results),
            "sha256": _canonical_sha256(guard["_agent_manifest"](results)),
        },
        "client": {key: client[key] for key in ("id", "version", "sha256")},
    }
    manifests = {
        "context": _empty_manifest("kt-agentic-context-manifest-json-v1"),
        "retrieval": _empty_manifest("kt-agentic-retrieval-manifest-json-v1"),
        "tool_results": _empty_manifest("kt-agentic-tool-result-manifest-json-v1"),
    }
    primary: dict[str, object] = {
        "canonicalization": "kt-agentic-primary-evaluation-json-v1",
        "sha256": "",
        "invocation_id": context["evaluator"]["invocation_id"],
        "span_id": context["evaluator"]["span_id"],
        "started_at": started_at,
        "completed_at": started_at,
        **primary_outcome,
    }
    primary["sha256"] = _canonical_sha256(primary, excluding="sha256")
    snapshot_sha256 = context["snapshot_sha256"]
    checked = {
        "canonicalization": "kt-agentic-checked-digest-set-json-v1",
        "canonical_input_sha256": snapshot_sha256,
        "snapshot_sha256": snapshot_sha256,
        "authority_sha256": component_binding["authority"]["sha256"],
        "orchestration_sha256": component_binding["orchestration"]["sha256"],
        "aggregation_policy_sha256": component_binding["aggregation_policy"]["sha256"],
        "agentic_evaluator_sha256": component_binding["agentic_evaluator"]["sha256"],
        "harness_sha256": component_binding["harness"]["sha256"],
        "rule_sha256": component_binding["rule"]["sha256"],
        "skill_sha256": component_binding["skill"]["sha256"],
        "agent_manifest_sha256": component_binding["agent_manifest"]["sha256"],
        "client_sha256": component_binding["client"]["sha256"],
        "prompt_template_sha256": component_binding["skill"]["sha256"],
        "prompt_envelope_sha256": envelope["sha256"],
        "context_manifest_sha256": manifests["context"]["sha256"],
        "retrieval_manifest_sha256": manifests["retrieval"]["sha256"],
        "tool_result_manifest_sha256": manifests["tool_results"]["sha256"],
        "primary_evaluation_sha256": primary["sha256"],
    }
    audit_replay: dict[str, object] = {
        "capability": "audit_replay",
        "requirement": "mandatory",
        "canonicalization": "kt-agentic-audit-replay-json-v1",
        "sha256": "",
        "status": "verified",
        "reason_codes": ["AUDIT_REPLAY_VERIFIED"],
        "project_id": context["project_id"],
        "run_id": context["run_id"],
        "trace_id": context["trace_id"],
        "input_binding": {
            "canonical_input": {
                "canonicalization": "kt-agentic-review-input-manifest-json-v1",
                "item_count": 1,
                "sha256": snapshot_sha256,
            },
            "snapshot": {
                "canonicalization": "kt-git-index-snapshot-json-v1",
                "sha256": snapshot_sha256,
            },
            "acceptance_criteria": context["acceptance_criteria"],
        },
        "component_binding": component_binding,
        "prompt_binding": {
            "template": {key: harness["skill"][key] for key in ("ref", "version", "sha256")},
            "envelope": envelope,
        },
        "manifests": manifests,
        "primary_evaluation": primary,
        "second_pass_validator": {
            "validator_id": "validator:governed-review-agentic-second-pass",
            "version": evaluator["version"],
            "sha256": _canonical_sha256(
                {
                    "canonicalization": "kt-agentic-second-pass-validator-binding-json-v1",
                    "agentic_evaluator_sha256": evaluator["sha256"],
                    "harness_sha256": harness["sha256"],
                    "skill_sha256": harness["skill"]["sha256"],
                }
            ),
            "method": "independent-second-pass-policy-recalculation",
            "invocation_id": context["second_pass"]["invocation_id"],
            "span_id": context["second_pass"]["span_id"],
            "checked_digest_set": checked,
            "checked_digest_set_sha256": _canonical_sha256(checked),
            "result": "verified",
            "recalculated": second_outcome,
            "matches_primary_evaluation": True,
            "claim_boundary": {
                "external_independence_proven": False,
                "deterministic_runtime": False,
                "production_authority": False,
            },
            "completed_at": decided_at,
        },
    }
    audit_replay["sha256"] = _canonical_sha256(audit_replay, excluding="sha256")
    evidence: dict[str, object] = {
        "schema_version": "1.1",
        "kind": "AgenticGovernedReviewDecisionEvidence",
        "evidence_profile": "phase1-evidence-bound-accountable-replay",
        "canonicalization": "kt-agentic-decision-evidence-json-v1",
        "evidence_sha256": "",
        "audit_replay": audit_replay,
        "model_rerun": _model_rerun(cast(dict[str, object], context["model"])),
        "data_handling": {**_data_handling(), "credential_stored": False},
    }
    evidence["evidence_sha256"] = _canonical_sha256(evidence, excluding="evidence_sha256")
    return evidence


def _decision(
    context: dict[str, Any],
    components: dict[str, Any],
    evidence: dict[str, Any],
    observations: list[dict[str, object]],
) -> dict[str, object]:
    primary = evidence["audit_replay"]["primary_evaluation"]
    policy = components["aggregation_policy"]
    return {
        "schema_version": "1.0",
        "kind": "AgenticGovernedReviewDecision",
        "evidence_profile": "phase1-agentic-advisory",
        "receipt_id": context["receipt_id"],
        "project_id": context["project_id"],
        "run_id": context["run_id"],
        "trace_id": context["trace_id"],
        "span_id": primary["span_id"],
        "evaluator_invocation_id": primary["invocation_id"],
        "snapshot_sha256": context["snapshot_sha256"],
        "aggregation_policy": {
            key: policy[key]
            for key in ("ref", "version", "sha256", "instructions_ref", "instructions_sha256")
        },
        "agentic_evaluator": components["agentic_evaluator"],
        "agent_statuses": {
            str(observation["agent_id"]): observation["status"] for observation in observations
        },
        "acceptance_criteria": context["acceptance_criteria"],
        "decision": primary["verdict"],
        "reason_codes": primary["reason_codes"],
        "rationale_summary": primary["rationale_summary"],
        "weighted_risk_score_basis_points": primary["weighted_risk_score_basis_points"],
        "compliance_score_basis_points": primary["compliance_score_basis_points"],
        "decision_evidence_sha256": evidence["evidence_sha256"],
        "claim_boundary": {
            "deterministic_decision": False,
            "canonical_conformance": False,
            "runtime_admission": False,
            "production_decision": False,
        },
        "data_handling": _data_handling(),
        "evaluation_started_at": primary["started_at"],
        "decided_at": evidence["audit_replay"]["second_pass_validator"]["completed_at"],
    }


def _receipt(
    guard: dict[str, Any],
    context: dict[str, Any],
    components: dict[str, Any],
    snapshot: dict[str, object],
    results: list[dict[str, object]],
    evidence: dict[str, Any],
    decision: dict[str, object],
    decision_raw: bytes,
    created_at: str,
) -> dict[str, object]:
    run_id = context["run_id"]
    client_id = context["client"]["id"]
    hook_error, timeout = guard["EXPECTED_NATIVE_SURFACE"][client_id]
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "kind": "AgenticGovernedReviewReceipt",
        "evidence_profile": "phase1-agentic-advisory",
        "receipt_id": context["receipt_id"],
        "project_id": context["project_id"],
        "run_id": run_id,
        "trace_id": context["trace_id"],
        "authority": components["authority"],
        "snapshot": {**snapshot, "snapshot_sha256": context["snapshot_sha256"]},
        "orchestration": components["orchestration"],
        "aggregation_policy": components["aggregation_policy"],
        "agentic_evaluator": components["agentic_evaluator"],
        "mandatory_governed_execution": components["mandatory_governed_execution"],
        "execution": {
            "session_id": context["session_id"],
            "client": context["client"],
            "model": context["model"],
        },
        "agent_results": results,
        "acceptance_criteria": context["acceptance_criteria"],
        "reuse_identity_canonicalization": "kt-agentic-review-reuse-json-v3",
        "reuse_identity_sha256": "",
        "decision_evidence": evidence,
        "decision": decision["decision"],
        "reason_codes": decision["reason_codes"],
        "weighted_risk_score_basis_points": decision["weighted_risk_score_basis_points"],
        "compliance_score_basis_points": decision["compliance_score_basis_points"],
        "report_directory": f"governed-review/{run_id}/reports",
        "decision_path": f"governed-review/{run_id}/decision.json",
        "decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
        "audit_path": f"governed-review/{run_id}/audit.json",
        "audit_event_count": 14,
        "receipt_canonicalization": "kt-agentic-governed-review-receipt-json-v1",
        "receipt_sha256": "",
        "same_snapshot_retry_only": True,
        "native_surface": {
            "client_id": client_id,
            "adapter_mode": "native-command-receipt-guard",
            "hook_error_behavior": hook_error,
            "timeout_behavior": timeout,
            "enforcement_claim": "conditional-native-guard",
            "native_result_recorded": False,
            "commit_retry_recorded": False,
        },
        "claim_boundary": {
            "deterministic_decision": False,
            "canonical_conformance": False,
            "runtime_admission": False,
            "production_decision": False,
            "immutable_audit": False,
        },
        "data_handling": _data_handling(),
        "created_at": created_at,
    }
    receipt["reuse_identity_sha256"] = _canonical_sha256(guard["_reuse_identity"](receipt))
    receipt["receipt_sha256"] = _canonical_sha256(receipt, excluding="receipt_sha256")
    return receipt


def _finding_summaries(observations: list[dict[str, object]]) -> list[dict[str, object]]:
    """Report references for the Agent's answer to the user; no raw source or prompt."""

    summaries: list[dict[str, object]] = []
    for observation in observations:
        for finding in cast(list[dict[str, object]], observation.get("findings", [])):
            locations = cast(list[dict[str, object]], finding.get("locations", []))
            summaries.append(
                {
                    "agent_id": observation["agent_id"],
                    "finding_id": finding.get("finding_id"),
                    "severity": finding.get("severity"),
                    "confidence": finding.get("confidence"),
                    "title": finding.get("title"),
                    "locations": [
                        f"{location.get('path')}:{location.get('start_line')}"
                        for location in locations[:3]
                    ],
                }
            )
    return summaries


def _run_inputs(
    run_root: Path, guard: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, object], dict[str, dict[str, object]]]:
    """The code-written run context, snapshot identity and twelve bindings inputs."""

    _, context = _read_review_json(run_root / "inputs" / "run.json")
    _, snapshot = _read_review_json(run_root / "inputs" / "snapshot.json")
    if (
        context.get("canonicalization") != RUN_CONTEXT_CANONICALIZATION
        or context.get("run_id") != run_root.name
        or _canonical_sha256(snapshot) != context.get("snapshot_sha256")
    ):
        raise GovernanceClientError("review-artifact-invalid")
    bindings: dict[str, dict[str, object]] = {}
    for agent_id in guard["AGENTS"]:
        slug = agent_id.removeprefix("agent:")
        bindings[agent_id] = _read_review_json(run_root / "inputs" / f"{slug}.bindings.json")[1]
    return cast(dict[str, Any], context), snapshot, bindings


def finalize_review(run_id: str) -> dict[str, object]:
    """Decide a complete run and, for PASS, write its receipt, audit and publication; resumable.

    The decision, its evidence and the receipt come from the twelve reports, the run inputs and
    the versioned policies.  An interrupted run resumes from its stored decision and receipt;
    the Agent never writes or corrects them.
    """

    started = time.monotonic()
    project_root = Path.cwd().resolve(strict=True)
    project_id, run_root = _review_run(project_root, run_id)
    guard = _hook_module("agentic_review_receipt_guard.py")
    context, snapshot, bindings = _run_inputs(run_root, guard)
    try:
        current = guard["_capture_snapshot"](project_root, "git")
        components = _component_bindings(project_root, guard, str(context["client"]["id"]))
    except guard["GuardError"] as exc:
        raise GovernanceClientError("review-run-invalid", reason_code=exc.code) from None
    if current["snapshot_sha256"] != context["snapshot_sha256"]:
        raise GovernanceClientError("review-run-invalid", reason_code="SNAPSHOT_CHANGED")
    missing = [
        agent_id
        for agent_id in guard["AGENTS"]
        if not (run_root / "reports" / f"{agent_id.removeprefix('agent:')}.json").exists()
    ]
    if missing:
        return {
            "status": "incomplete",
            "run_id": run_id,
            "missing_agents": missing,
            "next_action": "dispatch-specialists",
        }
    schemas = guard["_schema_registry"](project_root)
    observations: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    for agent_id in guard["AGENTS"]:
        slug = agent_id.removeprefix("agent:")
        raw, observation = _read_review_json(run_root / "reports" / f"{slug}.json")
        try:
            guard["_validate_against_schema"](
                observation, "agentic-governance-observation.schema.json", schemas
            )
        except guard["GuardError"]:
            raise GovernanceClientError(
                "review-run-invalid", reason_code="REPORT_SCHEMA_INVALID"
            ) from None
        expected = _observation_bindings(context, components, agent_id)
        if any(observation.get(key) != value for key, value in expected.items()) or any(
            observation.get(key) != value for key, value in bindings[agent_id].items()
        ):
            raise GovernanceClientError("review-run-invalid", reason_code="REPORT_BINDING_MISMATCH")
        observations.append(observation)
        findings = cast(list[object], observation.get("findings", []))
        results.append(
            {
                "agent_id": agent_id,
                "invocation_id": expected["invocation_id"],
                "span_id": expected["span_id"],
                "status": observation["status"],
                "component_binding": expected["component_binding"],
                "report_path": f"governed-review/{run_id}/reports/{slug}.json",
                "report_sha256": hashlib.sha256(raw).hexdigest(),
                "finding_count": len(findings),
                "max_risk_score_basis_points": 0,
            }
        )
    outcome, agent_scores = _policy_outcome(guard, components, observations)
    for index, score in enumerate(agent_scores):
        results[index]["max_risk_score_basis_points"] = score
    outcome = {**outcome, "rationale_summary": _rationale(components, outcome)}
    decision_path = run_root / "decision.json"
    if decision_path.exists() or decision_path.is_symlink():
        decision_raw, decision = _read_review_json(decision_path)
        started_at = str(decision.get("evaluation_started_at"))
        decided_at = str(decision.get("decided_at"))
    else:
        started_at = _iso_utc(datetime.now(UTC))
        decided_at = ""
    receipt_like = {
        "aggregation_policy": components["aggregation_policy"],
        "agent_results": results,
    }
    try:
        recalculated = guard["recalculate_policy_outcome"](
            receipt_like,
            observations,
            components["severity_scores"],
            components["hard_fail_detectors"],
        )
    except guard["GuardError"] as exc:
        raise GovernanceClientError("review-run-invalid", reason_code=exc.code) from None
    second_outcome = {**recalculated, "rationale_summary": _rationale(components, recalculated)}
    if second_outcome != outcome:
        # Producer and commit-hook verifier disagree: record nothing and let the tests show why.
        raise GovernanceClientError(
            "review-run-invalid", reason_code="POLICY_RECALCULATION_MISMATCH"
        )
    if not decided_at:
        decided_at = _iso_utc(datetime.now(UTC))
    evidence = _decision_evidence(
        guard, context, components, results, outcome, second_outcome, started_at, decided_at
    )
    decision = _decision(context, components, evidence, observations)
    try:
        guard["_validate_against_schema"](
            evidence, "agentic-governed-review-decision-evidence.schema.json", schemas
        )
        guard["_validate_against_schema"](
            decision, "agentic-governed-review-decision.schema.json", schemas
        )
    except guard["GuardError"] as exc:
        raise GovernanceClientError("review-run-invalid", reason_code=exc.code) from None
    _, decision_raw, _ = _write_artifact(project_id, run_id, "decision", decision)
    summary: dict[str, object] = {
        "run_id": run_id,
        "acceptance_criteria": decision["acceptance_criteria"],
        "decision": decision["decision"],
        "reason_codes": decision["reason_codes"],
        "rationale_summary": decision["rationale_summary"],
        "weighted_risk_score_basis_points": decision["weighted_risk_score_basis_points"],
        "compliance_score_basis_points": decision["compliance_score_basis_points"],
        "findings": _finding_summaries(observations),
    }
    if decision["decision"] != "PASS":
        return {
            **summary,
            "status": "decided",
            "next_action": "resolve-findings-and-start-a-new-run",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    receipt_path = run_root / "receipt.json"
    if not (receipt_path.exists() or receipt_path.is_symlink()):
        receipt = _receipt(
            guard,
            context,
            components,
            snapshot,
            results,
            evidence,
            decision,
            decision_raw,
            _iso_utc(datetime.now(UTC)),
        )
        _write_artifact(project_id, run_id, "receipt", receipt)
    receipt_raw, receipt = _read_review_json(receipt_path)
    events = _build_review_audit_events(run_root, receipt_path, receipt, decision_raw, decision)
    _verify_review_run(project_root, receipt_raw, receipt, events)
    writer = _hook_module("governance_records.py")
    location = _record_location()
    try:
        try:
            writer["write_review_run_file"](
                project_id, run_id, "audit", {"events": events}, location=location
            )
            audit = "written"
        except writer["RecordError"] as exc:
            if exc.code != "review-run-file-exists":
                raise
            _, stored = writer["read_review_run_file"](
                project_id, run_id, "audit", location=location
            )
            if stored.get("body") != {"events": events}:
                raise GovernanceClientError("audit-invalid") from None
            audit = "reused"
        _, created = writer["publish_review"](
            project_id,
            context["snapshot_sha256"],
            run_id,
            hashlib.sha256(receipt_raw).hexdigest(),
            location=location,
        )
    except writer["RecordError"]:
        raise GovernanceClientError("current-publication-failed") from None
    return {
        **summary,
        "status": "complete",
        "audit": audit,
        "current_receipt": "published" if created else "reused",
        "next_action": "commit-retry",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def _project_id(project_root: Path) -> str:
    value = _read_regular_json(
        project_root / ".kt-scaffold/project-manifest.json", maximum=MAX_PROMPT_METADATA_BYTES
    ).get("project_id")
    if not isinstance(value, str) or PROJECT_ID_RE.fullmatch(value) is None:
        raise GovernanceClientError("prompt-metadata-invalid")
    return value


def _metadata_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GovernanceClientError("prompt-metadata-invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise GovernanceClientError("prompt-metadata-invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise GovernanceClientError("prompt-metadata-invalid")
    return parsed


def _validate_prompt_metadata(
    value: dict[str, object], *, client_id: str, project_id: str, event_token: str
) -> datetime:
    source_ref = f"record:v1:{project_id}:prompt-ingress:{event_token}"
    expected_event = "beforeSubmitPrompt" if client_id == "cursor" else "UserPromptSubmit"
    if (
        set(value) != PROMPT_METADATA_KEYS
        or value.get("schema_version") != "2.0"
        or value.get("kind") != "PromptIngressMetadata"
        or value.get("project_id") != project_id
        or value.get("client_id") != client_id
        or value.get("event") != expected_event
        or value.get("event_id") != f"event:{event_token}"
        or value.get("source_receipt_path") != source_ref
        or not isinstance(value.get("source_receipt_sha256"), str)
        or DIGEST_RE.fullmatch(str(value["source_receipt_sha256"])) is None
        or not isinstance(value.get("prompt_capture_sha256"), str)
        or DIGEST_RE.fullmatch(str(value["prompt_capture_sha256"])) is None
        or not isinstance(value.get("prompt_session_id"), str)
        or SESSION_ID_RE.fullmatch(str(value["prompt_session_id"])) is None
        or value.get("prompt_session_id_source") != "client-envelope"
        or not isinstance(value.get("prompt_turn_id"), str)
        or TURN_ID_RE.fullmatch(str(value["prompt_turn_id"])) is None
        or value.get("prompt_turn_id_source")
        not in {"client-envelope", "local-generated-client-unavailable"}
        or value.get("decision") not in {"allow", "block"}
        or value.get("outcome") not in {"clean", "matched", "input-invalid", "guard-error"}
        or (value.get("decision") == "allow" and value.get("outcome") != "clean")
        or (value.get("decision") == "block" and value.get("outcome") == "clean")
    ):
        raise GovernanceClientError("prompt-metadata-invalid")
    try:
        _hook_module("llm_call_events.py")["validate_model"](value.get("model"))
    except Exception:
        raise GovernanceClientError("prompt-metadata-invalid") from None
    return _metadata_time(value.get("occurred_at"))


def _hook_module(name: str) -> dict[str, Any]:
    path = Path(__file__).resolve().with_name(name)
    if path.is_symlink() or not path.is_file():
        raise GovernanceClientError("prompt-metadata-invalid")
    return runpy.run_path(str(path))


def _record_location() -> Any:
    """The shared governance root; ``None`` selects the fixed operating-system location."""
    return None


def _stored_prompt_metadata(record: dict[str, Any]) -> dict[str, object]:
    try:
        return cast(
            dict[str, object], _hook_module("prompt_ingress_guard.py")["prompt_metadata"](record)
        )
    except GovernanceClientError:
        raise
    except Exception:
        raise GovernanceClientError("prompt-metadata-invalid") from None


def prompt_metadata_by_ref(source_ref: str) -> dict[str, object]:
    """Return the metadata projection of one stored prompt record in the shared root."""

    match = re.fullmatch(
        r"record:v1:(project-[0-9a-f]{32}):prompt-ingress:([0-9a-f]{32})", source_ref
    )
    if match is None:
        raise GovernanceClientError("invalid-request")
    writer = _hook_module("governance_records.py")
    try:
        record = writer["read_event"](
            "prompt-ingress", match.group(1), match.group(2), location=_record_location()
        )
    except writer["RecordError"]:
        raise GovernanceClientError("prompt-metadata-missing") from None
    return _stored_prompt_metadata(record)


def current_prompt_metadata(client_id: str) -> dict[str, object]:
    """Return the latest prompt metadata bound to the current native client session."""
    environment_names = CLIENT_SESSION_ENVIRONMENT.get(client_id)
    if environment_names is None:
        raise GovernanceClientError("invalid-request")
    session_ids = {
        "session:client." + hashlib.sha256(raw.encode("utf-8")).hexdigest()
        for name in environment_names
        if (raw := os.environ.get(name))
    }
    if not session_ids:
        raise GovernanceClientError("current-session-unavailable")

    project_id = _project_id(Path.cwd())
    writer = _hook_module("governance_records.py")
    try:
        records = writer["recent_events"](
            "prompt-ingress",
            project_id,
            limit=MAX_PROMPT_METADATA_FILES,
            location=_record_location(),
        )
    except writer["RecordError"]:
        raise GovernanceClientError("prompt-metadata-invalid") from None
    candidates: list[tuple[datetime, dict[str, object]]] = []
    for record in records:
        body = record.get("body")
        if (
            record.get("client") != client_id
            or not isinstance(body, dict)
            or body.get("prompt_session_id") not in session_ids
        ):
            continue
        metadata = _stored_prompt_metadata(record)
        observed_at = _validate_prompt_metadata(
            metadata,
            client_id=client_id,
            project_id=project_id,
            event_token=str(record["record_id"]),
        )
        if metadata["prompt_session_id"] in session_ids:
            candidates.append((observed_at, metadata))

    if not candidates:
        raise GovernanceClientError(
            "prompt-metadata-missing", guidance=PROMPT_HOOK_TRUST_GUIDANCE.get(client_id)
        )
    if len({str(value["prompt_session_id"]) for _, value in candidates}) != 1:
        raise GovernanceClientError("prompt-metadata-ambiguous")
    latest_time = max(observed_at for observed_at, _ in candidates)
    latest = [value for observed_at, value in candidates if observed_at == latest_time]
    if len(latest) != 1:
        raise GovernanceClientError("prompt-metadata-ambiguous")
    selected = latest[0]
    if selected["decision"] != "allow" or selected["outcome"] != "clean":
        raise GovernanceClientError("prompt-metadata-invalid")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(description="Shared-root prompt metadata and review publication.")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("preflight")
    current_metadata = commands.add_parser("current-prompt-metadata")
    current_metadata.add_argument(
        "--client-id", choices=tuple(CLIENT_SESSION_ENVIRONMENT), required=True
    )
    metadata = commands.add_parser("metadata")
    metadata.add_argument("--source-ref", required=True)
    start = commands.add_parser("review-start")
    start.add_argument("--run-id", required=True)
    start.add_argument("--client-id", choices=tuple(CLIENT_SESSION_ENVIRONMENT), required=True)
    start.add_argument("--client-version", required=True)
    start.add_argument("--criteria-path", required=True)
    finalize = commands.add_parser("finalize-review")
    finalize.add_argument("--run-id", required=True)
    observation = commands.add_parser("observation")
    observation.add_argument("--run-id", required=True)
    observation.add_argument("--agent", required=True)
    commands.add_parser("consultation")
    if argv is None:
        script = Path(__file__)
        if _hook_module("governance_records.py")["ensure_profile_interpreter"](
            Path.cwd(), script, sys.argv[1:]
        ):
            print(json.dumps({"error": "python-runtime-mismatch"}, separators=(",", ":")))
            return 1
    try:
        arguments = parser.parse_args(argv)
        exit_code = 0
        if arguments.operation == "preflight":
            result = preflight()
            exit_code = 0 if result["ok"] is True else 1
        elif arguments.operation == "current-prompt-metadata":
            result = current_prompt_metadata(arguments.client_id)
        elif arguments.operation == "metadata":
            result = prompt_metadata_by_ref(arguments.source_ref)
        elif arguments.operation == "review-start":
            result = review_start(
                arguments.run_id,
                arguments.client_id,
                arguments.client_version,
                arguments.criteria_path,
            )
        elif arguments.operation == "finalize-review":
            result = finalize_review(arguments.run_id)
            exit_code = 0 if result["status"] == "complete" else 1
        elif arguments.operation == "consultation":
            result = record_consultation(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
        else:
            result = record_observation(arguments.run_id, arguments.agent)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return exit_code
    except GovernanceClientError as exc:
        failure: dict[str, object] = {"error": str(exc)}
        if exc.reason_code is not None:
            failure["reason_code"] = exc.reason_code
        if exc.violation is not None:
            failure["violation"] = exc.violation
        if exc.guidance is not None:
            failure["guidance"] = exc.guidance
        print(json.dumps(failure, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
