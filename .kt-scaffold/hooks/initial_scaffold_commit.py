#!/usr/bin/env python3
"""Recognize the project's initial scaffold commit, the one commit that needs no review receipt.

This dependency-free module is the single implementation of the `INITIAL_SCAFFOLD_COMMIT`
exception that commit hooks load.  It never writes, repairs or records anything and never creates
a receipt.  It answers `True` only when every condition holds; any doubt answers `False` and the
calling hook keeps its ordinary governed-review check.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

INITIAL_SCAFFOLD_COMMIT = "INITIAL_SCAFFOLD_COMMIT"
# The literal commands of `delivery.initial_commit`; any other spelling is a different command.
COMMIT_MESSAGE = "chore: KT proje iskeletini oluştur"
INITIAL_COMMIT_COMMANDS = (
    f'git commit -m "{COMMIT_MESSAGE}"',
    'git -c "user.name=KT İskelet" -c "user.email=kt-iskelet@kt-scaffold.invalid" '
    f'commit -m "{COMMIT_MESSAGE}"',
)
BRANCH_REF = "refs/heads/main"
MANIFEST_PATH = ".kt-scaffold/manifest.json"
MANIFEST_KEYS = {"format", "generator_version", "managed", "application_seed"}
# Variables that could point Git at another repository, index or object store.
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
MAX_FILES = 8192
MAX_BYTES = 128 * 1024 * 1024
TIMEOUT_SECONDS = 30
SHA256_RE = re.compile(r"[0-9a-f]{64}")
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
NOTICE = (
    f"{INITIAL_SCAFFOLD_COMMIT}: projenin ilk commit'ine (projenin ilk kaydedilmiş hâli) "
    "yönetilen inceleme makbuzu (kodun incelendiğini gösteren kayıt) aranmadan izin verildi; "
    "commit edilen dosyalar üreticinin kaydettiği iskelet dosyalarıyla birebir aynı. Sonraki "
    "her commit yönetilen incelemeyi ister."
)


class _Ineligible(Exception):
    """One unmet condition; the caller falls back to the ordinary check."""


def _require(condition: bool) -> None:
    if not condition:
        raise _Ineligible


def _git(directory: Path, *arguments: str, stdin: bytes | None = None) -> tuple[int, bytes]:
    executable = shutil.which("git")
    _require(executable is not None)
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        [str(executable), "-C", str(directory), *arguments],
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
        env=environment,
    )
    return completed.returncode, completed.stdout


def _output(directory: Path, *arguments: str, stdin: bytes | None = None) -> bytes:
    code, output = _git(directory, *arguments, stdin=stdin)
    _require(code == 0)
    return output


def _strict_json(raw: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        _require(len(keys) == len(set(keys)))
        return dict(pairs)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique)


def _staged_blobs(root: Path, object_ids: set[str]) -> dict[str, bytes]:
    """Read every staged blob once, bounded before any content is loaded."""

    request = ("\n".join(sorted(object_ids)) + "\n").encode("ascii")
    sizes: dict[str, int] = {}
    for line in _output(root, "cat-file", "--batch-check", stdin=request).splitlines():
        fields = line.decode("ascii").split(" ")
        _require(len(fields) == 3 and fields[1] == "blob" and fields[2].isdigit())
        sizes[fields[0]] = int(fields[2])
    _require(set(sizes) == object_ids and sum(sizes.values()) <= MAX_BYTES)
    output = _output(root, "cat-file", "--batch", stdin=request)
    blobs: dict[str, bytes] = {}
    cursor = 0
    while cursor < len(output):
        header_end = output.index(b"\n", cursor)
        fields = output[cursor:header_end].decode("ascii").split(" ")
        _require(len(fields) == 3 and fields[0] in sizes and fields[2] == str(sizes[fields[0]]))
        start, size = header_end + 1, sizes[fields[0]]
        _require(output[start + size : start + size + 1] == b"\n")
        blobs[fields[0]] = output[start : start + size]
        cursor = start + size + 1
    _require(set(blobs) == object_ids)
    return blobs


def _staged_index(root: Path) -> dict[str, str]:
    """Stage-0 regular or executable files only; symlinks, gitlinks and conflicts are refused."""

    staged: dict[str, str] = {}
    for record in _output(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.decode("ascii").split(" ")
        _require(
            bool(separator)
            and len(fields) == 3
            and fields[0] in {"100644", "100755"}
            and OBJECT_ID_RE.fullmatch(fields[1]) is not None
            and fields[2] == "0"
        )
        relative = raw_path.decode("utf-8")
        _require(relative not in staged)
        staged[relative] = fields[1]
    _require(0 < len(staged) <= MAX_FILES and MANIFEST_PATH in staged)
    return staged


def _recorded_scaffold(manifest_raw: bytes) -> dict[str, str]:
    """The generator's managed files plus its application seed, each with its SHA-256."""

    manifest = _strict_json(manifest_raw)
    _require(isinstance(manifest, dict) and set(manifest) == MANIFEST_KEYS)
    _require(manifest["format"] == 1 and isinstance(manifest["generator_version"], str))
    expected: dict[str, str] = {}
    for section in ("managed", "application_seed"):
        records = manifest[section]
        _require(isinstance(records, dict) and bool(records))
        for relative, digest in records.items():
            parts = PurePosixPath(relative).parts if isinstance(relative, str) else ()
            _require(
                isinstance(relative, str)
                and isinstance(digest, str)
                and SHA256_RE.fullmatch(digest) is not None
                and "\\" not in relative
                and not relative.startswith("/")
                and bool(parts)
                and all(part not in {"", ".", ".."} for part in parts)
                and relative != MANIFEST_PATH
                and relative not in expected
                and (section == "managed" or relative.startswith("app/"))
            )
            expected[relative] = digest
    return expected


def _require_initial_scaffold_commit(root: Path, event: dict[str, Any], client: str) -> None:
    # (a) Git inspects and commits the same repository and index, and the command runs here.
    _require(not any(name in os.environ for name in GIT_LOCATION_VARIABLES))
    cwd = event.get("cwd")
    if cwd is None and client == "github-copilot-vscode":
        observed = Path.cwd()
    else:
        _require(isinstance(cwd, str) and bool(cwd))
        observed = Path(str(cwd))
    top_level = _output(observed.resolve(), "rev-parse", "--show-toplevel").decode("utf-8")
    _require(Path(top_level.strip()).resolve() == root.resolve())
    # (b) No commit and no reference at all, with `HEAD` naming the unborn `main`.
    _require(_output(root, "symbolic-ref", "-q", "HEAD").strip() == BRANCH_REF.encode("ascii"))
    code, _ = _git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    _require(code == 1)
    _require(_output(root, "for-each-ref", "--format=%(refname)") == b"")
    # (d) The index is exactly the recorded scaffold, byte for byte.
    staged = _staged_index(root)
    blobs = _staged_blobs(root, set(staged.values()))
    expected = _recorded_scaffold(blobs[staged[MANIFEST_PATH]])
    _require(set(staged) == set(expected) | {MANIFEST_PATH})
    for relative, digest in expected.items():
        _require(hashlib.sha256(blobs[staged[relative]]).hexdigest() == digest)


def allowed(root: Path, command: object, event: dict[str, Any], client: str) -> bool:
    """True only for (c) a literal initial-commit command plus every repository condition."""

    if command not in INITIAL_COMMIT_COMMANDS:
        return False
    try:
        _require_initial_scaffold_commit(root, event, client)
    except Exception:
        return False
    return True
