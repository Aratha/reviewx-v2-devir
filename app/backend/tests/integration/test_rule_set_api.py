"""Rule-set draft, publish and published-version API against real PostgreSQL.

sql-review/PRDs/001-rule-management Requirement 1-9 (Acceptance 1). The platform tenant's draft
is shared by the tests, so each test reads the current revision before changing it.
"""

import asyncio
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.db.session import async_session_factory
from app.domain.models.rule_set import RuleSetVersion
from app.domain.models.tenant import Tenant
from app.services.rule_set_service import RuleSetService
from tests.integration.conftest import (
    AuthHarness,
    RoleSession,
    RoleSessions,
    SuperAdmin,
)

pytestmark = pytest.mark.integration

RULE_FILE = (
    Path(__file__).resolve().parents[4] / "schema" / "alembic" / "data" / "review_rules.json"
)


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(
            json.dumps(
                {"message": record.getMessage(), **getattr(record, "structured_fields", {})},
                ensure_ascii=False,
            )
        )


@pytest.fixture
def rule_logs() -> Iterator[_Records]:
    handler = _Records()
    loggers = [logging.getLogger(name) for name in ("app.rule_set", "app.http")]
    levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        for logger, level in zip(loggers, levels, strict=True):
            logger.removeHandler(handler)
            logger.setLevel(level)


def _rule(code: str, text_value: str, flag: bool = False) -> dict[str, Any]:
    return {"id": code, "text": text_value, "requires_metadata": flag}


async def _workspace(auth: AuthHarness, manager: RoleSession) -> dict[str, Any]:
    response = await auth.client.get(f"{auth.prefix}/rule-set", headers=manager.headers)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _save(
    auth: AuthHarness,
    manager: RoleSession,
    revision: int,
    critical: list[dict[str, Any]],
    normal: list[dict[str, Any]] | None = None,
) -> Any:
    return await auth.client.put(
        f"{auth.prefix}/rule-set/draft",
        json={"base_revision": revision, "critical": critical, "normal": normal or []},
        headers=manager.headers,
    )


def _next(code: str, step: int = 0) -> str:
    number = int(code.removeprefix("Kural")) + step
    return f"Kural{number:02d}"


