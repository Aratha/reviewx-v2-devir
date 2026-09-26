#!/usr/bin/env python3
"""Thin generated launcher for the canonical kt-scaffold commit governance guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _selected_client() -> str | None:
    try:
        index = sys.argv.index("--client")
        return sys.argv[index + 1]
    except (ValueError, IndexError):
        return None


def _native_hook_mode() -> bool:
    return "--native-hook" in sys.argv[1:]


def _missing_runtime_output(client_id: str | None) -> dict[str, object]:
    message = (
        "GOVERNED_REVIEW_REQUIRED: COMMIT_GOVERNANCE_RUNTIME_UNAVAILABLE. "
        "Güvenilen kt-scaffold runtime'ını doğrulayın."
    )
    if client_id == "cursor":
        return {
            "permission": "deny",
            "user_message": message,
            "agent_message": message,
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": message,
        }
    }


def main() -> int:
    # Generated projects can verify the launcher without importing the trusted
    # kt-scaffold runtime. Actual hook decisions remain fail-closed when that
    # runtime is unavailable.
    if sys.argv[1:] == ["--self-check"]:
        print(json.dumps({"agent_invocation": False, "network": False, "ok": True}, sort_keys=True))
        return 0
    project_root = Path(__file__).resolve(strict=True).parents[2]
    try:
        from kt_scaffold.agent_platform.commit_governance import main as canonical_main
    except Exception:
        if _native_hook_mode():
            print(json.dumps(_missing_runtime_output(_selected_client()), separators=(",", ":")))
            return 0
        print(
            "GOVERNED_REVIEW_REQUIRED: COMMIT_GOVERNANCE_RUNTIME_UNAVAILABLE. "
            "Güvenilen kt-scaffold runtime'ını doğrulayın.",
            file=sys.stderr,
        )
        return 1
    return canonical_main(default_project_root=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
