#!/usr/bin/env python3
"""Fail closed when dependency authorities drift from their reviewed admission record."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

OCI_RE = re.compile(r"[A-Za-z0-9._/][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}")
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)")
ADVISORY_RE = re.compile(
    r"^(?:CVE-\d{4}-\d{4,}|GHSA-[23456789cfghjmpqrvwx]{4}(?:-[23456789cfghjmpqrvwx]{4}){2}|OSV-.+)$"
)
ALPINE_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+_.-]*=[A-Za-z0-9][A-Za-z0-9+_.-]*$")


def fail(message: str) -> None:
    raise SystemExit(f"dependency admission failed: {message}")


def safe_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.as_posix() != relative:
        fail(f"unsafe authority path: {relative}")
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"authority escapes project root: {relative}")
    return resolved


def require_file(root: Path, relative: str) -> Path:
    path = safe_path(root, relative)
    if not path.is_file() or path.is_symlink():
        fail(f"authority is missing or unsafe: {relative}")
    return path


def npm_inventory(path: Path, relative: str) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: list[str] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        dependencies = payload.get(section, {})
        if not isinstance(dependencies, dict):
            fail(f"{relative}: {section} must be an object")
        for name, version in sorted(dependencies.items()):
            if not isinstance(version, str) or not version:
                fail(f"{relative}: invalid version for {name}")
            result.append(f"npm:{relative}:{section}:{name}={version}")
    engines = payload.get("engines", {})
    if engines:
        if not isinstance(engines, dict):
            fail(f"{relative}: engines must be an object")
        for name, version in sorted(engines.items()):
            result.append(f"npm:{relative}:engines:{name}={version}")
    overrides = payload.get("overrides", {})
    if overrides:
        if not isinstance(overrides, dict):
            fail(f"{relative}: overrides must be an object")
        for name, version in sorted(overrides.items()):
            if not isinstance(version, str) or not version:
                fail(f"{relative}: override for {name} must be an exact version string")
            if version.startswith(("^", "~", ">", "<", "*")):
                fail(f"{relative}: override for {name} must use an exact version")
            result.append(f"npm:{relative}:overrides:{name}={version}")
    return result


def requirements_inventory(path: Path, relative: str) -> list[str]:
    result: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        match = PIN_RE.match(stripped)
        if match is None:
            fail(f"{relative}:{line_number}: direct requirement must use an exact == pin")
        result.append(
            f"python:{relative}:{match.group(1).lower().replace('_', '-')}={match.group(2)}"
        )
    return result


def python_hash_lock_inventory(path: Path, relative: str) -> list[str]:
    """Bind each locked wheel's exact version and SHA-256 so a new artifact needs review."""
    result: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+) \\", line)
        if match is None:
            fail(f"{relative}:{index}: locked wheel must use an exact == pin")
        hashed = (
            re.fullmatch(r"    --hash=sha256:([0-9a-f]{64})", lines[index])
            if index < len(lines)
            else None
        )
        if hashed is None:
            fail(f"{relative}:{index}: locked wheel requires exactly one SHA-256 hash")
        index += 1
        name = match.group(1).lower().replace("_", "-")
        result.append(f"wheel:{relative}:{name}={match.group(2)}@sha256:{hashed.group(1)}")
    if not result:
        fail(f"{relative}: hash lock inventory is empty")
    return result


def pyproject_inventory(path: Path, relative: str) -> list[str]:
    text = path.read_text(encoding="utf-8")
    groups: dict[str, list[str]] = {}
    for match in re.finditer(r"(?ms)^(requires|dependencies|test)\s*=\s*\[(.*?)\]", text):
        name, body = match.groups()
        requirements = re.findall(r'"([^"]+)"', body)
        if any("==" in requirement for requirement in requirements):
            groups[name] = requirements
    if not groups:
        fail(f"{relative}: no pinned dependency arrays found")
    result: list[str] = []
    for group, requirements in groups.items():
        for requirement in requirements:
            match = PIN_RE.match(requirement)
            if match is None:
                fail(f"{relative}: direct requirement must use an exact == pin: {requirement}")
            normalized_name = match.group(1).lower().replace("_", "-")
            coordinate = f"python:{relative}:{group}:{normalized_name}={match.group(2)}"
            result.append(coordinate)
    return result


def images_yaml_inventory(path: Path, relative: str) -> list[str]:
    result: list[str] = []
    source: str | None = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("source:"):
            source = stripped.partition(":")[2].strip()
        elif stripped.startswith("digest:"):
            digest = stripped.partition(":")[2].strip()
            if source is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                fail(f"{relative}:{line_number}: image source/digest pair is malformed")
            result.append(f"oci:{relative}:{source}@{digest}")
            source = None
    if source is not None or not result:
        fail(f"{relative}: image inventory is incomplete")
    return result