async def test_imported_file_is_version_one_for_both_roles(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    source = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    for session in (await role_sessions.reviewer(), await role_sessions.rule_manager()):
        response = await auth.client.get(
            f"{auth.prefix}/rule-set/versions/1", headers=session.headers
        )
        assert response.status_code == 200, response.text
        version = response.json()
        assert version["source"] == "ice-aktarim"
        assert version["published_by_name"] is None
        assert version["published_at"].startswith("2026-04-10T14:05:15")
        assert (version["critical_count"], version["normal_count"]) == (10, 1)
        assert version["critical"] == source["published"]["critical"]
        assert version["normal"] == source["published"]["normal"]


async def test_workspace_shows_draft_latest_version_and_next_free_code(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    workspace = await _workspace(auth, manager)

    assert isinstance(workspace["revision"], int)
    assert workspace["latest_version"]["number"] >= 1
    assert workspace["next_rule_id"].startswith("Kural")
    assert int(workspace["next_rule_id"][5:]) >= 13
    codes = [rule["id"] for rule in workspace["critical"] + workspace["normal"]]
    assert all(int(code[5:]) < int(workspace["next_rule_id"][5:]) for code in codes)


async def test_save_trims_drops_blank_rules_and_counts_revisions(
    auth: AuthHarness, role_sessions: RoleSessions, rule_logs: _Records
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    new_code = before["next_rule_id"]
    secret_text = f"kural-metni-{uuid4().hex}"

    response = await _save(
        auth,
        manager,
        before["revision"],
        [*before["critical"], _rule(new_code, f"  {secret_text}  ", True)],
        [*before["normal"], _rule(_next(new_code, 1), "   ")],
    )

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["revision"] == before["revision"] + 1
    assert after["critical"][-1] == _rule(new_code, secret_text, True)
    assert after["normal"] == before["normal"]
    assert after["next_rule_id"] == _next(new_code, 1)
    assert after["draft_differs"] is True
    assert after["latest_version"] == before["latest_version"]
    assert all(secret_text not in line for line in rule_logs.lines)
    saved = [line for line in rule_logs.lines if "rule_set.draft_saved" in line]
    assert saved and manager.public_id in saved[-1]


async def test_stale_revision_is_a_conflict_and_writes_nothing(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    first = await _save(auth, manager, before["revision"], before["critical"], before["normal"])
    assert first.status_code == 200

    stale = await _save(
        auth,
        manager,
        before["revision"],
        [*before["critical"], _rule(before["next_rule_id"], "yarış")],
        before["normal"],
    )
    stale_publish = await auth.client.post(
        f"{auth.prefix}/rule-set/versions",
        json={"base_revision": before["revision"]},
        headers=manager.headers,
    )

    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "rule_set_draft_conflict",
        "message": "Kurallar başka biri tarafından değiştirildi; sayfayı yenileyin.",
    }
    assert stale_publish.status_code == 409
    after = await _workspace(auth, manager)
    assert after["revision"] == before["revision"] + 1
    assert after["critical"] == before["critical"]


async def test_invalid_codes_and_limits_are_rejected_without_writing(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    fresh = before["next_rule_id"]
    cases = [
        ([_rule("Kural7", "x")], "rule_id_invalid"),
        ([_rule(fresh, "x"), _rule(fresh, "y")], "rule_id_duplicate"),
        ([_rule("Kural02", "x")], "rule_id_reused"),
        ([_rule(fresh, "x" * 8001)], "rule_text_too_long"),
        ([_rule(f"Kural{n}", "x") for n in range(200, 401)], "rule_set_too_large"),
    ]
    for critical, code in cases:
        response = await _save(auth, manager, before["revision"], critical)
        assert response.status_code == 422, (code, response.text)
        assert response.json()["detail"]["code"] == code
    malformed = await auth.client.put(
        f"{auth.prefix}/rule-set/draft", json={"critical": []}, headers=manager.headers
    )
    assert malformed.status_code == 422
    assert malformed.json() == {
        "detail": {"code": "invalid_request", "message": "İstek değerleri geçersiz."}
    }
    assert await _workspace(auth, manager) == before


async def test_a_removed_code_is_never_given_to_a_new_rule(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    code = before["next_rule_id"]
    added = await _save(
        auth, manager, before["revision"], [*before["critical"], _rule(code, "geçici")]
    )
    assert added.status_code == 200
    removed = await _save(auth, manager, added.json()["revision"], before["critical"])
    assert removed.status_code == 200
    assert removed.json()["next_rule_id"] == _next(code, 1)

    reused = await _save(
        auth, manager, removed.json()["revision"], [*before["critical"], _rule(code, "yeniden")]
    )

    assert reused.status_code == 422
    assert reused.json()["detail"]["code"] == "rule_id_reused"


async def test_publish_creates_numbered_immutable_versions_and_repeats_idempotently(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    reviewer = await role_sessions.reviewer()
    before = await _workspace(auth, manager)
    marker = uuid4().hex
    saved = await _save(
        auth,
        manager,
        before["revision"],
        [*before["critical"], _rule(before["next_rule_id"], f"yayın {marker}")],
        before["normal"],
    )
    revision = saved.json()["revision"]
    previous_number = before["latest_version"]["number"]
    previous = await auth.client.get(
        f"{auth.prefix}/rule-set/versions/{previous_number}", headers=reviewer.headers
    )

    created = await auth.client.post(
        f"{auth.prefix}/rule-set/versions",
        json={"base_revision": revision},
        headers=manager.headers,
    )
    repeated = await auth.client.post(
        f"{auth.prefix}/rule-set/versions",
        json={"base_revision": revision},
        headers=manager.headers,
    )

    assert created.status_code == 201, created.text
    version = created.json()
    assert version["number"] == previous_number + 1
    assert version["source"] == "arayuz"
    assert version["published_by_name"] == manager.display_name
    assert version["critical"][-1]["text"] == f"yayın {marker}"
    assert repeated.status_code == 200
    assert repeated.json() == version
    workspace = await _workspace(auth, manager)
    assert workspace["draft_differs"] is False
    assert workspace["latest_version"]["number"] == version["number"]
    assert workspace["revision"] == revision

    # Later draft changes never touch a published version.
    await _save(auth, manager, revision, before["critical"], before["normal"])
    again = await auth.client.get(
        f"{auth.prefix}/rule-set/versions/{previous_number}", headers=reviewer.headers
    )
    assert again.json() == previous.json()
    latest = await auth.client.get(
        f"{auth.prefix}/rule-set/versions/latest", headers=reviewer.headers
    )
    assert latest.json() == version


async def test_concurrent_publishes_of_one_draft_create_one_version(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    saved = await _save(
        auth,
        manager,
        before["revision"],
        [*before["critical"], _rule(before["next_rule_id"], f"eşzamanlı {uuid4().hex}")],
        before["normal"],
    )
    revision = saved.json()["revision"]

    responses = await asyncio.gather(
        *(
            auth.client.post(
                f"{auth.prefix}/rule-set/versions",
                json={"base_revision": revision},
                headers=manager.headers,
            )
            for _ in range(2)
        )
    )

    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["number"] for response in responses}) == 1


async def test_an_empty_draft_cannot_be_published(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    before = await _workspace(auth, manager)
    emptied = await _save(auth, manager, before["revision"], [], [])
    assert emptied.status_code == 200

    response = await auth.client.post(
        f"{auth.prefix}/rule-set/versions",
        json={"base_revision": emptied.json()["revision"]},
        headers=manager.headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "rule_set_empty"
    # Removed rules keep their codes used (Requirement 3); the draft is refilled with fresh codes.
    refilled = await _save(
        auth,
        manager,
        emptied.json()["revision"],
        [_rule(emptied.json()["next_rule_id"], "yeniden doldurulan kural")],
    )
    assert refilled.status_code == 200


async def test_versions_are_listed_newest_first_with_counts(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    reviewer = await role_sessions.reviewer()
    response = await auth.client.get(
        f"{auth.prefix}/rule-set/versions", params={"page_size": 2}, headers=reviewer.headers
    )

    assert response.status_code == 200, response.text
    page = response.json()
    assert page["page"] == 1 and page["page_size"] == 2
    assert page["total"] >= 1
    numbers = [item["number"] for item in page["items"]]
    assert numbers == sorted(numbers, reverse=True)
    oldest = await auth.client.get(
        f"{auth.prefix}/rule-set/versions",
        params={"page": page["total"], "page_size": 1},
        headers=reviewer.headers,
    )
    assert oldest.json()["items"][0]["number"] == 1
    assert oldest.json()["items"][0]["critical_count"] == 10
    for params in ({"page": 0}, {"page_size": 101}):
        invalid = await auth.client.get(
            f"{auth.prefix}/rule-set/versions", params=params, headers=reviewer.headers
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "invalid_request"


async def test_unknown_version_is_not_found(auth: AuthHarness, role_sessions: RoleSessions) -> None:
    reviewer = await role_sessions.reviewer()
    response = await auth.client.get(
        f"{auth.prefix}/rule-set/versions/999999", headers=reviewer.headers
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "rule_set_version_not_found"


async def test_roles_are_enforced_on_every_endpoint(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    reviewer = await role_sessions.reviewer()
    manager_only = [
        ("GET", "/rule-set", None),
        ("PUT", "/rule-set/draft", {"base_revision": 0}),
        ("POST", "/rule-set/versions", {"base_revision": 0}),
    ]
    both = [
        ("GET", "/rule-set/versions", None),
        ("GET", "/rule-set/versions/latest", None),
        ("GET", "/rule-set/versions/1", None),
    ]
    tenant_only = {auth.settings.tenant_header: reviewer.headers[auth.settings.tenant_header]}
    for method, path, body in manager_only + both:
        anonymous = await auth.client.request(
            method, f"{auth.prefix}{path}", json=body, headers=tenant_only
        )
        assert anonymous.status_code == 401, path
        assert anonymous.json()["detail"]["code"] == "not_authenticated"
    for method, path, body in manager_only:
        forbidden = await auth.client.request(
            method, f"{auth.prefix}{path}", json=body, headers=reviewer.headers
        )
        assert forbidden.status_code == 403, path
        assert forbidden.json()["detail"]["code"] == "forbidden"
    for method, path, body in both:
        allowed = await auth.client.request(
            method, f"{auth.prefix}{path}", json=body, headers=reviewer.headers
        )
        assert allowed.status_code == 200, path


async def test_other_tenants_see_only_their_own_rule_set(
    auth: AuthHarness, super_admin: SuperAdmin
) -> None:
    async with async_session_factory() as session:
        tenant = Tenant(code=f"t-{uuid4().hex[:10]}", name="Başka kurum")
        session.add(tenant)
        await session.commit()
        other_tenant_id, other_public_id = tenant.tenant_id, tenant.public_id
    login = await auth.login(super_admin.username, super_admin.password)
    headers = auth.auth_headers(login.json())
    headers[auth.settings.tenant_header] = str(other_public_id)

    listed = await auth.client.get(f"{auth.prefix}/rule-set/versions", headers=headers)
    latest = await auth.client.get(f"{auth.prefix}/rule-set/versions/latest", headers=headers)
    workspace = await auth.client.get(f"{auth.prefix}/rule-set", headers=headers)

    assert listed.json()["total"] == 0
    assert latest.status_code == 404
    assert latest.json()["detail"]["code"] == "no_published_rule_set"
    assert workspace.json()["revision"] == 0
    assert workspace.json()["next_rule_id"] == "Kural01"
    assert workspace.json()["latest_version"] is None
    async with async_session_factory() as session:
        assert await RuleSetService(session).latest_published_rule_set(other_tenant_id) is None


async def test_review_runs_read_the_latest_published_version_once(
    auth: AuthHarness, role_sessions: RoleSessions
) -> None:
    manager = await role_sessions.rule_manager()
    latest = (
        await auth.client.get(f"{auth.prefix}/rule-set/versions/latest", headers=manager.headers)
    ).json()
    async with async_session_factory() as session:
        tenant_id = await session.scalar(text("SELECT tenant_id FROM tenant WHERE code='platform'"))
        pinned = await RuleSetService(session).latest_published_rule_set(int(tenant_id))
        version_id = await session.scalar(
            select(RuleSetVersion.rule_set_version_id).where(
                RuleSetVersion.tenant_id == tenant_id,
                RuleSetVersion.number == latest["number"],
            )
        )

    assert pinned is not None
    assert pinned.number == latest["number"]
    assert pinned.version_id == version_id
    assert [rule.code for rule in pinned.rules.critical] == [r["id"] for r in latest["critical"]]
    assert [rule.text for rule in pinned.rules.normal] == [r["text"] for r in latest["normal"]]
