#!/usr/bin/env python3
"""Fail closed when the generated runtime configuration surfaces drift.

This checker deliberately uses only the Python standard library so it can run before
backend dependencies are installed.  The application settings loader is the source of
truth; examples and deployment inputs must follow it.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_ENV_FROM_REFERENCE_COUNT = 1


class ConfigSyncError(RuntimeError):
    """A configuration contract cannot be proved from the generated tree."""


@dataclass(frozen=True)
class ConfigContract:
    profile: str
    env_prefix: str
    suffixes: frozenset[str]
    loader_paths: frozenset[Path]
    bootstrap_paths: frozenset[Path]

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(f"{self.env_prefix}{suffix}" for suffix in self.suffixes)

    @property
    def runtime_keys(self) -> frozenset[str]:
        return frozenset(
            f"{self.env_prefix}{suffix}"
            for suffix in self.suffixes
            if not suffix.startswith("BOOTSTRAP_")
        )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigSyncError(f"cannot read {path}: {exc}") from exc


def _answer_fields(path: Path) -> tuple[str, str]:
    """Read the two required flat YAML scalars without adding a YAML dependency."""

    values: dict[str, str] = {}
    for line_number, line in enumerate(_read(path).splitlines(), start=1):
        if not line or line.isspace() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        match = re.fullmatch(r"([a-z][a-z0-9_]*):[ \t]*(.*)", line)
        if match is None:
            # PyYAML emits top-level list members without indentation.  They cannot define either
            # scalar used by this checker, so ignore them and fail below if a required scalar was
            # not found in canonical top-level key/value form.
            continue
        key, raw = match.groups()
        if key not in {"backend_profile", "env_prefix"}:
            continue
        raw = raw.strip()
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConfigSyncError(f"{path}:{line_number}: invalid quoted scalar") from exc
        elif raw.startswith("'") and raw.endswith("'"):
            value = raw[1:-1].replace("''", "'")
        else:
            value = raw
        if not isinstance(value, str) or not value:
            raise ConfigSyncError(f"{path}:{line_number}: {key} must be a non-empty string")
        values[key] = value

    missing = sorted({"backend_profile", "env_prefix"} - values.keys())
    if missing:
        raise ConfigSyncError(f"{path}: missing required answers: {', '.join(missing)}")
    profile = values["backend_profile"]
    prefix = values["env_prefix"]
    if profile != "python-fastapi":
        raise ConfigSyncError(f"{path}: unsupported backend_profile {profile!r}")
    if re.fullmatch(r"[A-Z][A-Z0-9_]*_", prefix) is None:
        raise ConfigSyncError(f"{path}: invalid env_prefix {prefix!r}")
    return profile, prefix


def _python_contract(root: Path, expected_prefix: str) -> ConfigContract:
    relative = Path("app/backend/app/core/config.py")
    path = root / relative
    try:
        tree = ast.parse(_read(path), filename=str(path))
    except SyntaxError as exc:
        raise ConfigSyncError(f"cannot parse typed Python settings: {exc}") from exc

    settings_classes = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings"
    ]
    if len(settings_classes) != 1:
        raise ConfigSyncError(f"{path}: expected exactly one Settings class")
    settings = settings_classes[0]
    suffixes = {
        node.target.id.upper()
        for node in settings.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and not node.target.id.startswith("_")
    }
    if not suffixes:
        raise ConfigSyncError(f"{path}: no typed settings fields found")

    prefixes: list[str] = []
    for node in settings.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        function = node.value.func
        if not isinstance(function, ast.Name) or function.id != "SettingsConfigDict":
            continue
        for keyword in node.value.keywords:
            if (
                keyword.arg == "env_prefix"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                prefixes.append(keyword.value.value)
    if prefixes != [expected_prefix]:
        raise ConfigSyncError(
            f"{path}: typed loader env_prefix must be exactly {expected_prefix!r}, got {prefixes!r}"
        )

    return ConfigContract(
        profile="python-fastapi",
        env_prefix=expected_prefix,
        suffixes=frozenset(suffixes),
        loader_paths=frozenset({relative}),
        bootstrap_paths=frozenset({Path("app/backend/app/scripts/create_super_admin.py")}),
    )


def _check_env_example(root: Path, contract: ConfigContract, errors: list[str]) -> int:
    path = root / "app/backend/.env.example"
    source = _read(path)
    assigned = re.findall(r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", source)
    foreign = sorted(key for key in assigned if not key.startswith(contract.env_prefix))
    if foreign:
        errors.append(f"{path}: keys do not use {contract.env_prefix!r}: {', '.join(foreign)}")

    missing = sorted(
        key
        for key in contract.keys
        if re.search(rf"(?<![A-Z0-9_]){re.escape(key)}(?![A-Z0-9_])", source) is None
    )
    if missing:
        errors.append(f"{path}: typed keys are not represented: {', '.join(missing)}")
    return len(assigned)


def _compose_backend_environment(path: Path) -> list[str]:
    lines = _read(path).splitlines()
    backend_indexes = [
        index for index, line in enumerate(lines) if re.fullmatch(r"  backend:\s*", line)
    ]
    if len(backend_indexes) != 1:
        raise ConfigSyncError(f"{path}: expected exactly one backend service")
    start = backend_indexes[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index]
        if line and not line.startswith(" "):
            end = index
            break
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", line):
            end = index
            break

    environment_indexes = [
        index for index in range(start, end) if re.fullmatch(r"    environment:\s*", lines[index])
    ]
    if len(environment_indexes) != 1:
        raise ConfigSyncError(f"{path}: backend must have exactly one mapping environment block")
    environment_start = environment_indexes[0] + 1
    environment_end = end
    for index in range(environment_start, end):
        line = lines[index]
        if line.strip() and not line.startswith("      "):
            environment_end = index
            break

    keys: list[str] = []
    for index in range(environment_start, environment_end):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^      ([A-Z][A-Z0-9_]*):(?:\s|$)", line)
        if match is None:
            raise ConfigSyncError(
                f"{path}:{index + 1}: backend environment must use a scalar YAML mapping"
            )
        keys.append(match.group(1))
    if len(keys) != len(set(keys)):
        raise ConfigSyncError(f"{path}: duplicate backend environment keys")
    return keys


def _check_compose(root: Path, contract: ConfigContract, errors: list[str]) -> int:
    path = root / "app/infra/docker-compose.local.yml"
    keys = _compose_backend_environment(path)
    foreign = sorted(key for key in keys if not key.startswith(contract.env_prefix))
    if foreign:
        errors.append(
            f"{path}: backend keys do not use {contract.env_prefix!r}: {', '.join(foreign)}"
        )
    missing = sorted(contract.runtime_keys - set(keys))
    if missing:
        errors.append(
            f"{path}: runtime settings missing from backend environment: {', '.join(missing)}"
        )
    return len(keys)


def _contains_python_env_read(source: str) -> bool:
    return bool(
        re.search(r"\bos\s*\.\s*(?:environ|getenv)\b", source)
        or re.search(r"(?m)^\s*from\s+os\s+import\s+[^\n]*(?:environ|getenv)", source)
    )


def _check_process_environment(root: Path, contract: ConfigContract, errors: list[str]) -> int:
    backend = root / "app/backend"
    suffixes = {".py"}
    approved = contract.loader_paths | contract.bootstrap_paths
    checked = 0
    for path in sorted(backend.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        relative = path.relative_to(root)
        if (
            "tests" in relative.parts
            or "node_modules" in relative.parts
            or "dist" in relative.parts
        ):
            continue
        checked += 1
        source = _read(path)
        has_read = _contains_python_env_read(source)
        if has_read and relative not in approved:
            errors.append(f"{path}: direct process-environment read outside an approved boundary")

    return checked


def _check_kubernetes(root: Path, errors: list[str]) -> None:
    deployment = root / "helm/dwhcodereview/templates/backend-deployment.yaml"
    values = root / "helm/dwhcodereview/values.yaml"
    source = _read(deployment)
    # Only the backend section feeds the application; the database and migration own their Secrets.
    backend = re.search(r"(?ms)^backend:\s*$(.*?)(?=^\S|\Z)", _read(values))
    value_matches = re.findall(
        r"(?m)^  existingSecret:\s*([^#]+?)\s*(?:#.*)?$", backend.group(1) if backend else ""
    )
    if value_matches != ['""']:
        errors.append(
            f"{values}: backend existingSecret must be one empty environment-supplied fact"
        )

    env_from = re.findall(r"(?m)^\s+envFrom:\s*$", source)
    secret_refs = re.findall(r"(?m)^\s+-\s+secretRef:\s*.*$", source)
    if len(env_from) != 1:
        errors.append(f"{deployment}: expected exactly one envFrom boundary")
    if len(secret_refs) != EXPECTED_ENV_FROM_REFERENCE_COUNT:
        errors.append(f"{deployment}: expected exactly one secretRef under envFrom")
    elif re.search(r"\.Values\.backend\.existingSecret\b", secret_refs[0]) is None:
        errors.append(f"{deployment}: secretRef must use .Values.backend.existingSecret")
    if re.search(r"(?m)^\s+env:\s*$", source) is not None:
        errors.append(f"{deployment}: per-key container env mappings are forbidden; use envFrom")
    if "secretKeyRef:" in source or "configMapRef:" in source:
        errors.append(
            f"{deployment}: only the pre-created existingSecret envFrom boundary is allowed"
        )


def check(root: Path) -> dict[str, object]:
    answers_path = root / ".kt-scaffold/answers.yml"
    profile, prefix = _answer_fields(answers_path)
    contract = _python_contract(root, prefix)
    errors: list[str] = []
    env_assignments = _check_env_example(root, contract, errors)
    compose_keys = _check_compose(root, contract, errors)
    source_files = _check_process_environment(root, contract, errors)
    _check_kubernetes(root, errors)
    if errors:
        raise ConfigSyncError("\n".join(errors))
    return {
        "backend_profile": profile,
        "checked": {
            "compose_environment_keys": compose_keys,
            "env_example_assignments": env_assignments,
            "kubernetes_secret_refs": EXPECTED_ENV_FROM_REFERENCE_COUNT,
            "source_files": source_files,
            "typed_configuration_keys": len(contract.keys),
        },
        "env_prefix": prefix,
        "ok": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="generated project root")
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except ConfigSyncError as exc:
        print("configuration-sync: FAILED", file=sys.stderr)
        for line in str(exc).splitlines():
            print(f"- {line}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