def alpine_lock_inventory(path: Path, relative: str) -> list[str]:
    result: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) != 4:
            fail(f"{relative}:{line_number}: Alpine lock record must contain four fields")
        docker_arch, alpine_arch, package_spec, digest = fields
        if docker_arch not in {"amd64", "arm64"}:
            fail(f"{relative}:{line_number}: unsupported Docker architecture")
        expected_alpine_arch = {"amd64": "x86_64", "arm64": "aarch64"}[docker_arch]
        if alpine_arch != expected_alpine_arch:
            fail(f"{relative}:{line_number}: Docker and Alpine architectures disagree")
        if ALPINE_PACKAGE_RE.fullmatch(package_spec) is None:
            fail(f"{relative}:{line_number}: Alpine package must use an exact name=version pin")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            fail(f"{relative}:{line_number}: Alpine package must use a lowercase SHA-256 digest")
        result.append(f"apk:{relative}:{docker_arch}:{alpine_arch}:{package_spec}@sha256:{digest}")
    if not result:
        fail(f"{relative}: Alpine lock inventory is empty")
    return result


def glob_files(root: Path, patterns: object) -> list[Path]:
    if not isinstance(patterns, list) or not patterns:
        fail("glob authority requires a non-empty patterns list")
    files: set[Path] = set()
    for pattern in patterns:
        if not isinstance(pattern, str):
            fail("glob pattern must be a string")
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            fail(f"unsafe authority glob: {pattern}")
        files.update(
            path for path in root.glob(pattern) if path.is_file() and not path.is_symlink()
        )
    if not files:
        fail(f"authority globs matched no files: {patterns}")
    return sorted(files)


def oci_inventory(root: Path, patterns: object) -> list[str]:
    result: set[str] = set()
    for path in glob_files(root, patterns):
        result.update(OCI_RE.findall(path.read_text(encoding="utf-8")))
    if not result:
        fail("OCI authorities contain no digest-pinned images")
    return [f"oci:{identity}" for identity in sorted(result)]


def actions_inventory(root: Path, patterns: object) -> list[str]:
    result: set[str] = set()
    for path in glob_files(root, patterns):
        for action in re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", path.read_text(), re.MULTILINE):
            if not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action):
                fail(f"{path.relative_to(root)}: action is not pinned by commit SHA: {action}")
            result.add(action)
    if not result:
        fail("workflow authorities contain no actions")
    return [f"github-action:{action}" for action in sorted(result)]


def build_inventory(root: Path, authorities: object) -> list[str]:
    if not isinstance(authorities, list) or not authorities:
        fail("authorities must be a non-empty list")
    inventory: list[str] = []
    for authority in authorities:
        if not isinstance(authority, dict):
            fail("authority entries must be objects")
        kind = authority.get("kind")
        relative = authority.get("path")
        if kind in {
            "npm",
            "requirements",
            "python-hash-lock",
            "pyproject",
            "images-yaml",
            "alpine-lock",
        }:
            if not isinstance(relative, str):
                fail(f"{kind} authority requires path")
            path = require_file(root, relative)
            if kind == "npm":
                inventory.extend(npm_inventory(path, relative))
            elif kind == "requirements":
                inventory.extend(requirements_inventory(path, relative))
            elif kind == "python-hash-lock":
                inventory.extend(python_hash_lock_inventory(path, relative))
            elif kind == "pyproject":
                inventory.extend(pyproject_inventory(path, relative))
            elif kind == "alpine-lock":
                inventory.extend(alpine_lock_inventory(path, relative))
            else:
                inventory.extend(images_yaml_inventory(path, relative))
        elif kind == "oci":
            inventory.extend(oci_inventory(root, authority.get("patterns")))
        elif kind == "github-actions":
            inventory.extend(actions_inventory(root, authority.get("patterns")))
        else:
            fail(f"unsupported authority kind: {kind}")
    if len(inventory) != len(set(inventory)):
        fail("authority inventory contains duplicate coordinates")
    return sorted(inventory)


