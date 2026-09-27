"""Import the previous application's review rules once, as version 1 and the draft.

Data-only revision for sql-review/PRDs/001-rule-management Requirement 9 (Decision 3). It reads
the committed copy ``schema/alembic/data/review_rules.json``, refuses to run unless the copy has
the pinned SHA-256 and every identifier is a KuralNN code, and writes nothing when the platform
tenant already has a draft or a version. Codes, groups, order, texts and flags are kept exactly.
Downgrade keeps the rules: published versions are immutable and the draft may have been edited.

Revision ID: 202609260002
Revises: 202609260001
Create Date: 2026-09-26 19:30:00.000000
"""

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

from app.core.logging import log_event
from app.domain.rule_set import Rule, RuleGroups, content_sha256, rule_number

revision: str = "202609260002"
down_revision: str | None = "202609260001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULE_FILE = Path(__file__).resolve().parents[1] / "data" / "review_rules.json"
RULE_FILE_SHA256 = "2346ad4769259b5a09b4d1c742ec0a6f3d575cdb054bf126fb395cdc709a25eb"
_RULE_TEXT_MAX_LENGTH = 8000
_IMPORT_SOURCE = "ice-aktarim"

logger = logging.getLogger("app.rule_set")

_draft = sa.table(
    "rule_set_draft",
    sa.column("rule_set_draft_id", sa.BigInteger),
    sa.column("tenant_id", sa.BigInteger),
    sa.column("revision", sa.Integer),
    sa.column("next_rule_number", sa.Integer),
)
_draft_rule = sa.table(
    "rule_set_draft_rule",
    sa.column("rule_set_draft_id", sa.BigInteger),
    sa.column("rule_code", sa.String),
    sa.column("priority_group", sa.String),
    sa.column("position", sa.Integer),
    sa.column("rule_text", sa.Text),
    sa.column("requires_metadata", sa.Boolean),
)
_version = sa.table(
    "rule_set_version",
    sa.column("rule_set_version_id", sa.BigInteger),
    sa.column("public_id", sa.Text),
    sa.column("tenant_id", sa.BigInteger),
    sa.column("number", sa.Integer),
    sa.column("published_at", sa.DateTime(timezone=True)),
    sa.column("published_by_user_id", sa.BigInteger),
    sa.column("source", sa.String),
    sa.column("content_sha256", sa.String),
)
_version_rule = sa.table(
    "rule_set_version_rule",
    sa.column("rule_set_version_id", sa.BigInteger),
    sa.column("rule_code", sa.String),
    sa.column("priority_group", sa.String),
    sa.column("position", sa.Integer),
    sa.column("rule_text", sa.Text),
    sa.column("requires_metadata", sa.Boolean),
)


class RuleImportError(RuntimeError):
    """The committed rule file cannot be imported; the migration stops."""


def _groups(bundle: object, label: str) -> RuleGroups:
    if not isinstance(bundle, dict) or set(bundle) != {"critical", "normal"}:
        raise RuleImportError(f"{label} must hold exactly the critical and normal groups")
    groups: list[tuple[Rule, ...]] = []
    for group in ("critical", "normal"):
        entries = bundle[group]
        if not isinstance(entries, list):
            raise RuleImportError(f"{label}.{group} must be a list")
        rules: list[Rule] = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "text", "requires_metadata"}:
                raise RuleImportError(f"{label}.{group} holds a malformed rule")
            code, text, flag = entry["id"], entry["text"], entry["requires_metadata"]
            if not isinstance(code, str) or rule_number(code) is None:
                raise RuleImportError(f"{label}.{group} holds an identifier outside KuralNN")
            if not isinstance(text, str) or not 1 <= len(text) <= _RULE_TEXT_MAX_LENGTH:
                raise RuleImportError(f"{label}.{group} holds a rule text of invalid length")
            if not isinstance(flag, bool):
                raise RuleImportError(f"{label}.{group} holds a non-boolean metadata flag")
            rules.append(Rule(code, text, flag))
        groups.append(tuple(rules))
    result = RuleGroups(critical=groups[0], normal=groups[1])
    if len(result.codes) != len(result.critical) + len(result.normal):
        raise RuleImportError(f"{label} repeats an identifier")
    return result


