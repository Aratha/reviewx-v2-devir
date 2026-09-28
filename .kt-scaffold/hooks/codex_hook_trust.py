#!/usr/bin/env python3
"""Record Codex's own trust for this project's canonical `.codex/hooks.json` hooks.

Codex runs a project hook only after the user trusts its exact definition, and it keeps that trust
only in the user's own `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`) as
`[hooks.state."<abs>/.codex/hooks.json:<event>:<group>:<handler>"] trusted_hash = "sha256:..."`.
The Codex Trust button writes exactly that entry. Creating or updating a project with the factory is
the user's consent to trust that project's hooks, so the project creation and update flows record
the same entries here instead of asking the user to press Trust.

This is the only implementation. The factory package loads this file; the HTTP creation flow asks
the client to run it once, right after it has written the canonical hook file:

    python3.13 .kt-scaffold/hooks/codex_hook_trust.py onayla --ozet <sha256 of .codex/hooks.json>

It writes trust only for the hooks of the project it belongs to, only when the hook file is
byte-identical to the canonical digest it is given, and only Codex's own trust record. It never
uses Codex's trust bypass flag or setting and never touches another project's entries. Every other
byte of the user's configuration is kept; a configuration it cannot edit safely is left unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePath
from typing import Any

# Keep 3.9 syntax: a host python3 older than the profile can still parse and report.

HOOKS_FILE = (".codex", "hooks.json")
CONFIG_FILE = "config.toml"
# Codex's persisted hook-state key label of each event (codex-rs `hook_event_key_label`).
EVENT_KEY_LABELS = {
    "PreToolUse": "pre_tool_use",
    "PermissionRequest": "permission_request",
    "PostToolUse": "post_tool_use",
    "PreCompact": "pre_compact",
    "PostCompact": "post_compact",
    "SessionStart": "session_start",
    "SessionEnd": "session_end",
    "UserPromptSubmit": "user_prompt_submit",
    "SubagentStart": "subagent_start",
    "SubagentStop": "subagent_stop",
    "Stop": "stop",
    "Interrupt": "interrupt",
}
# Events whose matcher Codex ignores, so it is not part of their trust identity.
MATCHERLESS_EVENTS = frozenset({"UserPromptSubmit", "Stop", "Interrupt"})
# Events that may emit additional context; elsewhere Codex drops `additionalContextLimit`.
ADDITIONAL_CONTEXT_EVENTS = frozenset(
    {"PreToolUse", "PostToolUse", "SessionStart", "UserPromptSubmit", "SubagentStart"}
)
DEFAULT_ADDITIONAL_CONTEXT_LIMIT = 2500
DEFAULT_TIMEOUT_SECONDS = 600
SHORT_EVENTS = frozenset({"SessionEnd", "Interrupt"})
SHORT_DEFAULT_TIMEOUT_SECONDS = 1
SHORT_MAX_TIMEOUT_SECONDS = 3
COMMAND_FIELDS = frozenset(
    {
        "type",
        "command",
        "commandWindows",
        "command_windows",
        "timeout",
        "async",
        "statusMessage",
        "additionalContextLimit",
    }
)
# Plain Turkish names of the factory's hook scripts, shown in the one-line result.
HOOK_NAMES = {
    "prompt_ingress_guard": "mesaj denetimi",
    "agentic_review_receipt_guard": "değişiklik kaydı öncesi inceleme denetimi",
    "governance_surface_guard": "yönetişim dosyası koruması",
    "governance_drift_feedback": "yönetişim sapması bildirimi",
    "llm_call_audit_hook": "model çağrısı kaydı",
}
HOOK_TERM = (
    "Codex kancaları (mesaj gönderince veya bir araç çalışınca kendiliğinden çalışan denetimler)"
)
MANUAL_STEP = (
    "VS Code'da Codex kenar çubuğundaki dişli simgesinden Codex Settings'i açıp Hooks bölümünde bu "
    "projenin kancalarını Trust ile onaylayın."
)
PUBLIC_RESULT_FIELDS = ("status", "hooks", "message")
_SCRIPT = re.compile(r"\.kt-scaffold/hooks/([a-z_]+)\.py")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_HEADER = re.compile(
    r"^[ \t]*\[[ \t]*hooks[ \t]*\.[ \t]*state[ \t]*\.[ \t]*"
    r"(?P<key>\"(?:[^\"\\\r\n]|\\.)*\"|'[^'\r\n]*')[ \t]*\][ \t]*(?:#.*)?$"
)
_TRUSTED_HASH = re.compile(r"^(?P<indent>[ \t]*)trusted_hash[ \t]*=")
_TABLE_START = re.compile(r"^[ \t]*\[")


class TrustError(ValueError):
    """A bounded, plain-Turkish reason why no trust was recorded."""


def _is_windows() -> bool:
    return os.name == "nt"


def _toml() -> Any:
    try:
        import tomllib
    except ImportError as exc:  # Python < 3.11
        raise TrustError("bu komut Python 3.11 veya daha yeni bir sürümle çalışmalıdır") from exc
    return tomllib


def _canonical_json(value: object) -> bytes:
    # serde_json of Codex's key-sorted TOML value: no spaces, UTF-8, lower-case `\u00xx` escapes.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _timeout(event: str, value: object) -> int:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
        raise TrustError("kanca dosyasında geçersiz zaman aşımı değeri var")
    if event in SHORT_EVENTS:
        chosen = SHORT_DEFAULT_TIMEOUT_SECONDS if value is None else value
        return min(max(chosen, 1), SHORT_MAX_TIMEOUT_SECONDS)
    return max(DEFAULT_TIMEOUT_SECONDS if value is None else value, 1)


def _normalized_handler(event: str, handler: object, windows: bool) -> dict[str, object] | None:
    """Codex's normalized command handler, or None for a handler Codex skips."""

    if not isinstance(handler, dict) or handler.get("type") != "command":
        raise TrustError("kanca dosyasında yalnız komut kancası bulunabilir")
    unknown = set(handler) - COMMAND_FIELDS
    if unknown or ("commandWindows" in handler and "command_windows" in handler):
        raise TrustError("kanca dosyasında bilinmeyen kanca alanı var")
    command = handler.get("command")
    override = handler.get("commandWindows", handler.get("command_windows"))
    status_message = handler.get("statusMessage")
    run_async = handler.get("async", False)
    limit = handler.get("additionalContextLimit")
    if (
        not isinstance(command, str)
        or (override is not None and not isinstance(override, str))
        or (status_message is not None and not isinstance(status_message, str))
        or not isinstance(run_async, bool)
        or (limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)))
    ):
        raise TrustError("kanca dosyasında geçersiz kanca alanı var")
    if windows and override is not None:
        command = override
    if not command.strip():
        return None
    normalized: dict[str, object] = {
        "type": "command",
        "command": command,
        "timeout": _timeout(event, handler.get("timeout")),
        "async": run_async,
    }
    if status_message is not None:
        normalized["statusMessage"] = status_message
    if (
        event in ADDITIONAL_CONTEXT_EVENTS
        and limit is not None
        and limit != DEFAULT_ADDITIONAL_CONTEXT_LIMIT
    ):
        normalized["additionalContextLimit"] = limit
    return normalized


