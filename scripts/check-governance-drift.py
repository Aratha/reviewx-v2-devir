#!/usr/bin/env python3
"""Yerel üreteç kurulumu olmadan üretilen ajan-istemci izdüşümlerini doğrula."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules"
LOCK = RULES / "GENERATED.lock"
AGENT_PLATFORM = ROOT / "agent-platform"
PROJECTION_ROOT = ROOT / ".kt-scaffold" / "agent-projections"
PROJECTION_LOCK = PROJECTION_ROOT / "PROJECTIONS.lock.json"
SCAFFOLD_MANIFEST = ROOT / ".kt-scaffold" / "manifest.json"
PROMPT_INGRESS_ASSETS = {
    ".kt-scaffold/hooks/prompt_ingress_guard.py",
    "agent-platform/prompt-ingress-metadata.schema.json",
    "agent-platform/llm-call-event.schema.json",
    ".kt-scaffold/hooks/governance_client.py",
    ".kt-scaffold/hooks/governance_records.py",
    ".kt-scaffold/hooks/python_environment.py",
    ".kt-scaffold/hooks/llm_call_events.py",
    ".kt-scaffold/hooks/llm_call_audit_hook.py",
    "agent-platform/policies/prompt-ingress/prompt-ingress-policy.json",
    "agent-platform/policies/local-state/local-governance-state-policy.json",
    "agent-platform/local-governance-state-policy.schema.json",
    "agent-platform/prompt-ingress-policy.schema.json",
    "agent-platform/prompt-ingress-receipt.schema.json",
}
LOCAL_GOVERNANCE_GUARD_ASSETS = {
    ".github/workflows/governance-drift.yml",
    ".kt-scaffold/hooks/agentic_review_receipt_guard.py",
    ".kt-scaffold/hooks/commit_governance_guard.py",
    ".kt-scaffold/hooks/initial_scaffold_commit.py",
    ".kt-scaffold/hooks/governance_drift_feedback.py",
    ".kt-scaffold/hooks/git/pre-commit",
    ".kt-scaffold/hooks/governance_surface_guard.py",
    ".pre-commit-config.yaml",
    "scripts/git-gate.sh",
    "agent-platform/agentic-governance-observation.schema.json",
    "agent-platform/agentic-governed-review-audit-event.schema.json",
    "agent-platform/agentic-governed-review-decision-evidence.schema.json",
    "agent-platform/agentic-governed-review-decision.schema.json",
    "agent-platform/agentic-governed-review-evaluator-policy.schema.json",
    "agent-platform/agentic-governed-review-receipt.schema.json",
    "agent-platform/policies/aggregation/governed-review-agentic-evaluation.yml",
}
UNTRUSTED_CONTENT_ASSETS = {
    "agent-platform/evals/indirect-injection-v1.json",
    "agent-platform/indirect-injection-eval.schema.json",
    "agent-platform/untrusted-content-envelope.schema.json",
}
ACTIVATION_STATE_ROOT = Path(".kt-scaffold/agent-activation")
EXPECTED_RENDERER_VERSION = "0.4.0"
AGENT_IDS = {
    "acik-kaynak-lisansi",
    "bilgi-guvenligi",
    "devops",
    "dokumantasyon",
    "gereksinim-kapsami",
    "gizlilik-kvkk",
    "gozlemlenebilirlik",
    "kod-inceleme",
    "kod-kalitesi",
    "kurumsal-mimari",
    "otomatik-duzeltme",
    "test-otomasyonu",
    "uygulama-guvenligi",
}
CLIENT_PATHS = {
    "claude-code": ".claude/agents/{agent_id}.md",
    "codex": ".codex/agents/{agent_id}.toml",
    "cursor": ".cursor/agents/{agent_id}.md",
    "github-copilot-vscode": ".github/agents/{agent_id}.agent.md",
}
LOCAL_DISCOVERY_ROOTS = {
    Path(pattern.format(agent_id="placeholder")).parent for pattern in CLIENT_PATHS.values()
}
COMMAND_SKILL_NAMES = {
    "kt-baslat",
    "kt-guncelle",
    "kt-kurallar",
    "kt-kural",
    "kt-yansit",
    "kt-spesifikasyon",
    "kt-alan",
    "kt-sayfa",
    "kt-sema",
    "kt-kalite-kapisi",
    "kt-senaryo",
    "kt-tamamla",
}
# Skills of commands that exist only in the separated-web layout.
WEB_ONLY_SKILL_NAMES = {"kt-alan", "kt-sayfa", "kt-sema", "kt-senaryo"}
REPORT_SKILL_NAME = "kt-test-kosumu-raporu"
GOVERNED_REVIEW_SKILL_NAME = "governed-review"


def digest_corpus() -> str:
    digest = hashlib.sha256()
    # Order by the name's code points; Path ordering ignores case on Windows.
    for path in sorted(RULES.glob("*"), key=lambda item: item.name):
        if path.is_file() and path.name != "GENERATED.lock":
            digest.update(path.name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str):
        raise SystemExit(f"{label} yol değeri metin değildir")
    path = Path(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise SystemExit(f"güvenli olmayan {label} yol değeri: {value}")
    return path


def safe_project_path(relative: Path, label: str) -> Path:
    current = ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"{label} yolunda sembolik bağlantı var: {relative}")
    try:
        current.resolve(strict=False).relative_to(ROOT.resolve(strict=True))
    except ValueError as exc:
        raise SystemExit(f"{label} proje kökü dışına çıkıyor: {relative}") from exc
    return current


def scaffold_managed_digests() -> dict[str, str]:
    manifest = safe_project_path(SCAFFOLD_MANIFEST.relative_to(ROOT), "scaffold manifesti")
    if not manifest.is_file():
        raise SystemExit("scaffold ownership manifesti eksik veya güvenli değil")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("generator_version") != EXPECTED_RENDERER_VERSION
    ):
        raise SystemExit(
            "scaffold ownership manifestinin generator_version değeri doğrulayıcıyla eşleşmiyor"
        )
    managed = payload.get("managed") if isinstance(payload, dict) else None
    if not isinstance(managed, dict) or any(
        not isinstance(path, str)
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for path, digest in managed.items()
    ):
        raise SystemExit("scaffold ownership manifesti bozuk")
    return managed


def application_mode() -> str:
    answers = ROOT / ".kt-scaffold" / "answers.yml"
    for line in answers.read_text(encoding="utf-8").splitlines():
        if line.startswith("application_mode:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return "separated-web"


def mode_skill_names() -> set[str]:
    if application_mode() == "separated-web":
        return set(COMMAND_SKILL_NAMES)
    return COMMAND_SKILL_NAMES - WEB_ONLY_SKILL_NAMES


def expected_governance_files(selected_clients: set[str]) -> set[str]:
    expected = {"AGENTS.md", ".specify/memory/constitution.md"}
    if "claude-code" in selected_clients:
        expected.update(
            {
                "CLAUDE.md",
                ".claude/settings.json",
                f".claude/skills/{REPORT_SKILL_NAME}/SKILL.md",
                f".claude/skills/{GOVERNED_REVIEW_SKILL_NAME}/SKILL.md",
            }
        )
        for skill_name in mode_skill_names():
            expected.add(f".claude/skills/{skill_name}/SKILL.md")
    if "codex" in selected_clients:
        expected.update(
            {
                ".codex/config.toml",
                ".codex/hooks.json",
                f".agents/skills/{REPORT_SKILL_NAME}/SKILL.md",
                f".agents/skills/{GOVERNED_REVIEW_SKILL_NAME}/SKILL.md",
            }
        )
        for skill_name in mode_skill_names():
            expected.add(f".agents/skills/{skill_name}/SKILL.md")
    if "cursor" in selected_clients:
        expected.update(
            {
                ".cursor/hooks.json",
                f".cursor/skills/{GOVERNED_REVIEW_SKILL_NAME}/SKILL.md",
            }
        )
    if "github-copilot-vscode" in selected_clients:
        expected.update(
            {
                ".github/hooks/kt-prompt-ingress.json",
                ".github/hooks/kt-call-audit.json",
                ".github/hooks/kt-commit-governance.json",
                f".github/skills/{GOVERNED_REVIEW_SKILL_NAME}/SKILL.md",
            }
        )
    for rule in sorted(RULES.glob("*.md")):
        content = rule.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            continue
        header = content.split("---", 2)[1]
        fields = {}
        for line in header.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
        if fields.get("trigger") == "path-match":
            rule_id = fields.get("id")
            if not rule_id:
                raise SystemExit(f"path-match kural kimliği eksik: {rule.name}")
            if "claude-code" in selected_clients:
                expected.add(f".claude/rules/{rule_id}.md")
            if "cursor" in selected_clients:
                expected.add(f".cursor/rules/{rule_id}.mdc")
            if "github-copilot-vscode" in selected_clients:
                expected.add(f".github/instructions/{rule_id}.instructions.md")
            # Only the web layout gets Rule 58's Codex directory-scoped copies.
            if (
                rule_id == "58-kimlik-dogrulama-ve-yetkilendirme"
                and "codex" in selected_clients
                and application_mode() == "separated-web"
            ):
                expected.update({"app/backend/AGENTS.md", "app/frontend/AGENTS.md", "helm/AGENTS.md"})
    return expected


def verify_prompt_ingress_assets() -> None:
    managed = scaffold_managed_digests()
    for relative in sorted(PROMPT_INGRESS_ASSETS):
        destination = safe_project_path(Path(relative), "prompt giriş koruması varlığı")
        if not destination.is_file():
            raise SystemExit(f"prompt giriş koruması varlığı eksik veya güvenli değil: {relative}")
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if managed.get(relative) != actual:
            raise SystemExit(
                f"prompt giriş koruması varlığı scaffold özetiyle eşleşmiyor: {relative}"
            )


def verify_local_governance_guard_assets() -> None:
    managed = scaffold_managed_digests()
    for relative in sorted(LOCAL_GOVERNANCE_GUARD_ASSETS):
        destination = safe_project_path(Path(relative), "yerel yönetişim kapısı varlığı")
        if not destination.is_file():
            raise SystemExit(f"yerel yönetişim kapısı varlığı eksik veya güvenli değil: {relative}")
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if managed.get(relative) != actual:
            raise SystemExit(
                f"yerel yönetişim kapısı varlığı scaffold özetiyle eşleşmiyor: {relative}"
            )


def verify_untrusted_content_assets() -> None:
    managed = scaffold_managed_digests()
    for relative in sorted(UNTRUSTED_CONTENT_ASSETS):
        destination = safe_project_path(Path(relative), "harici içerik güven sınırı varlığı")
        if not destination.is_file():
            raise SystemExit(
                f"harici içerik güven sınırı varlığı eksik veya güvenli değil: {relative}"
            )
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if managed.get(relative) != actual:
            raise SystemExit(
                f"harici içerik güven sınırı varlığı scaffold özetiyle eşleşmiyor: {relative}"
            )


def verify_agent_projections() -> tuple[int, set[str]]:
    activation_root = safe_project_path(
        ACTIVATION_STATE_ROOT, "yönetilen etkinleştirme durumu kökü"
    )
    if activation_root.exists() and (
        not activation_root.is_dir() or any(activation_root.iterdir())
    ):
        raise SystemExit(
            "yönetilen etkinleştirme durumu yerel danışman projeksiyonu denetimiyle karıştırılamaz"
        )
    managed = scaffold_managed_digests()
    projection_lock = safe_project_path(PROJECTION_LOCK.relative_to(ROOT), "ajan izdüşüm kilidi")
    if not projection_lock.is_file():
        raise SystemExit("ajan izdüşüm kilidi eksik veya güvenli değil")
    payload = json.loads(projection_lock.read_text(encoding="utf-8"))
    if payload.get("kind") != "AgentProjectionLock":
        raise SystemExit("ajan izdüşüm kilidinin kind değeri geçersiz")
    if payload.get("generation_status") != "generated":
        raise SystemExit("ajan izdüşüm kilidi generation_status=generated durumunu kaydetmiyor")
    if payload.get("activation_status") != "not_activated":
        raise SystemExit("ajan izdüşüm kilidi yönetişimli etkinleştirme iddiası taşıyor")
    if payload.get("runtime_conformance") != "not_run":
        raise SystemExit("eylemsiz ajan izdüşüm kilidi çalışma zamanı uygunluğu iddiası taşıyor")
    if payload.get("runtime_admission") != "research":
        raise SystemExit("ajan izdüşüm kilidi runtime admission iddiası taşıyor")

    inputs = payload.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise SystemExit("ajan izdüşüm kilidi kanonik girdi envanteri taşımıyor")
    for item in inputs:
        if not isinstance(item, dict):
            raise SystemExit("ajan izdüşüm girdi kaydı bozuk")
        relative = safe_relative(item.get("path"), "agent-platform girdisi")
        source = safe_project_path(
            AGENT_PLATFORM.relative_to(ROOT) / relative,
            "kanonik agent-platform girdisi",
        )
        if not source.is_file():
            raise SystemExit(f"kanonik agent-platform girdisi eksik veya güvenli değil: {relative}")
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != item.get("sha256"):
            raise SystemExit(f"kanonik agent-platform girdisi sapma gösteriyor: {relative}")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SystemExit("ajan izdüşüm kilidi varlık envanteri taşımıyor")
    expected_files = {PROJECTION_LOCK.relative_to(PROJECTION_ROOT).as_posix()}
    seen: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    selected_clients: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise SystemExit("ajan izdüşüm varlık kaydı bozuk")
        client_id = item.get("client_id")
        agent_id = item.get("agent_id")
        if client_id not in CLIENT_PATHS or agent_id not in AGENT_IDS:
            raise SystemExit(f"bilinmeyen ajan izdüşüm kimliği: {client_id}/{agent_id}")
        relative = safe_relative(item.get("relative_path"), "ajan izdüşümü")
        normalized = relative.as_posix()
        expected_relative = CLIENT_PATHS[client_id].format(agent_id=agent_id)
        if normalized != expected_relative:
            raise SystemExit(
                f"ajan izdüşüm yolu kanonik istemci/ajan kimliğiyle eşleşmiyor: {normalized}"
            )
        if normalized in seen:
            raise SystemExit(f"yinelenen ajan izdüşüm yolu: {normalized}")
        seen.add(normalized)
        pair = (client_id, agent_id)
        if pair in seen_pairs:
            raise SystemExit(f"yinelenen ajan izdüşüm kimliği: {client_id}/{agent_id}")
        seen_pairs.add(pair)
        selected_clients.add(client_id)
        expected_files.add(normalized)
        if item.get("runtime_conformance") != "not_run":
            raise SystemExit(
                f"ajan izdüşümü çalışma zamanı uygunluğu iddiası taşıyor: {normalized}"
            )
        if item.get("runtime_admission") != "research":
            raise SystemExit(f"ajan izdüşümü runtime admission iddiası taşıyor: {normalized}")
        destination = safe_project_path(
            PROJECTION_ROOT.relative_to(ROOT) / relative,
            "eylemsiz ajan izdüşümü",
        )
        if not destination.is_file():
            raise SystemExit(f"eylemsiz ajan izdüşümü eksik veya güvenli değil: {normalized}")
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual != item.get("sha256"):
            raise SystemExit(f"eylemsiz ajan izdüşümü sapma gösteriyor: {normalized}")
        inert_relative = destination.relative_to(ROOT).as_posix()
        if managed.get(inert_relative) != actual:
            raise SystemExit(
                f"eylemsiz ajan izdüşümü scaffold tarafından sahiplenilmiyor: {normalized}"
            )
        live_destination = safe_project_path(relative, "yerel ajan keşif dosyası")
        if not live_destination.is_file():
            raise SystemExit(f"yerel ajan keşif dosyası eksik veya güvenli değil: {normalized}")
        live_actual = hashlib.sha256(live_destination.read_bytes()).hexdigest()
        if live_actual != item.get("sha256"):
            raise SystemExit(f"yerel ajan keşif dosyası sapma gösteriyor: {normalized}")
        if managed.get(normalized) != live_actual:
            raise SystemExit(
                f"yerel ajan keşif dosyası scaffold tarafından sahiplenilmiyor: {normalized}"
            )

    expected_pairs = {
        (client_id, agent_id) for client_id in selected_clients for agent_id in AGENT_IDS
    }
    if seen_pairs != expected_pairs:
        raise SystemExit(
            "ajan izdüşüm kilidi seçili istemciler için eksik kimlik envanteri taşıyor"
        )

    projection_root = safe_project_path(PROJECTION_ROOT.relative_to(ROOT), "eylemsiz izdüşüm kökü")
    actual_files: set[str] = set()
    for path in projection_root.rglob("*"):
        if path.is_symlink():
            raise SystemExit(f"eylemsiz izdüşüm ağacında sembolik bağlantı var: {path}")
        if path.is_file():
            actual_files.add(path.relative_to(projection_root).as_posix())
    extra = sorted(actual_files - expected_files)
    if extra:
        raise SystemExit(f"sahipsiz eski eylemsiz ajan izdüşümleri: {', '.join(extra)}")

    actual_live_files: set[str] = set()
    existing_live_roots: set[str] = set()
    for relative_root in sorted(LOCAL_DISCOVERY_ROOTS):
        discovery_root = safe_project_path(relative_root, "yerel ajan keşif kökü")
        if not discovery_root.exists():
            continue
        existing_live_roots.add(relative_root.as_posix())
        if not discovery_root.is_dir():
            raise SystemExit(f"yerel ajan keşif kökü dizin değil: {relative_root}")
        for path in discovery_root.rglob("*"):
            relative = path.relative_to(ROOT)
            safe_project_path(relative, "yerel ajan keşif ağacı")
            if path.is_file():
                actual_live_files.add(relative.as_posix())
            elif not path.is_dir():
                raise SystemExit(f"yerel ajan keşif ağacında özel dosya var: {relative}")
    extra_live = sorted(actual_live_files - seen)
    if extra_live:
        raise SystemExit(f"sahipsiz yerel ajan keşif dosyaları: {', '.join(extra_live)}")
    selected_live_roots = {
        Path(CLIENT_PATHS[client_id].format(agent_id="placeholder")).parent.as_posix()
        for client_id in selected_clients
    }
    extra_live_roots = sorted(existing_live_roots - selected_live_roots)
    if extra_live_roots:
        raise SystemExit(f"seçilmemiş yerel ajan keşif kökleri: {', '.join(extra_live_roots)}")
    projection_lock_relative = projection_lock.relative_to(ROOT).as_posix()
    projection_lock_digest = hashlib.sha256(projection_lock.read_bytes()).hexdigest()
    if managed.get(projection_lock_relative) != projection_lock_digest:
        raise SystemExit("ajan izdüşüm kilidi scaffold tarafından sahiplenilmiyor")
    return len(artifacts), selected_clients


def main() -> int:
    lock_path = safe_project_path(LOCK.relative_to(ROOT), "yönetişim kilidi")
    if not lock_path.is_file():
        raise SystemExit("yönetişim kilidi eksik veya güvenli değil")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if payload.get("renderer_version") != EXPECTED_RENDERER_VERSION:
        raise SystemExit(
            "yönetişim kilidinin renderer_version değeri üretilmiş doğrulayıcıyla eşleşmiyor: "
            f"{payload.get('renderer_version')} != {EXPECTED_RENDERER_VERSION}"
        )
    if payload.get("corpus_digest") != digest_corpus():
        raise SystemExit("kanonik kural külliyatı üretilmiş izdüşüm kilidiyle eşleşmiyor")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise SystemExit("yönetişim kilidi üretilmiş dosya envanteri taşımıyor")
    agent_count, selected_clients = verify_agent_projections()
    verify_prompt_ingress_assets()
    verify_local_governance_guard_assets()
    verify_untrusted_content_assets()
    expected_files = expected_governance_files(selected_clients)
    if set(files) != expected_files:
        missing = sorted(expected_files - set(files))
        unexpected = sorted(set(files) - expected_files)
        raise SystemExit(
            "yönetişim kilidi tam üretilmiş envanterle eşleşmiyor: "
            f"eksik={missing or 'yok'}, beklenmeyen={unexpected or 'yok'}"
        )
    managed = scaffold_managed_digests()
    for relative, expected in sorted(files.items()):
        path = safe_relative(relative, "yönetişim kilidi")
        destination = safe_project_path(path, "üretilmiş yönetişim dosyası")
        if not destination.is_file():
            raise SystemExit(f"üretilmiş yönetişim dosyası eksik veya güvenli değil: {relative}")
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"üretilmiş yönetişim dosyası sapma gösteriyor: {relative}")
        if managed.get(relative) != actual:
            raise SystemExit(
                f"üretilmiş yönetişim dosyası scaffold tarafından sahiplenilmiyor: {relative}"
            )
    print(f"yönetişim izdüşümleri güncel: {len(files)} dosya")
    print(
        f"ajan izdüşümleri güncel: {agent_count} etkisiz kopya ve "
        f"{agent_count} salt-okunur yetki talebiyle yapılandırılmış yerel keşif dosyası; "
        "conformance/admission iddiası yok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