def read_rule_file(path: Path, expected_sha256: str) -> tuple[RuleGroups, RuleGroups, datetime]:
    """Return the published rules, the draft rules and the publication time of the file."""

    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RuleImportError("the rule file does not match its pinned SHA-256")
    payload: Any = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"draft", "published", "published_at"}:
        raise RuleImportError("the rule file must hold draft, published and published_at")
    published_at_text = payload["published_at"]
    if not isinstance(published_at_text, str) or not published_at_text.endswith("Z"):
        raise RuleImportError("published_at must be a UTC timestamp")
    published_at = datetime.fromisoformat(published_at_text)
    return (
        _groups(payload["published"], "published"),
        _groups(payload["draft"], "draft"),
        published_at,
    )


def import_rule_file(
    connection: Connection, *, tenant_id: int, path: Path, expected_sha256: str
) -> str:
    """Import the file for one tenant; return 'imported' or 'skipped' (tables not empty)."""

    published, draft, published_at = read_rule_file(path, expected_sha256)
    if published.is_empty:
        raise RuleImportError("the published rule set of the file is empty")
    existing = connection.execute(
        sa.select(
            sa.exists().where(_draft.c.tenant_id == tenant_id)
            | sa.exists().where(_version.c.tenant_id == tenant_id)
        )
    ).scalar_one()
    if existing:
        return "skipped"

    numbers = [rule_number(code) or 0 for code in published.codes | draft.codes]
    version_id = connection.execute(
        sa.insert(_version)
        .values(
            public_id=sa.text("gen_random_uuid()::text"),
            tenant_id=tenant_id,
            number=1,
            published_at=published_at,
            published_by_user_id=None,
            source=_IMPORT_SOURCE,
            content_sha256=content_sha256(published),
        )
        .returning(_version.c.rule_set_version_id)
    ).scalar_one()
    draft_id = connection.execute(
        sa.insert(_draft)
        .values(tenant_id=tenant_id, revision=0, next_rule_number=max(numbers) + 1)
        .returning(_draft.c.rule_set_draft_id)
    ).scalar_one()
    for table, key, owner, rules in (
        (_version_rule, "rule_set_version_id", version_id, published),
        (_draft_rule, "rule_set_draft_id", draft_id, draft),
    ):
        rows = [
            {
                key: owner,
                "rule_code": rule.code,
                "priority_group": group.value,
                "position": position,
                "rule_text": rule.text,
                "requires_metadata": rule.requires_metadata,
            }
            for group, members in rules.grouped()
            for position, rule in enumerate(members)
        ]
        if rows:
            connection.execute(sa.insert(table), rows)
    return "imported"


def upgrade() -> None:
    connection = op.get_bind()
    tenant_id = connection.execute(
        sa.text("SELECT tenant_id FROM tenant WHERE code = 'platform' AND is_deleted = false")
    ).scalar_one_or_none()
    try:
        if tenant_id is None:
            raise RuleImportError("the platform tenant is missing")
        outcome = import_rule_file(
            connection, tenant_id=tenant_id, path=RULE_FILE, expected_sha256=RULE_FILE_SHA256
        )
    except (RuleImportError, OSError, ValueError) as error:
        log_event(logger, "rule_set.import", outcome="failed", error_type=type(error).__name__)
        raise
    log_event(logger, "rule_set.import", outcome=outcome)


def downgrade() -> None:
    # Published versions are immutable (Requirement 5) and the draft may already be edited, so
    # the imported rules stay; a repeated upgrade writes nothing because the tables are not empty.
    pass