def inventory_digest(inventory: list[str]) -> str:
    encoded = json.dumps(inventory, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        fail(f"{field} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        fail(f"{field} must be an ISO date")
    return parsed


def observability_variant(root: Path) -> str:
    answers = require_file(root, ".kt-scaffold/answers.yml")
    matches = re.findall(
        r"(?m)^observability:[ \t]*(true|false)[ \t]*$",
        answers.read_text(encoding="utf-8"),
    )
    if len(matches) != 1:
        fail(".kt-scaffold/answers.yml must define observability exactly once")
    enabled = matches[0] == "true"
    surfaces = (
        ("app/infra/observability", "directory"),
        ("app/infra/docker-compose.observability.yml", "file"),
    )
    for relative, kind in surfaces:
        path = safe_path(root, relative)
        valid = path.is_dir() if kind == "directory" else path.is_file()
        if enabled and (not valid or path.is_symlink()):
            fail(f"observability=true requires a safe {kind}: {relative}")
        if not enabled and path.exists():
            fail(f"observability=false forbids optional surface: {relative}")
    return "observability-enabled" if enabled else "observability-disabled"


def reviewed_inventory_digest(root: Path, decision: dict[str, Any]) -> tuple[str, str | None]:
    single = decision.get("inventory_sha256")
    variants = decision.get("inventory_sha256_by_variant")
    if isinstance(single, str) and variants is None:
        if re.fullmatch(r"[0-9a-f]{64}", single) is None:
            fail("decision.inventory_sha256 must be a lowercase SHA-256 digest")
        return single, None
    if single is not None or not isinstance(variants, dict):
        fail("decision requires exactly one inventory digest authority")
    expected_keys = {"observability-enabled", "observability-disabled"}
    if set(variants) != expected_keys or not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in variants.values()
    ):
        fail("decision.inventory_sha256_by_variant must contain exact enabled/disabled digests")
    variant = observability_variant(root)
    return variants[variant], variant


def validate_evidence(payload: dict[str, Any], digest: str, root: Path) -> None:
    policy = payload.get("policy")
    if not isinstance(policy, dict) or policy.get("minimum_release_age_days") != 30:
        fail("policy must enforce a 30-day minimum release age")
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        fail("decision must be an object")
    reviewed_digest, variant = reviewed_inventory_digest(root, decision)
    if reviewed_digest != digest:
        context = f" variant={variant}" if variant is not None else ""
        fail(f"authority inventory drifted; reviewed={reviewed_digest} actual={digest}{context}")
    reviewed_on = parse_date(decision.get("reviewed_on"), "decision.reviewed_on")
    if reviewed_on > date.today():
        fail("decision.reviewed_on cannot be in the future")
    compatibility = decision.get("compatibility_evidence")
    if (
        not isinstance(compatibility, list)
        or not compatibility
        or not all(isinstance(item, str) and item.strip() for item in compatibility)
    ):
        fail("decision requires compatibility_evidence")

    exceptions = payload.get("exceptions", [])
    if not isinstance(exceptions, list):
        fail("exceptions must be a list")
    seen: set[str] = set()
    for index, exception in enumerate(exceptions):
        label = f"exceptions[{index}]"
        if not isinstance(exception, dict):
            fail(f"{label} must be an object")
        artifact = exception.get("artifact")
        version = exception.get("version")
        if not isinstance(artifact, str) or not artifact or artifact in seen:
            fail(f"{label}.artifact must be non-empty and unique")
        seen.add(artifact)
        if not isinstance(version, str) or not version:
            fail(f"{label}.version is required")
        release_date = parse_date(exception.get("released_on"), f"{label}.released_on")
        if release_date > reviewed_on:
            fail(f"{label} was reviewed before its release")
        raw_sources = exception.get("release_evidence")
        sources = [raw_sources] if isinstance(raw_sources, str) else raw_sources
        if (
            not isinstance(sources, list)
            or not sources
            or not all(
                isinstance(source, str) and source.startswith(("https://", "internal://"))
                for source in sources
            )
        ):
            fail(
                f"{label}.release_evidence must identify every registry or approved internal record"
            )
        reason = exception.get("reason")
        age = (reviewed_on - release_date).days
        if age >= 30:
            fail(f"{label} is mature and must not be recorded as an exception")
        if reason == "security":
            advisories = exception.get("advisory_ids")
            if (
                not isinstance(advisories, list)
                or not advisories
                or not all(
                    isinstance(item, str) and ADVISORY_RE.fullmatch(item) for item in advisories
                )
            ):
                fail(f"{label} security exception requires advisory_ids")
        elif reason == "governance-exception":
            if not isinstance(exception.get("exception_id"), str) or not exception["exception_id"]:
                fail(f"{label} governance exception requires exception_id")
            evidence = exception.get("compatibility_evidence")
            if (
                not isinstance(evidence, list)
                or not evidence
                or not all(isinstance(item, str) and item.strip() for item in evidence)
            ):
                fail(f"{label} governance exception requires compatibility_evidence")
        else:
            fail(f"{label}.reason must be security or governance-exception")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--print-inventory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = (args.root or Path(__file__).resolve().parent.parent).resolve(strict=True)
    ledger = (args.ledger or root / "dependency-admission.json").resolve(strict=True)
    try:
        ledger.relative_to(root)
    except ValueError:
        fail("ledger must be inside the selected root")
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        fail("ledger schema_version must be 1")
    inventory = build_inventory(root, payload.get("authorities"))
    digest = inventory_digest(inventory)
    if args.print_inventory:
        print(json.dumps({"inventory_sha256": digest, "inventory": inventory}, indent=2))
        return 0
    validate_evidence(payload, digest, root)
    print(f"dependency admission current: {len(inventory)} coordinates, sha256:{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
