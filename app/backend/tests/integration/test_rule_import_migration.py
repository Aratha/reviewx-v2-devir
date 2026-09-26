"""One-time import of the previous application's rule file (revision 202609260002).

sql-review/PRDs/001-rule-management Requirement 9 (Acceptance 2): empty tables, filled tables and
a corrupt copy. Each case runs in a rolled-back transaction for a fresh tenant.
"""

import hashlib
import importlib.util
import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.session import engine
from app.domain.rule_set import Rule, RuleGroups, content_sha256

pytestmark = pytest.mark.integration

VERSIONS = Path(__file__).resolve().parents[4] / "schema" / "alembic" / "versions"
PINNED_SHA256 = "2346ad4769259b5a09b4d1c742ec0a6f3d575cdb054bf126fb395cdc709a25eb"


def _migration() -> ModuleType:
    path = VERSIONS / "202609260002_import_previous_review_rules.py"
    spec = importlib.util.spec_from_file_location("rule_import_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def connection(migrated_database: None) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        try:
            yield conn
        finally:
            await transaction.rollback()


async def _new_tenant(conn: AsyncConnection) -> int:
    tenant_id = await conn.scalar(
        text(
            "INSERT INTO tenant (public_id, code, name) "
            "VALUES (gen_random_uuid()::text, :code, 'Deneme') RETURNING tenant_id"
        ),
        {"code": f"import-{uuid4().hex[:10]}"},
    )
    return int(tenant_id)


async def _run(
    conn: AsyncConnection, migration: ModuleType, tenant_id: int, path: Path, sha256: str
) -> str:
    def call(sync: Connection) -> str:
        outcome: str = migration.import_rule_file(
            sync, tenant_id=tenant_id, path=path, expected_sha256=sha256
        )
        return outcome

    return await conn.run_sync(call)


async def _rule_rows(conn: AsyncConnection, tenant_id: int) -> dict[str, Any]:
    versions = (
        await conn.execute(
            text(
                "SELECT rule_set_version_id, number, source, published_by_user_id, "
                "published_at, content_sha256 FROM rule_set_version WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        )
    ).all()
    drafts = (
        await conn.execute(
            text(
                "SELECT rule_set_draft_id, revision, next_rule_number FROM rule_set_draft "
                "WHERE tenant_id = :t"
            ),
            {"t": tenant_id},
        )
    ).all()
    return {"versions": versions, "drafts": drafts}


async def _rules(conn: AsyncConnection, table: str, key: str, owner: int) -> RuleGroups:
    rows = (
        await conn.execute(
            text(
                f"SELECT priority_group, rule_code, rule_text, requires_metadata FROM {table} "
                f"WHERE {key} = :owner ORDER BY priority_group, position"
            ),
            {"owner": owner},
        )
    ).all()
    return RuleGroups(
        critical=tuple(Rule(r[1], r[2], r[3]) for r in rows if r[0] == "critical"),
        normal=tuple(Rule(r[1], r[2], r[3]) for r in rows if r[0] == "normal"),
    )


def _file_groups(bundle: dict[str, Any]) -> RuleGroups:
    return RuleGroups(
        critical=tuple(
            Rule(r["id"], r["text"], r["requires_metadata"]) for r in bundle["critical"]
        ),
        normal=tuple(Rule(r["id"], r["text"], r["requires_metadata"]) for r in bundle["normal"]),
    )


async def test_empty_tables_receive_version_one_and_the_draft_exactly(
    connection: AsyncConnection,
) -> None:
    migration = _migration()
    assert migration.RULE_FILE_SHA256 == PINNED_SHA256
    source = json.loads(migration.RULE_FILE.read_text(encoding="utf-8"))
    tenant_id = await _new_tenant(connection)

    outcome = await _run(connection, migration, tenant_id, migration.RULE_FILE, PINNED_SHA256)

    assert outcome == "imported"
    rows = await _rule_rows(connection, tenant_id)
    ((version_id, number, source_kind, publisher, published_at, digest),) = rows["versions"]
    ((draft_id, revision, next_number),) = rows["drafts"]
    assert (number, source_kind, publisher) == (1, "ice-aktarim", None)
    assert published_at.isoformat() == "2026-04-10T14:05:15+00:00"
    published = await _rules(connection, "rule_set_version_rule", "rule_set_version_id", version_id)
    draft = await _rules(connection, "rule_set_draft_rule", "rule_set_draft_id", draft_id)
    assert published == _file_groups(source["published"])
    assert draft == _file_groups(source["draft"])
    assert (len(published.critical), len(published.normal)) == (10, 1)
    assert "Kural02" not in published.codes
    assert digest == content_sha256(published)
    assert (revision, next_number) == (0, 13)


async def test_filled_tables_make_the_import_write_nothing(connection: AsyncConnection) -> None:
    migration = _migration()
    tenant_id = await _new_tenant(connection)
    assert await _run(connection, migration, tenant_id, migration.RULE_FILE, PINNED_SHA256) == (
        "imported"
    )
    before = await _rule_rows(connection, tenant_id)

    repeated = await _run(connection, migration, tenant_id, migration.RULE_FILE, PINNED_SHA256)

    assert repeated == "skipped"
    assert await _rule_rows(connection, tenant_id) == before


async def test_a_tenant_with_its_own_rules_is_not_overwritten(
    connection: AsyncConnection,
) -> None:
    migration = _migration()
    tenant_id = await _new_tenant(connection)
    await connection.execute(
        text("INSERT INTO rule_set_draft (tenant_id, revision) VALUES (:t, 4)"), {"t": tenant_id}
    )

    outcome = await _run(connection, migration, tenant_id, migration.RULE_FILE, PINNED_SHA256)

    assert outcome == "skipped"
    rows = await _rule_rows(connection, tenant_id)
    assert rows["versions"] == []
    assert [row[1] for row in rows["drafts"]] == [4]


def _corrupt_copies(tmp_path: Path, original: bytes) -> list[tuple[Path, str]]:
    changed = tmp_path / "changed.json"
    changed.write_bytes(original.replace(b"NOLOCK", b"NOLOCX", 1))
    foreign = tmp_path / "foreign.json"
    payload = json.loads(original)
    payload["published"]["critical"][0]["id"] = "Rule01"
    foreign.write_text(json.dumps(payload), encoding="utf-8")
    return [
        # The committed pin no longer matches the bytes.
        (changed, PINNED_SHA256),
        # Even a copy whose own digest is supplied must hold only KuralNN identifiers.
        (foreign, hashlib.sha256(foreign.read_bytes()).hexdigest()),
    ]


async def test_a_corrupt_copy_stops_the_migration_without_writing(
    connection: AsyncConnection, tmp_path: Path
) -> None:
    migration = _migration()
    for path, sha256 in _corrupt_copies(tmp_path, migration.RULE_FILE.read_bytes()):
        tenant_id = await _new_tenant(connection)
        with pytest.raises(migration.RuleImportError):
            await _run(connection, migration, tenant_id, path, sha256)
        assert await _rule_rows(connection, tenant_id) == {"versions": [], "drafts": []}
