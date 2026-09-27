#!/usr/bin/env python3
"""Write governance records to the shared, repository-free governance root.

Records live outside the consumer repository and the user's home directory, under one
operating-system root shared by every local user, keyed by ``project_id``. Each record is written
once and never changed, so a collector can pick up new files incrementally. The storage location
is visible and user-writable by design: it is not an integrity boundary. Trust comes from the
specialist agents and from the hooks that enforce their evidence on the agent path.

This module is dependency-free. Hooks load it with ``runpy``; the factory package reuses the same
file through ``kt_scaffold.governance_records``.
"""

from __future__ import annotations

import contextlib
import getpass
import json
import os
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

# Hooks may start on the host's python3 before moving to the project's `.venv`; keep 3.9 syntax.
UTC = timezone.utc  # noqa: UP017
SCHEMA = "kt-governance-record/v1"
SHARED_DIRECTORY_MODE = 0o1777
RECORD_FILE_MODE = 0o644

DATED_KINDS = frozenset(
    {"prompt-ingress", "llm-call-events", "commit-governance", "agent-consultation"}
)
ADDRESSED_KINDS = frozenset({"review-baseline", "authority-pin"})
REVIEW_RUN_KIND = "governed-review"
MAX_RECORD_BYTES = {
    "llm-call-events": 16 * 1024,
    "prompt-ingress": 256 * 1024,
    "commit-governance": 64 * 1024,
    "agent-consultation": 512 * 1024,
    "authority-pin": 64 * 1024,
    "review-baseline": 2 * 1024 * 1024,
}
MAX_REVIEW_RUN_BYTES = {
    "snapshot": 4 * 1024 * 1024,
    "reports": 512 * 1024,
}
DEFAULT_REVIEW_RUN_BYTES = 1024 * 1024
CONTEXT_FIELDS = (
    "client",
    "client_source",
    "session_hash",
    "turn_hash",
    "identity_source",
)
CLIENT_SOURCES = frozenset({"envelope", "command"})
MAX_CONTEXT_CHARACTERS = 256

PROJECT_ID_RE = re.compile(r"^project-[0-9a-f]{32}$")
RECORD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ADDRESS_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^run-[A-Za-z0-9][A-Za-z0-9._-]{3,119}$")
RUN_FILE_RE = re.compile(r"^(?:snapshot|decision|receipt|audit|lease|reports/[a-z0-9-]{1,64})$")
# Canonical run artifacts the governance client writes as raw bytes: the run inputs, the decision
# and the receipt.  Specialist reports have their own writer; the audit is an enveloped record.
RUN_ARTIFACT_RE = re.compile(
    r"^(?:inputs/(?:snapshot|run|[a-z][a-z0-9]*(?:-[a-z0-9]+)*\.bindings)|decision|receipt)$"
)
AGENT_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
MAX_IDENTITY_CHARACTERS = 256
# Variables that could point Git at a different repository than the project.
GIT_LOCATION_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)
GIT_TIMEOUT_SECONDS = 30