def _hook_name(event: str, command: object) -> str:
    match = _SCRIPT.search(command) if isinstance(command, str) else None
    if match is not None and match.group(1) in HOOK_NAMES:
        return HOOK_NAMES[match.group(1)]
    return f"{event} kancası"


def hook_trust_hashes(hooks_bytes: bytes, *, windows: bool) -> list[dict[str, object]]:
    """Each hook's Codex trust identity: key suffix, `trusted_hash` and plain name.

    The hash is Codex's `hook_hash`: SHA-256 of the key-sorted compact JSON of
    `{"event_name", "matcher"?, "hooks": [normalized handler]}`.
    """

    try:
        document = json.loads(hooks_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TrustError("kanca dosyası okunamadı") from exc
    events = document.get("hooks") if isinstance(document, dict) else None
    if not isinstance(events, dict) or set(document) - {"description", "hooks"}:
        raise TrustError("kanca dosyası beklenen biçimde değil")
    identities: list[dict[str, object]] = []
    for event, groups in events.items():
        label = EVENT_KEY_LABELS.get(event)
        if label is None or not isinstance(groups, list):
            raise TrustError("kanca dosyasında bilinmeyen kanca olayı var")
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
                raise TrustError("kanca dosyası beklenen biçimde değil")
            matcher = None if event in MATCHERLESS_EVENTS else group.get("matcher")
            if matcher is not None and not isinstance(matcher, str):
                raise TrustError("kanca dosyasında geçersiz eşleştirici var")
            for handler_index, handler in enumerate(group.get("hooks", [])):
                normalized = _normalized_handler(event, handler, windows)
                if normalized is None:
                    continue
                identity: dict[str, object] = {"event_name": label, "hooks": [normalized]}
                if matcher is not None:
                    identity["matcher"] = matcher
                identities.append(
                    {
                        "suffix": f"{label}:{group_index}:{handler_index}",
                        "trusted_hash": "sha256:"
                        + hashlib.sha256(_canonical_json(identity)).hexdigest(),
                        "name": _hook_name(event, normalized["command"]),
                    }
                )
    if not identities:
        raise TrustError("kanca dosyasında onaylanacak kanca yok")
    return identities


def hook_file_keys(project_root: PurePath, *, windows: bool) -> list[str]:
    """The hook-file part of Codex's trust key, for this project's absolute path only.

    Codex keys trust by the hook file path it discovers. On Windows the same file may be reached as
    `C:\\...` or `c:\\...` (openai/codex#40360), so both spellings of the one path are recorded.
    Codex drops a `\\\\?\\` device prefix from a drive path, so it is dropped here too.
    """

    hooks_path = str(project_root.joinpath(*HOOKS_FILE))
    if windows and hooks_path.startswith("\\\\?\\") and hooks_path[5:6] == ":":
        hooks_path = hooks_path[4:]
    if not windows or len(hooks_path) < 2 or hooks_path[1] != ":":
        return [hooks_path]
    return [hooks_path[0].upper() + hooks_path[1:], hooks_path[0].lower() + hooks_path[1:]]


def codex_config_path(environ: dict[str, str] | None = None) -> Path:
    """`$CODEX_HOME/config.toml`, else `~/.codex/config.toml`, as Codex resolves its home."""

    source = os.environ if environ is None else environ
    configured = source.get("CODEX_HOME", "")
    if configured:
        home = Path(configured)
        if not home.is_dir():
            raise TrustError("CODEX_HOME ile gösterilen Codex ayar klasörü bulunamadı")
        return home.resolve() / CONFIG_FILE
    return Path.home() / ".codex" / CONFIG_FILE


def _basic_string(value: str) -> str:
    escaped = []
    for character in value:
        code = ord(character)
        if character in {'"', "\\"}:
            escaped.append("\\" + character)
        elif code < 0x20 or code == 0x7F:
            escaped.append(f"\\u{code:04X}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def _hook_states(data: dict[str, Any]) -> dict[str, Any]:
    hooks = data.get("hooks", {})
    state = hooks.get("state", {}) if isinstance(hooks, dict) else None
    if not isinstance(state, dict):
        raise TrustError("Codex ayar dosyasındaki kanca onayı bölümü beklenen biçimde değil")
    return state


def _set_hash(text: str, key: str, trusted_hash: str, newline: str) -> str:
    """Set one existing standard table's `trusted_hash`, keeping every other line."""

    tomllib = _toml()
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        header = _HEADER.match(line.rstrip("\r\n"))
        if header is None:
            continue
        try:
            decoded = tomllib.loads("k = " + header.group("key"))["k"]
        except tomllib.TOMLDecodeError:
            continue
        if decoded != key:
            continue
        end = index + 1
        while end < len(lines) and not _TABLE_START.match(lines[end]):
            end += 1
        for position in range(index + 1, end):
            current = _TRUSTED_HASH.match(lines[position])
            if current is not None:
                ending = lines[position][len(lines[position].rstrip("\r\n")) :] or newline
                lines[position] = (
                    f"{current.group('indent')}trusted_hash = {_basic_string(trusted_hash)}{ending}"
                )
                return "".join(lines)
        if not line.endswith(("\n", "\r")):
            lines[index] = line + newline
        lines.insert(index + 1, f"trusted_hash = {_basic_string(trusted_hash)}{newline}")
        return "".join(lines)
    raise TrustError("Codex ayar dosyasındaki kanca onayı bölümü beklenen biçimde değil")


def _updated_config(original: str, entries: dict[str, str]) -> tuple[str, list[str]]:
    """Return the edited text and the keys whose trust it records or refreshes.

    Only `trusted_hash` of the given keys changes; an existing `enabled` choice stays. The result
    must parse to exactly the original data plus those values, or nothing is written.
    """

    tomllib = _toml()
    try:
        data = tomllib.loads(original)
    except tomllib.TOMLDecodeError as exc:
        raise TrustError("Codex ayar dosyası okunamadı (geçerli TOML değil)") from exc
    states = _hook_states(data)
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original
    changed: list[str] = []
    for key, trusted_hash in entries.items():
        current = states.get(key)
        if current is not None and not isinstance(current, dict):
            raise TrustError("Codex ayar dosyasındaki kanca onayı bölümü beklenen biçimde değil")
        if current is not None and current.get("trusted_hash") == trusted_hash:
            continue
        changed.append(key)
        if current is None:
            if text and not text.endswith(("\n", "\r")):
                text += newline
            separator = newline if text.strip() else ""
            text += (
                f"{separator}[hooks.state.{_basic_string(key)}]{newline}"
                f"trusted_hash = {_basic_string(trusted_hash)}{newline}"
            )
        else:
            text = _set_hash(text, key, trusted_hash, newline)
    if not changed:
        return original, []
    expected = copy.deepcopy(data)
    expected_states = expected.setdefault("hooks", {}).setdefault("state", {})
    for key in changed:
        expected_states.setdefault(key, {})["trusted_hash"] = entries[key]
    try:
        edited = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TrustError("Codex ayar dosyası güvenle düzenlenemedi; dosya değiştirilmedi") from exc
    if edited != expected:
        raise TrustError("Codex ayar dosyası güvenle düzenlenemedi; dosya değiştirilmedi")
    return text, changed


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _write_atomically(path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".config.toml.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _record_entries(config: Path, entries: dict[str, str]) -> list[str]:
    """Upsert the entries; retry once if Codex changed the file while this edit was prepared."""

    if config.is_symlink():
        # A linked dotfile stays linked; its target is edited in place.
        config = config.resolve(strict=True)
    if config.parent == Path.home() / ".codex" and not config.parent.exists():
        config.parent.mkdir(mode=0o700)
    for _attempt in range(2):
        before = _read(config)
        try:
            original = "" if before is None else before.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrustError("Codex ayar dosyası okunamadı (UTF-8 değil)") from exc
        text, changed = _updated_config(original, entries)
        if not changed:
            return []
        mode = 0o600 if before is None else stat.S_IMODE(config.stat().st_mode)
        if _read(config) != before:
            continue
        _write_atomically(config, text.encode("utf-8"), mode)
        return changed
    raise TrustError("Codex ayar dosyası bu sırada başka bir işlemce değiştirildi")


def _names(identities: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    for identity in identities:
        name = str(identity["name"])
        if name not in names:
            names.append(name)
    return names


def _joined(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ve " + names[-1]


def record_project_hook_trust(
    project_root: Path,
    expected_sha256: str,
    *,
    environ: dict[str, str] | None = None,
    windows: bool | None = None,
) -> dict[str, object]:
    """Trust this project's canonical Codex hooks in the user's own Codex configuration."""

    selected_windows = _is_windows() if windows is None else windows
    try:
        if _SHA256.fullmatch(expected_sha256) is None:
            raise TrustError("beklenen kanca dosyası özeti geçersiz")
        root = project_root.resolve(strict=True)
        hooks_path = root.joinpath(*HOOKS_FILE)
        if hooks_path.is_symlink() or not hooks_path.is_file():
            raise TrustError("bu projede Codex kanca dosyası (`.codex/hooks.json`) yok")
        hooks_bytes = hooks_path.read_bytes()
        if hashlib.sha256(hooks_bytes).hexdigest() != expected_sha256:
            raise TrustError(
                "Codex kanca dosyası (`.codex/hooks.json`) fabrikanın ürettiği içerikte değil"
            )
        identities = hook_trust_hashes(hooks_bytes, windows=selected_windows)
        entries = {
            f"{source}:{identity['suffix']}": str(identity["trusted_hash"])
            for source in hook_file_keys(root, windows=selected_windows)
            for identity in identities
        }
        changed = _record_entries(codex_config_path(environ), entries)
    except (TrustError, OSError) as exc:
        reason = str(exc) if isinstance(exc, TrustError) else "Codex ayar dosyası yazılamadı"
        return {
            "status": "failed",
            "hooks": [],
            "message": f"{HOOK_TERM} bu proje için onaylanamadı: {reason}. {MANUAL_STEP}",
        }
    names = _names(identities)
    if not changed:
        return {
            "status": "unchanged",
            "hooks": names,
            "message": (
                f"{HOOK_TERM} bu proje için zaten onaylıydı: {_joined(names)}; Codex ayarlarınız "
                "değiştirilmedi."
            ),
        }
    return {
        "status": "recorded",
        "hooks": names,
        "message": (
            f"{HOOK_TERM} bu proje için onaylandı: {_joined(names)}. Onay, projeyi oluşturma veya "
            "güncelleme isteğinize dayanarak yalnız bu projenin kancaları için Codex ayarlarınıza "
            "yazıldı."
        ),
    }


def public_result(result: dict[str, object]) -> dict[str, object]:
    """The allow-listed fields of a trust result, as the command prints them."""

    return {name: result[name] for name in PUBLIC_RESULT_FIELDS if name in result}


def main(arguments: list[str] | None = None) -> int:
    selected = sys.argv[1:] if arguments is None else arguments
    if len(selected) != 3 or selected[:2] != ["onayla", "--ozet"]:
        print("usage: codex_hook_trust.py onayla --ozet <sha256>", file=sys.stderr)
        return 2
    root = Path(__file__).resolve(strict=True).parents[2]
    result = record_project_hook_trust(root, selected[2])
    print(json.dumps(public_result(result), ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"recorded", "unchanged"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
