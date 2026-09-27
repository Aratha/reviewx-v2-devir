#!/usr/bin/env python3
"""Emit bounded project metadata for the global governance MCP; never inspect source files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".kt-scaffold" / "project-manifest.json"
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid project metadata: {exc}") from exc

required = {
    "format",
    "blueprint_id",
    "blueprint_version",
    "project_intent",
    "primary_domain",
    "application_mode",
    "backend_profile",
    "persistence_profile",
    "locales",
    "authority_generation",
    "governance_version",
    "governance_digest",
    "artifacts",
}
if not isinstance(payload, dict) or not required <= payload.keys():
    raise SystemExit("invalid project metadata: required fields are missing")
encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
if len(encoded.encode()) > 256 * 1024:
    raise SystemExit("invalid project metadata: 262144-byte limit exceeded")
sys.stdout.write(encoded + "\n")