class RecordError(Exception):
    """A record could not be written; ``code`` is a stable, content-free reason."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GovernanceLocation:
    """The provisioned ``anchor`` must already exist; ``root`` is created below it on demand."""

    anchor: Path
    root: Path


def resolve_location(
    platform_name: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> GovernanceLocation:
    """Return the fixed shared root for this operating system; no variable can relocate it."""

    selected = sys.platform if platform_name is None else platform_name
    values = os.environ if environment is None else environment
    if selected == "darwin":
        anchor = Path("/Users/Shared")
        return GovernanceLocation(anchor, anchor / "kt-scaffold" / "governance")
    if selected == "win32":
        program_data = values.get("ProgramData") or values.get("PROGRAMDATA")
        if not program_data:
            raise RecordError("root-unavailable")
        windows_anchor = PureWindowsPath(program_data)
        if not windows_anchor.is_absolute() or ".." in windows_anchor.parts:
            raise RecordError("root-unavailable")
        anchor = Path(str(windows_anchor))
        return GovernanceLocation(anchor, anchor / "kt-scaffold" / "governance")
    linux_root = Path(str(PurePosixPath("/var/lib/kt-scaffold/governance")))
    return GovernanceLocation(linux_root, linux_root)


def device_name() -> str:
    return _bounded_identity(socket.gethostname())


def os_user() -> str:
    if os.name == "posix":
        import pwd

        with contextlib.suppress(KeyError):
            return _bounded_identity(pwd.getpwuid(os.geteuid()).pw_name)
    return _bounded_identity(getpass.getuser())


def _bounded_identity(value: str) -> str:
    cleaned = "".join(character for character in value if character.isprintable()).strip()
    if not cleaned:
        return "unavailable"
    return cleaned[:MAX_IDENTITY_CHARACTERS]


def _now() -> datetime:
    return datetime.now(UTC)


def _require_project_id(project_id: str) -> None:
    if not isinstance(project_id, str) or PROJECT_ID_RE.fullmatch(project_id) is None:
        raise RecordError("project-id-invalid")


def _is_windows() -> bool:
    return os.name == "nt"


def _checked_directory(path: Path) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        raise RecordError("root-unavailable") from None
    except OSError as exc:
        raise RecordError("root-unavailable") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise RecordError("root-path-unsafe")


def _shared_directory(path: Path) -> None:
    """Create ``path`` as a shared directory, or accept an existing real directory."""

    try:
        path.mkdir(mode=SHARED_DIRECTORY_MODE)
    except FileExistsError:
        _checked_directory(path)
        return
    except OSError as exc:
        raise RecordError("root-not-writable") from exc
    _checked_directory(path)
    if not _is_windows():
        try:
            os.chmod(path, SHARED_DIRECTORY_MODE)
        except OSError as exc:
            raise RecordError("root-not-writable") from exc


def _prepare_directory(location: GovernanceLocation, parts: tuple[str, ...]) -> Path:
    _checked_directory(location.anchor)
    relative = location.root.relative_to(location.anchor).parts
    current = location.anchor
    for part in (*relative, *parts):
        current = current / part
        _shared_directory(current)
    return current


def _fsync_directory(path: Path) -> None:
    if _is_windows():
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(destination: Path, payload: bytes) -> bool:
    """Atomically publish ``payload``; return False when the destination already exists."""

    temporary = destination.parent / f".{destination.name}.{secrets.token_hex(16)}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, RECORD_FILE_MODE)
    except OSError as exc:
        raise RecordError("root-not-writable") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            if not _is_windows():
                os.fchmod(handle.fileno(), RECORD_FILE_MODE)
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            return False
        _fsync_directory(destination.parent)
        return True
    except OSError as exc:
        raise RecordError("record-write-failed") from exc
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()


def _encode(record: Mapping[str, Any], limit: int) -> bytes:
    try:
        payload = (
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RecordError("record-invalid") from exc
    if len(payload) > limit:
        raise RecordError("record-too-large")
    return payload


def _context(context: Mapping[str, object] | None) -> dict[str, object]:
    supplied = {} if context is None else dict(context)
    if set(supplied) - set(CONTEXT_FIELDS):
        raise RecordError("record-context-invalid")
    result: dict[str, object] = {}
    for field in CONTEXT_FIELDS:
        value = supplied.get(field)
        if value is not None and (
            not isinstance(value, str)
            or not value
            or len(value) > MAX_CONTEXT_CHARACTERS
            or not value.isprintable()
        ):
            raise RecordError("record-context-invalid")
        result[field] = value
    if result["client_source"] is not None and result["client_source"] not in CLIENT_SOURCES:
        raise RecordError("record-context-invalid")
    return result


def _envelope(
    kind: str,
    project_id: str,
    record_id: str,
    body: Mapping[str, Any],
    recorded_at: datetime,
    context: Mapping[str, object] | None,
) -> dict[str, Any]:
    """Wrap ``body`` unchanged; identity fields come from this process, never from the caller."""

    if not isinstance(body, Mapping):
        raise RecordError("record-invalid")
    return {
        "schema": SCHEMA,
        "kind": kind,
        "record_id": record_id,
        "project_id": project_id,
        "device_name": device_name(),
        "os_user": os_user(),
        "recorded_at": recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        **_context(context),
        "body": dict(body),
    }


def write_event(
    kind: str,
    project_id: str,
    body: Mapping[str, Any],
    *,
    record_id: str | None = None,
    context: Mapping[str, object] | None = None,
    location: GovernanceLocation | None = None,
    now: datetime | None = None,
) -> Path:
    """Write one dated event record under ``<root>/<project_id>/<kind>/<YYYY-MM-DD>/``.

    ``record_id`` lets a producer reuse its own random event token so the record can be found
    again; it must be 32 lowercase hex characters.
    """

    if kind not in DATED_KINDS:
        raise RecordError("record-kind-invalid")
    _require_project_id(project_id)
    if record_id is None:
        record_id = secrets.token_hex(16)
    elif not isinstance(record_id, str) or RECORD_ID_RE.fullmatch(record_id) is None:
        raise RecordError("record-id-invalid")
    moment = _now() if now is None else now
    payload = _encode(
        _envelope(kind, project_id, record_id, body, moment, context), MAX_RECORD_BYTES[kind]
    )
    selected = resolve_location() if location is None else location
    day = moment.astimezone(UTC).strftime("%Y-%m-%d")
    directory = _prepare_directory(selected, (project_id, kind, day))
    destination = directory / f"{record_id}.json"
    if not _write_once(destination, payload):
        raise RecordError("record-id-collision")
    return destination


def write_addressed(
    kind: str,
    project_id: str,
    address: str,
    body: Mapping[str, Any],
    *,
    context: Mapping[str, object] | None = None,
    location: GovernanceLocation | None = None,
    now: datetime | None = None,
) -> tuple[Path, bool]:
    """Publish a content-addressed record; an existing address is kept, never overwritten."""

    if kind not in ADDRESSED_KINDS:
        raise RecordError("record-kind-invalid")
    _require_project_id(project_id)
    if not isinstance(address, str) or ADDRESS_RE.fullmatch(address) is None:
        raise RecordError("record-address-invalid")
    moment = _now() if now is None else now
    payload = _encode(
        _envelope(kind, project_id, address, body, moment, context), MAX_RECORD_BYTES[kind]
    )
    selected = resolve_location() if location is None else location
    directory = _prepare_directory(selected, (project_id, kind))
    destination = directory / f"{address}.json"
    return destination, _write_once(destination, payload)


def write_review_run_file(
    project_id: str,
    run_id: str,
    name: str,
    body: Mapping[str, Any],
    *,
    context: Mapping[str, object] | None = None,
    location: GovernanceLocation | None = None,
    now: datetime | None = None,
) -> Path:
    """Write one immutable file of a governed-review run under ``governed-review/<run_id>/``."""

    _require_project_id(project_id)
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        raise RecordError("review-run-id-invalid")
    if not isinstance(name, str) or RUN_FILE_RE.fullmatch(name) is None:
        raise RecordError("review-run-file-invalid")
    moment = _now() if now is None else now
    group = name.split("/", 1)[0]
    limit = MAX_REVIEW_RUN_BYTES.get(group, DEFAULT_REVIEW_RUN_BYTES)
    record_id = f"{run_id}/{name}"
    payload = _encode(
        _envelope(REVIEW_RUN_KIND, project_id, record_id, body, moment, context), limit
    )
    selected = resolve_location() if location is None else location
    parts = (project_id, REVIEW_RUN_KIND, run_id, *name.split("/")[:-1])
    directory = _prepare_directory(selected, parts)
    destination = directory / f"{name.rsplit('/', 1)[-1]}.json"
    if not _write_once(destination, payload):
        raise RecordError("review-run-file-exists")
    return destination


def _read_file(path: Path, limit: int) -> dict[str, Any]:
    try:
        status = path.lstat()
    except FileNotFoundError:
        raise RecordError("record-not-found") from None
    except OSError as exc:
        raise RecordError("record-unreadable") from exc
    if not stat.S_ISREG(status.st_mode) or status.st_size > limit:
        raise RecordError("record-unreadable")
    try:
        with path.open("rb") as handle:
            raw = handle.read(limit + 1)
        record = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordError("record-unreadable") from exc
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise RecordError("record-unreadable")
    return record


def _kind_directory(kind: str, project_id: str, location: GovernanceLocation | None) -> Path:
    _require_project_id(project_id)
    selected = resolve_location() if location is None else location
    directory = selected.root / project_id / kind
    for candidate in (selected.anchor, selected.root, selected.root / project_id, directory):
        if candidate.exists() or candidate.is_symlink():
            _checked_directory(candidate)
    return directory


def read_event(
    kind: str,
    project_id: str,
    record_id: str,
    *,
    location: GovernanceLocation | None = None,
) -> dict[str, Any]:
    """Return one dated event record by its identifier, whatever day it was written."""

    if kind not in DATED_KINDS:
        raise RecordError("record-kind-invalid")
    if not isinstance(record_id, str) or RECORD_ID_RE.fullmatch(record_id) is None:
        raise RecordError("record-id-invalid")
    directory = _kind_directory(kind, project_id, location)
    if not directory.is_dir():
        raise RecordError("record-not-found")
    for day in sorted(directory.iterdir(), reverse=True):
        candidate = day / f"{record_id}.json"
        if not day.is_symlink() and day.is_dir() and (candidate.exists() or candidate.is_symlink()):
            record = _read_file(candidate, MAX_RECORD_BYTES[kind])
            if record.get("record_id") != record_id or record.get("project_id") != project_id:
                raise RecordError("record-unreadable")
            return record
    raise RecordError("record-not-found")


def recent_events(
    kind: str,
    project_id: str,
    *,
    limit: int,
    location: GovernanceLocation | None = None,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` readable records, newest first; unreadable files are skipped."""

    if kind not in DATED_KINDS:
        raise RecordError("record-kind-invalid")
    directory = _kind_directory(kind, project_id, location)
    if not directory.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for day in sorted(directory.iterdir(), reverse=True):
        if day.is_symlink() or not day.is_dir():
            continue
        records = []
        for candidate in day.glob("*.json"):
            with contextlib.suppress(RecordError):
                record = _read_file(candidate, MAX_RECORD_BYTES[kind])
                if record.get("project_id") == project_id and record.get("kind") == kind:
                    records.append(record)
        records.sort(key=lambda record: str(record.get("recorded_at")), reverse=True)
        found.extend(records)
        if len(found) >= limit:
            break
    return found[:limit]


def read_addressed(
    kind: str,
    project_id: str,
    address: str,
    *,
    location: GovernanceLocation | None = None,
) -> dict[str, Any]:
    if kind not in ADDRESSED_KINDS:
        raise RecordError("record-kind-invalid")
    if not isinstance(address, str) or ADDRESS_RE.fullmatch(address) is None:
        raise RecordError("record-address-invalid")
    directory = _kind_directory(kind, project_id, location)
    record = _read_file(directory / f"{address}.json", MAX_RECORD_BYTES[kind])
    if record.get("record_id") != address or record.get("project_id") != project_id:
        raise RecordError("record-unreadable")
    return record


STATE_DIRECTORY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def prepare_directory(
    project_id: str, *parts: str, location: GovernanceLocation | None = None
) -> Path:
    """Create ``<root>/<project_id>/<parts...>`` with shared modes for working state files."""

    _require_project_id(project_id)
    if not parts or any(STATE_DIRECTORY_RE.fullmatch(part) is None for part in parts):
        raise RecordError("state-directory-invalid")
    selected = resolve_location() if location is None else location
    return _prepare_directory(selected, (project_id, *parts))


def addressed_records(
    kind: str,
    project_id: str,
    *,
    location: GovernanceLocation | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Return the content-addressed records of ``kind``; ``strict`` fails on any unreadable one."""

    if kind not in ADDRESSED_KINDS:
        raise RecordError("record-kind-invalid")
    directory = _kind_directory(kind, project_id, location)
    if not directory.is_dir():
        return []
    records = []
    for candidate in sorted(directory.iterdir()):
        if candidate.name.startswith("."):
            continue
        try:
            record = _read_file(candidate, MAX_RECORD_BYTES[kind])
            if (
                candidate.suffix != ".json"
                or record.get("project_id") != project_id
                or record.get("record_id") != candidate.stem
            ):
                raise RecordError("record-unreadable")
        except RecordError:
            if strict:
                raise
            continue
        records.append(record)
    return records


REVIEW_INPUT_DIRECTORIES = ("inputs", "reports", "work")
PUBLICATION_DIRECTORY = "published"


def _require_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        raise RecordError("review-run-id-invalid")


def review_area(project_id: str, *, location: GovernanceLocation | None = None) -> Path:
    """Return ``<root>/<project_id>/governed-review`` after checking every existing component."""

    return _kind_directory(REVIEW_RUN_KIND, project_id, location)


def prepare_review_run(
    project_id: str, run_id: str, *, location: GovernanceLocation | None = None
) -> Path:
    """Create the run directory; its inputs, reports, decision and receipt come from commands."""

    _require_project_id(project_id)
    _require_run_id(run_id)
    selected = resolve_location() if location is None else location
    run = _prepare_directory(selected, (project_id, REVIEW_RUN_KIND, run_id))
    for name in REVIEW_INPUT_DIRECTORIES:
        _shared_directory(run / name)
    return run


def write_review_report(
    project_id: str,
    run_id: str,
    agent_slug: str,
    payload: bytes,
    *,
    location: GovernanceLocation | None = None,
) -> tuple[Path, bool]:
    """Write one specialist report of a run once; return its path and whether it was created."""

    _require_project_id(project_id)
    _require_run_id(run_id)
    if not isinstance(agent_slug, str) or AGENT_SLUG_RE.fullmatch(agent_slug) is None:
        raise RecordError("review-run-file-invalid")
    if len(payload) > MAX_REVIEW_RUN_BYTES["reports"]:
        raise RecordError("record-too-large")
    selected = resolve_location() if location is None else location
    directory = _prepare_directory(selected, (project_id, REVIEW_RUN_KIND, run_id, "reports"))
    destination = directory / f"{agent_slug}.json"
    return destination, _write_once(destination, payload)


def write_review_artifact(
    project_id: str,
    run_id: str,
    name: str,
    payload: bytes,
    *,
    location: GovernanceLocation | None = None,
) -> tuple[Path, bool]:
    """Write one canonical run input, decision or receipt once; return its path and creation."""

    _require_project_id(project_id)
    _require_run_id(run_id)
    if not isinstance(name, str) or RUN_ARTIFACT_RE.fullmatch(name) is None:
        raise RecordError("review-run-file-invalid")
    if len(payload) > DEFAULT_REVIEW_RUN_BYTES:
        raise RecordError("record-too-large")
    selected = resolve_location() if location is None else location
    parts = (project_id, REVIEW_RUN_KIND, run_id, *name.split("/")[:-1])
    directory = _prepare_directory(selected, parts)
    destination = directory / f"{name.rsplit('/', 1)[-1]}.json"
    return destination, _write_once(destination, payload)


def read_review_run_file(
    project_id: str,
    run_id: str,
    name: str,
    *,
    location: GovernanceLocation | None = None,
) -> tuple[Path, dict[str, Any]]:
    _require_run_id(run_id)
    if not isinstance(name, str) or RUN_FILE_RE.fullmatch(name) is None:
        raise RecordError("review-run-file-invalid")
    group = name.split("/", 1)[0]
    limit = MAX_REVIEW_RUN_BYTES.get(group, DEFAULT_REVIEW_RUN_BYTES)
    path = review_area(project_id, location=location) / run_id / f"{name}.json"
    record = _read_file(path, limit)
    if record.get("record_id") != f"{run_id}/{name}" or record.get("project_id") != project_id:
        raise RecordError("record-unreadable")
    return path, record


def publish_review(
    project_id: str,
    snapshot_sha256: str,
    run_id: str,
    receipt_sha256: str,
    *,
    location: GovernanceLocation | None = None,
    now: datetime | None = None,
) -> tuple[Path, bool]:
    """Mark a finalized PASS run as the review of one staged snapshot; never overwrite a mark."""

    _require_project_id(project_id)
    _require_run_id(run_id)
    for value in (snapshot_sha256, receipt_sha256):
        if not isinstance(value, str) or ADDRESS_RE.fullmatch(value) is None:
            raise RecordError("record-address-invalid")
    moment = _now() if now is None else now
    record_id = f"{PUBLICATION_DIRECTORY}/{snapshot_sha256}/{run_id}"
    body = {"run_id": run_id, "snapshot_sha256": snapshot_sha256, "receipt_sha256": receipt_sha256}
    payload = _encode(
        _envelope(REVIEW_RUN_KIND, project_id, record_id, body, moment, None),
        DEFAULT_REVIEW_RUN_BYTES,
    )
    selected = resolve_location() if location is None else location
    directory = _prepare_directory(
        selected, (project_id, REVIEW_RUN_KIND, PUBLICATION_DIRECTORY, snapshot_sha256)
    )
    destination = directory / f"{run_id}.json"
    return destination, _write_once(destination, payload)


def published_reviews(
    project_id: str,
    snapshot_sha256: str,
    *,
    location: GovernanceLocation | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Return the publication marks of one staged snapshot, newest first."""

    if not isinstance(snapshot_sha256, str) or ADDRESS_RE.fullmatch(snapshot_sha256) is None:
        raise RecordError("record-address-invalid")
    directory = review_area(project_id, location=location) / PUBLICATION_DIRECTORY / snapshot_sha256
    if directory.is_symlink() or not directory.is_dir():
        return []
    marks = []
    for candidate in directory.glob("*.json"):
        with contextlib.suppress(RecordError):
            record = _read_file(candidate, DEFAULT_REVIEW_RUN_BYTES)
            body = record.get("body")
            if (
                record.get("project_id") == project_id
                and isinstance(body, dict)
                and body.get("snapshot_sha256") == snapshot_sha256
                and body.get("run_id") == candidate.stem
            ):
                marks.append((candidate, record))
    marks.sort(key=lambda item: str(item[1].get("recorded_at")), reverse=True)
    return marks


def profile_python_version(project_root: Path) -> str | None:
    profile = project_root / "technology-profile.yml"
    try:
        if profile.is_symlink() or not profile.is_file():
            return None
        text = profile.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    in_backend = False
    for line in text.splitlines():
        if line and not line[0].isspace():
            in_backend = line.rstrip() == "backend:"
            continue
        match = re.fullmatch(r"\s+language:\s*python-(\d+\.\d+)\s*", line)
        if in_backend and match:
            return match.group(1)
    return None


PYTHON_ENVIRONMENT_SCRIPT = ".kt-scaffold/hooks/python_environment.py"


def repair_command(required: str) -> str:
    """The one project-root command that prepares `.venv` on the profile's Python."""
    script = PYTHON_ENVIRONMENT_SCRIPT
    return f"python{required} {script} hazirla (Windows: py -{required} {script} hazirla)"


def venv_interpreter(project_root: Path) -> Path:
    if _is_windows():
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python"


REEXEC_MARKER = "KT_SCAFFOLD_PROFILE_INTERPRETER"


def ensure_profile_interpreter(
    project_root: Path, script: Path, arguments: list[str]
) -> str | None:
    """Run the entry point on the profile's Python, moving once into the project's ``.venv``.

    Returns ``None`` when the running interpreter matches the technology profile. Otherwise it
    replaces the process with ``.venv`` when that exists, or returns ``python-runtime-mismatch``
    so a gate can refuse and an observation hook can warn.
    """

    expected = profile_python_version(project_root)
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    if expected is not None and running == expected:
        return None
    interpreter = venv_interpreter(project_root)
    # A POSIX `.venv` interpreter is normally a link to its base Python; follow it once.
    if expected is not None and os.environ.get(REEXEC_MARKER) != "1" and interpreter.is_file():
        environment = {**os.environ, REEXEC_MARKER: "1"}
        os.execve(  # noqa: S606 -- replace this hook with the same script on the profile Python
            str(interpreter), [str(interpreter), str(script), *arguments], environment
        )
    return "python-runtime-mismatch"


def repository_status(project_root: Path) -> str:
    """Report whether the project sits in a Git work tree with a commit; change nothing."""

    executable = shutil.which("git")
    if executable is None:
        return "git-unavailable"
    environment = {
        key: value for key, value in os.environ.items() if key not in GIT_LOCATION_VARIABLES
    }
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"

    def succeeds(*arguments: str) -> bool:
        completed = subprocess.run(
            [executable, "-C", str(project_root), *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=environment,
        )
        return completed.returncode == 0 and completed.stdout.strip() != b"false"

    try:
        if not succeeds("rev-parse", "--is-inside-work-tree"):
            return "not-a-repository"
        if not succeeds("rev-parse", "--verify", "--quiet", "HEAD"):
            return "no-commit"
    except (OSError, subprocess.SubprocessError):
        return "git-unavailable"
    return "ok"


def preflight(project_root: Path, location: GovernanceLocation | None = None) -> dict[str, Any]:
    """Report the root, its writability, the interpreter match and the project's Git state.

    It reads no record and changes nothing.
    """

    try:
        selected = resolve_location() if location is None else location
    except RecordError as exc:
        return {"ok": False, "root": None, "root_status": exc.code}
    root_status = "ok"
    try:
        _checked_directory(selected.anchor)
        if selected.root.exists() or selected.root.is_symlink():
            _checked_directory(selected.root)
            if not os.access(selected.root, os.W_OK | os.X_OK):
                root_status = "root-not-writable"
        elif not os.access(selected.anchor, os.W_OK | os.X_OK):
            root_status = "root-not-writable"
    except RecordError as exc:
        root_status = exc.code
    expected = profile_python_version(project_root)
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    interpreter = venv_interpreter(project_root)
    interpreter_status = "ok"
    if expected is None:
        interpreter_status = "profile-unavailable"
    elif not interpreter.is_file():
        interpreter_status = "venv-missing"
    elif running != expected:
        interpreter_status = "python-runtime-mismatch"
    repository = repository_status(project_root)
    return {
        "ok": root_status == "ok" and interpreter_status == "ok" and repository == "ok",
        "root": str(selected.root),
        "root_status": root_status,
        "profile_python": expected,
        "running_python": running,
        "venv_interpreter": str(interpreter),
        "interpreter_status": interpreter_status,
        "repository_status": repository,
    }


def main(arguments: list[str] | None = None) -> int:
    selected = sys.argv[1:] if arguments is None else arguments
    if selected != ["preflight"]:
        print("usage: governance_records.py preflight", file=sys.stderr)
        return 2
    result = preflight(Path.cwd())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
