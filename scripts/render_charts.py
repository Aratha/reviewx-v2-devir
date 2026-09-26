#!/usr/bin/env python3
"""Render and validate the generated project's single application Helm chart."""

from __future__ import annotations

import argparse
import copy
import hashlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART_PATH = "helm/dwhcodereview"
CHART = ROOT / CHART_PATH
EXPECTED_TEMPLATES = {
    "_helpers.tpl",
    "application-ingress.yaml",
    "backend-deployment.yaml",
    "backend-networkpolicy.yaml",
    "backend-service.yaml",
    "frontend-deployment.yaml",
    "frontend-networkpolicy.yaml",
    "frontend-service.yaml",
    "migration-job.yaml",
    "migration-networkpolicy.yaml",
    "postgres-networkpolicy.yaml",
    "postgres-service.yaml",
    "postgres-statefulset.yaml",
}
VALUE_SECTIONS = {"backend", "frontend", "postgres", "migration"}
FORBIDDEN_COMPONENTS = {
    "redis",
    "worker",
    "observability",
    "collector",
    "grafana",
    "loki",
    "prometheus",
    "tempo",
}
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
OCI_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
IMAGE_PROXY = "cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding"
POSTGRES_MAJOR = re.compile(r"^17(?:\.[0-9]+)?$")
POSTGRES_UID = 999
MIGRATION_COMMAND = ["alembic", "upgrade", "head"]
MIGRATION_MODES = {"bootstrap", "upgrade"}
HOOK_ANNOTATIONS = {
    "helm.sh/hook": "pre-upgrade",
    "helm.sh/hook-weight": "0",
    "helm.sh/hook-delete-policy": "before-hook-creation",
}
WORKLOAD_LABEL = "scaffold.kt.internal/workload"
DNS_PORTS = [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]
RKE2_DNS_PEERS = [
    {
        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
        "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
    }
]


class PolicyError(RuntimeError):
    """The generated chart cannot prove its bounded deployment contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PolicyError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"{path}: expected a YAML mapping")
    return cast(dict[str, Any], value)


def validate_chart_layout() -> tuple[dict[str, Any], dict[str, Any]]:
    require(CHART.is_dir() and not CHART.is_symlink(), f"{CHART_PATH} chart is missing or unsafe")
    chart_path = CHART / "Chart.yaml"
    values_path = CHART / "values.yaml"
    templates = CHART / "templates"
    require(chart_path.is_file(), f"{CHART_PATH}/Chart.yaml is required")
    require(values_path.is_file(), f"{CHART_PATH}/values.yaml is required")
    require(templates.is_dir() and not templates.is_symlink(), f"{CHART_PATH}/templates is required")

    values_files = sorted(path.relative_to(CHART).as_posix() for path in CHART.rglob("values.yaml"))
    require(
        values_files == ["values.yaml"], "the generated chart must contain exactly one values.yaml"
    )
    require(not (CHART / "charts").exists(), "component subcharts are forbidden")
    require(not (CHART / "environments").exists(), "environment overlays are forbidden")
    template_files = {
        path.relative_to(templates).as_posix() for path in templates.rglob("*") if path.is_file()
    }
    require(
        template_files == EXPECTED_TEMPLATES,
        "chart templates must contain backend/frontend and the optional database/migration only",
    )
    lowered_paths = "\n".join(sorted(template_files)).lower()
    require(
        not any(component in lowered_paths for component in FORBIDDEN_COMPONENTS),
        "forbidden application component template present",
    )

    chart = load_yaml(chart_path)
    values = load_yaml(values_path)
    require(chart.get("apiVersion") == "v2", "Chart.yaml must use Helm API v2")
    require(chart.get("type") == "application", "Chart.yaml must describe an application")
    slug = chart.get("name")
    require(isinstance(slug, str) and DNS_LABEL.fullmatch(slug) is not None, "invalid chart slug")
    annotations = chart.get("annotations")
    if not isinstance(annotations, dict):
        raise PolicyError("Chart.yaml annotations are required")
    require(
        annotations.get("scaffold.kt.internal/product-slug") == slug,
        "rendered product slug facts disagree",
    )
    product_name = annotations.get("scaffold.kt.internal/product-name")
    require(
        isinstance(product_name, str) and bool(product_name), "rendered product name is required"
    )
    require(chart.get("description") == product_name, "rendered product name facts disagree")

    require(
        set(values) == VALUE_SECTIONS,
        "values must contain backend/frontend and the optional postgres/migration only",
    )
    backend = values.get("backend")
    frontend = values.get("frontend")
    if not isinstance(backend, dict) or not isinstance(frontend, dict):
        raise PolicyError("component values must be mappings")
    for component, config in (("backend", backend), ("frontend", frontend)):
        image = config.get("image")
        if not isinstance(image, dict):
            raise PolicyError(f"{component}.image must be a mapping")
        require(
            image
            == {
                "repository": f"{IMAGE_PROXY}/{slug}-{component}",
                "tag": "latest",
                "digest": "",
            },
            f"{component} image defaults must use the canonical GHCR proxy route",
        )
    require(
        backend.get("existingSecret") == "",
        "backend.existingSecret must not hardcode an environment deployment fact",
    )
    backend_policy = backend.get("networkPolicy")
    frontend_policy = frontend.get("networkPolicy")
    ingress = frontend.get("ingress")

    def rke2_ingress(port: int) -> list[dict[str, Any]]:
        return [
            {
                "from": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                        }
                    }
                ],
                "ports": [{"protocol": "TCP", "port": port}],
            }
        ]

    require(
        backend_policy == {"ingress": rke2_ingress(8000), "egress": []},
        "backend ingress must allow the canonical RKE2 controller namespace",
    )
    require(
        frontend_policy == {"ingress": rke2_ingress(8080), "egress": []},
        "frontend ingress must allow the canonical RKE2 controller namespace",
    )
    require(
        ingress == {"className": "", "host": "", "tlsSecretName": ""},
        "ingress facts must be empty and deployment-environment supplied",
    )
    validate_optional_defaults(values)
    return chart, values


def has_requests_and_limits(resources: object) -> bool:
    return (
        isinstance(resources, dict)
        and bool(resources.get("requests"))
        and bool(resources.get("limits"))
    )


def validate_optional_defaults(values: dict[str, Any]) -> None:
    """The optional database and migration stay off until an accepted project PRD enables them."""

    postgres = values.get("postgres")
    migration = values.get("migration")
    if not isinstance(postgres, dict) or not isinstance(migration, dict):
        raise PolicyError("optional postgres/migration values must be mappings")
    require(postgres.get("enabled") is False, "postgres must be disabled by default")
    image = postgres.get("image")
    if not isinstance(image, dict):
        raise PolicyError("postgres.image must be a mapping")
    require(
        set(image) == {"repository", "tag", "digest"}
        and image.get("repository") == "postgres"
        and POSTGRES_MAJOR.fullmatch(str(image.get("tag", ""))) is not None,
        "postgres image defaults must name the PostgreSQL 17 image",
    )
    require(
        DIGEST.fullmatch(str(image.get("digest", ""))) is not None,
        "postgres image default must pin a sha256 digest",
    )
    require(
        postgres.get("existingSecret") == "",
        "postgres.existingSecret must not hardcode an environment deployment fact",
    )
    require(postgres.get("port") == 5432, "postgres.port must be 5432")
    database = postgres.get("database")
    require(
        isinstance(database, str) and bool(database), "postgres.database must name the database"
    )
    persistence = postgres.get("persistence")
    if not isinstance(persistence, dict):
        raise PolicyError("postgres.persistence must be a mapping")
    require(
        set(persistence) == {"size", "storageClassName", "accessMode"}
        and bool(persistence.get("size"))
        and persistence.get("accessMode") == "ReadWriteOnce",
        "postgres persistence must declare a size and ReadWriteOnce access",
    )
    require(
        persistence.get("storageClassName") == "",
        "postgres storage class must be empty and deployment-environment supplied",
    )
    require(has_requests_and_limits(postgres.get("resources")), "postgres resources incomplete")

    require(migration.get("enabled") is False, "migration must be disabled by default")
    require(
        migration.get("existingSecret") == "",
        "migration.existingSecret must not hardcode an environment deployment fact",
    )
    deadline = migration.get("activeDeadlineSeconds")
    require(
        isinstance(deadline, int) and not isinstance(deadline, bool) and deadline > 0,
        "migration.activeDeadlineSeconds must be a positive integer",
    )
    require(
        migration.get("networkPolicy") == {"dns": RKE2_DNS_PEERS},
        "migration DNS egress must target the canonical RKE2 cluster DNS",
    )
    require(has_requests_and_limits(migration.get("resources")), "migration resources incomplete")


def merge_values(base: object, override: object) -> Any:
    """Merge supplied values over chart defaults the way Helm does: maps merge, lists replace."""

    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = merge_values(base.get(key), value)
        return merged
    return copy.deepcopy(override)


def resource_name(release_name: str, namespace: str, slug: str, component: str) -> str:
    """Mirror the chart's generated.resourceName helper."""

    def bounded(value: str, limit: int) -> str:
        value = value[:limit]
        return value[:-1] if value.endswith("-") else value

    identity = f"{namespace}/{release_name}/{slug}/{component}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return bounded(
        f"{bounded(release_name, 18)}-{bounded(slug, 18)}-{component}-{digest}",
        63,
    )


def deployment_values(values: dict[str, Any], slug: str) -> dict[str, Any]:
    """Return deterministic synthetic facts used only to exercise the chart contract."""

    result = copy.deepcopy(values)
    result["backend"]["image"] = {
        "repository": f"{IMAGE_PROXY}/{slug}-backend",
        "tag": "1" * 40,
        "digest": "",
    }
    result["backend"]["existingSecret"] = "synthetic-runtime"
    gateway_peer = {
        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "synthetic-edge"}},
        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "synthetic-gateway"}},
    }
    result["backend"]["networkPolicy"] = {
        "ingress": [
            {
                "from": [gateway_peer],
                "ports": [{"protocol": "TCP", "port": result["backend"]["service"]["port"]}],
            }
        ],
        "egress": [
            {
                "to": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {"kubernetes.io/metadata.name": "synthetic-dns"}
                        },
                        "podSelector": {"matchLabels": {"app.kubernetes.io/name": "synthetic-dns"}},
                    }
                ],
                "ports": [
                    {"protocol": "UDP", "port": 53},
                    {"protocol": "TCP", "port": 53},
                ],
            },
            {
                "to": [
                    {
                        "podSelector": {
                            "matchLabels": {
                                "app.kubernetes.io/part-of": slug,
                                "app.kubernetes.io/component": "database",
                            }
                        }
                    }
                ],
                "ports": [{"protocol": "TCP", "port": 5432}],
            },
        ],
    }
    result["frontend"]["image"] = {
        "repository": f"{IMAGE_PROXY}/{slug}-frontend",
        "tag": "1" * 40,
        "digest": "",
    }
    result["frontend"]["ingress"] = {
        "className": "synthetic-gateway",
        "host": f"{slug}.test.invalid",
        "tlsSecretName": "synthetic-tls",
    }
    result["frontend"]["networkPolicy"] = {
        "ingress": [
            {
                "from": [gateway_peer],
                "ports": [{"protocol": "TCP", "port": result["frontend"]["service"]["port"]}],
            }
        ],
        "egress": [],
    }
    return result


def database_deployment_values(values: dict[str, Any], slug: str) -> dict[str, Any]:
    """Return synthetic facts that also enable the optional database and migration Job."""

    result = deployment_values(values, slug)
    result["postgres"]["enabled"] = True
    result["postgres"]["existingSecret"] = "synthetic-database"
    result["postgres"]["persistence"]["storageClassName"] = "synthetic-storage"
    result["migration"]["enabled"] = True
    result["migration"]["existingSecret"] = "synthetic-migration"
    return result


def helm(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PolicyError(f"{' '.join(command[:3])} failed: {detail}")
    return completed.stdout


def render_chart(
    values: dict[str, Any],
    *,
    release_name: str,
    namespace: str,
) -> list[dict[str, Any]]:
    require(DNS_LABEL.fullmatch(release_name) is not None, "release name must be a DNS label")
    require(DNS_LABEL.fullmatch(namespace) is not None, "namespace must be a DNS label")
    with tempfile.TemporaryDirectory(prefix="generated-chart-values-") as directory:
        values_path = Path(directory) / "values.yaml"
        values_path.write_text(yaml.safe_dump(values, sort_keys=True), encoding="utf-8")
        common = ["--values", str(values_path), "--namespace", namespace]
        helm(["helm", "lint", str(CHART), *common])
        rendered = helm(
            [
                "helm",
                "template",
                release_name,
                str(CHART),
                *common,
                "--kube-version",
                "1.33.0",
            ]
        )
    try:
        return [item for item in yaml.safe_load_all(rendered) if isinstance(item, dict)]
    except yaml.YAMLError as exc:
        raise PolicyError(f"Helm produced invalid YAML: {exc}") from exc


def pod_spec(document: dict[str, Any]) -> dict[str, Any]:
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        return {}
    template = spec.get("template", {})
    if not isinstance(template, dict):
        return {}
    pod = template.get("spec", {})
    return cast(dict[str, Any], pod) if isinstance(pod, dict) else {}


def validate_policy_rules(rules: object, peer_key: str, name: str) -> None:
    if not isinstance(rules, list) or not rules:
        raise PolicyError(f"{name}: admitted policy rules required")
    for rule in rules:
        if not isinstance(rule, dict):
            raise PolicyError(f"{name}: policy rule must be a mapping")
        peers = rule.get(peer_key)
        if not isinstance(peers, list) or not peers:
            raise PolicyError(f"{name}: policy peers required")
        for peer in peers:
            if not isinstance(peer, dict) or not peer:
                raise PolicyError(f"{name}: empty policy peer is forbidden")
            require(
                any(key in peer for key in ("podSelector", "namespaceSelector")),
                f"{name}: peer must use podSelector or namespaceSelector",
            )
            for selector in (peer.get("podSelector"), peer.get("namespaceSelector")):
                if selector is not None:
                    require(
                        isinstance(selector, dict) and bool(selector.get("matchLabels")),
                        f"{name}: empty peer selector is forbidden",
                    )
        require(
            isinstance(rule.get("ports"), list) and bool(rule["ports"]),
            f"{name}: peer ports required",
        )


def expected_resources(values: dict[str, Any]) -> set[tuple[str, str]]:
    expected = {
        ("Deployment", "backend"),
        ("Deployment", "frontend"),
        ("Ingress", "frontend"),
        ("NetworkPolicy", "backend"),
        ("NetworkPolicy", "frontend"),
        ("Service", "backend"),
        ("Service", "frontend"),
    }
    if values["postgres"]["enabled"] is True:
        expected |= {
            ("NetworkPolicy", "database"),
            ("Service", "database"),
            ("StatefulSet", "database"),
        }
    if values["migration"]["enabled"] is True:
        expected |= {("Job", "migration"), ("NetworkPolicy", "migration")}
    return expected


def image_reference(image: dict[str, Any], name: str) -> str:
    repository = str(image.get("repository", ""))
    digest = str(image.get("digest", ""))
    tag = str(image.get("tag", ""))
    require(bool(repository), f"{name}: image repository is required")
    if digest:
        require(DIGEST.fullmatch(digest) is not None, f"{name}: invalid image digest")
        return f"{repository}@{digest}"
    require(OCI_TAG.fullmatch(tag) is not None, f"{name}: invalid image tag")
    return f"{repository}:{tag}"


def component_peer(component: str, workload: str) -> dict[str, Any]:
    return {
        "podSelector": {
            "matchLabels": {
                "app.kubernetes.io/component": component,
                WORKLOAD_LABEL: workload,
            }
        }
    }


def validate_migration_hook(document: dict[str, Any], name: str, mode: str) -> None:
    """Bootstrap runs as a release resource beside the database; upgrade runs before new pods."""

    annotations = document.get("metadata", {}).get("annotations", {})
    hooks = {key: value for key, value in annotations.items() if key.startswith("helm.sh/hook")}
    if mode == "upgrade":
        require(
            hooks == HOOK_ANNOTATIONS,
            f"{name}: an upgrade migration must run as a pre-upgrade hook",
        )
    else:
        require(
            not hooks,
            f"{name}: a bootstrap migration must be created together with the database",
        )


def validate_network_policy(
    document: dict[str, Any],
    component: str,
    values: dict[str, Any],
    workloads: dict[str, str],
) -> None:
    name = str(document["metadata"]["name"])
    require(
        document.get("apiVersion") == "networking.k8s.io/v1",
        f"{name}: unsupported NetworkPolicy API",
    )
    policy = document.get("spec", {})
    require(
        policy.get("policyTypes") == ["Ingress", "Egress"],
        f"{name}: ingress/egress policy required",
    )
    require("ingress" in policy and "egress" in policy, f"{name}: policy directions incomplete")
    require(
        policy.get("podSelector") == {"matchLabels": {WORKLOAD_LABEL: workloads[component]}},
        f"{name}: policy must select its own workload",
    )
    if component == "database":
        port = values["postgres"]["port"]
        require(
            policy["ingress"]
            == [
                {
                    "from": [
                        component_peer("backend", workloads["backend"]),
                        component_peer("migration", workloads["migration"]),
                    ],
                    "ports": [{"protocol": "TCP", "port": port}],
                }
            ],
            f"{name}: database ingress must admit only backend and migration pods",
        )
        validate_policy_rules(policy["ingress"], "from", name)
        require(policy["egress"] == [], f"{name}: database must default-deny egress")
        return
    if component == "migration":
        require(policy["ingress"] == [], f"{name}: migration Job must default-deny ingress")
        require(
            policy["egress"]
            == [
                {"to": values["migration"]["networkPolicy"]["dns"], "ports": DNS_PORTS},
                {
                    "to": [component_peer("database", workloads["database"])],
                    "ports": [{"protocol": "TCP", "port": values["postgres"]["port"]}],
                },
            ],
            f"{name}: migration egress must reach only DNS and the database",
        )
        validate_policy_rules(policy["egress"], "to", name)
        return
    expected_policy = values[component]["networkPolicy"]
    require(policy.get("ingress") == expected_policy["ingress"], f"{name}: ingress peer drift")
    require(policy.get("egress") == expected_policy["egress"], f"{name}: egress peer drift")
    validate_policy_rules(policy["ingress"], "from", name)
    if component == "backend":
        validate_policy_rules(policy["egress"], "to", name)
        ports = {
            (port.get("protocol"), port.get("port"))
            for rule in policy["egress"]
            for port in rule.get("ports", [])
        }
        require(
            {("UDP", 53), ("TCP", 53), ("TCP", 5432)} <= ports,
            f"{name}: admitted DNS/database egress is incomplete",
        )
    else:
        require(policy["egress"] == [], f"{name}: static frontend must default-deny egress")


def validate_container_hardening(container: dict[str, Any], name: str) -> None:
    container_security = container.get("securityContext", {})
    require(
        container_security.get("allowPrivilegeEscalation") is False,
        f"{name}: privilege escalation enabled",
    )
    require(
        container_security.get("readOnlyRootFilesystem") is True,
        f"{name}: writable root filesystem",
    )
    require(
        container_security.get("capabilities", {}).get("drop") == ["ALL"],
        f"{name}: capabilities not dropped",
    )
    for field in ("runAsUser", "runAsNonRoot", "privileged"):
        require(field not in container_security, f"{name}: container overrides pod identity")
    require(has_requests_and_limits(container.get("resources", {})), f"{name}: resources incomplete")


def validate_pod_hardening(
    spec: dict[str, Any], name: str, *, init_containers: int = 0
) -> dict[str, Any]:
    require(
        spec.get("automountServiceAccountToken") is False,
        f"{name}: service account token enabled",
    )
    security = spec.get("securityContext", {})
    require(security.get("runAsNonRoot") is True, f"{name}: runAsNonRoot required")
    for field in ("runAsUser", "runAsGroup"):
        identity = security.get(field)
        require(
            isinstance(identity, int) and not isinstance(identity, bool) and identity > 0,
            f"{name}: explicit non-root {field} required",
        )
    require(
        security.get("seccompProfile", {}).get("type") == "RuntimeDefault",
        f"{name}: RuntimeDefault seccomp required",
    )
    containers = spec.get("containers", [])
    require(
        isinstance(containers, list) and len(containers) == 1,
        f"{name}: exactly one container required",
    )
    initializers = spec.get("initContainers", [])
    require(
        isinstance(initializers, list) and len(initializers) == init_containers,
        f"{name}: unexpected init containers",
    )
    container = cast(dict[str, Any], containers[0])
    for item in [container, *initializers]:
        validate_container_hardening(item, name)
    for volume in spec.get("volumes", []):
        require(
            set(volume) == {"name", "emptyDir"}, f"{name}: only bounded emptyDir volumes allowed"
        )
        require(bool(volume["emptyDir"].get("sizeLimit")), f"{name}: emptyDir must be bounded")
    return container


def validate_database(
    document: dict[str, Any], values: dict[str, Any], service_name: str
) -> None:
    name = str(document["metadata"]["name"])
    require(
        document.get("apiVersion") == "apps/v1",
        f"{name}: unsupported database workload",
    )
    postgres = values["postgres"]
    statefulset = document.get("spec", {})
    require(statefulset.get("replicas") == 1, f"{name}: database must run one replica")
    require(statefulset.get("serviceName") == service_name, f"{name}: database service drift")
    spec = pod_spec(document)
    container = validate_pod_hardening(spec, name)
    security = spec.get("securityContext", {})
    require(
        security.get("runAsUser") == POSTGRES_UID
        and security.get("runAsGroup") == POSTGRES_UID
        and security.get("fsGroup") == POSTGRES_UID,
        f"{name}: database must run as the non-root postgres user {POSTGRES_UID}",
    )
    grace = spec.get("terminationGracePeriodSeconds")
    require(
        isinstance(grace, int) and grace >= 60,
        f"{name}: database needs at least 60 seconds to shut down cleanly",
    )
    image = postgres["image"]
    digest = str(image.get("digest", ""))
    require(
        DIGEST.fullmatch(digest) is not None,
        f"{name}: database image must be pinned by digest",
    )
    require(
        container.get("image") == f"{image.get('repository')}@{digest}",
        f"{name}: image identity drift",
    )
    require(
        container.get("envFrom") == [{"secretRef": {"name": postgres["existingSecret"]}}],
        f"{name}: database must consume one pre-created Secret",
    )
    environment = container.get("env", [])
    require(
        isinstance(environment, list)
        and all(isinstance(item, dict) and set(item) == {"name", "value"} for item in environment)
        and {item["name"] for item in environment}
        == {"PGDATA", "POSTGRES_DB", "POSTGRES_INITDB_ARGS"},
        f"{name}: database environment must carry no credential",
    )
    settings = {item["name"]: item["value"] for item in environment}
    require(
        settings["POSTGRES_INITDB_ARGS"] == "--data-checksums",
        f"{name}: data checksums required",
    )
    require(settings["POSTGRES_DB"] == postgres["database"], f"{name}: database name drift")
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        command = container.get(probe, {}).get("exec", {}).get("command", [])
        require(
            isinstance(command, list)
            and bool(command)
            and "psql" in command[-1]
            and '"$POSTGRES_USER"' in command[-1]
            and "SELECT 1" in command[-1],
            f"{name}: {probe} must run a real query as the configured user",
        )
    mounts = {mount.get("mountPath"): mount.get("name") for mount in container["volumeMounts"]}
    require(
        mounts.get("/var/lib/postgresql/data") == "data",
        f"{name}: database data must live on the persistent volume",
    )
    require(
        {"/var/run/postgresql", "/tmp"} <= set(mounts), f"{name}: bounded runtime paths missing"
    )
    claims = statefulset.get("volumeClaimTemplates", [])
    require(
        isinstance(claims, list) and len(claims) == 1, f"{name}: one persistent volume claim"
    )
    claim = claims[0]
    claim_spec = claim.get("spec", {})
    require(claim.get("metadata", {}).get("name") == "data", f"{name}: volume claim name drift")
    require(
        bool(claim_spec.get("resources", {}).get("requests", {}).get("storage")),
        f"{name}: persistent volume claim must declare its size",
    )
    require(
        claim_spec.get("storageClassName") == postgres["persistence"]["storageClassName"]
        and bool(claim_spec.get("storageClassName")),
        f"{name}: persistent volume claim must name its storage class",
    )
    require(
        claim_spec.get("accessModes") == [postgres["persistence"]["accessMode"]],
        f"{name}: persistent volume access mode drift",
    )


def validate_migration(
    document: dict[str, Any],
    values: dict[str, Any],
    workloads: dict[str, str],
    mode: str,
) -> None:
    name = str(document["metadata"]["name"])
    require(document.get("apiVersion") == "batch/v1", f"{name}: unsupported migration workload")
    validate_migration_hook(document, name, mode)
    require(
        name == workloads["migration" if mode == "upgrade" else "migration-init"],
        f"{name}: migration Job identity drift",
    )
    job = document.get("spec", {})
    require(job.get("backoffLimit") == 0, f"{name}: a failed migration must not be retried")
    require(
        job.get("activeDeadlineSeconds") == values["migration"]["activeDeadlineSeconds"],
        f"{name}: migration deadline drift",
    )
    spec = pod_spec(document)
    require(
        spec.get("restartPolicy") == "Never",
        f"{name}: migration Job must not restart (restartPolicy Never)",
    )
    container = validate_pod_hardening(spec, name, init_containers=1)
    backend_image = image_reference(values["backend"]["image"], name)
    require(
        container.get("image") == backend_image,
        f"{name}: migration must run the backend image identity",
    )
    require(
        container.get("command") == MIGRATION_COMMAND and "args" not in container,
        f"{name}: migration must run alembic upgrade head",
    )
    require(
        container.get("envFrom")
        == [{"secretRef": {"name": values["migration"]["existingSecret"]}}],
        f"{name}: migration must consume one pre-created Secret",
    )
    require("env" not in container, f"{name}: per-key environment values are forbidden")
    wait = spec["initContainers"][0]
    script = "".join(str(item) for item in wait.get("args", []))
    require(
        wait.get("image") == backend_image
        and wait.get("command") == ["python", "-c"]
        and f'"{workloads["database"]}", {values["postgres"]["port"]}' in script,
        f"{name}: migration must wait for the in-chart database Service",
    )
    require(
        "env" not in wait and "envFrom" not in wait,
        f"{name}: the database wait carries no credential",
    )


def validate_documents(
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    chart: dict[str, Any],
    *,
    release_name: str,
    namespace: str,
    migration_mode: str = "bootstrap",
) -> None:
    require(migration_mode in MIGRATION_MODES, f"unknown migration mode: {migration_mode}")
    expected = expected_resources(values)
    observed: set[tuple[str, str]] = set()
    names: set[tuple[str, str]] = set()
    slug = str(chart["name"])
    product_name = str(chart["annotations"]["scaffold.kt.internal/product-name"])
    workloads = {
        component: resource_name(release_name, namespace, slug, component)
        for component in ("backend", "frontend", "database", "migration", "migration-init")
    }
    for document in documents:
        kind = str(document.get("kind", ""))
        metadata = document.get("metadata", {})
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        component = str(labels.get("app.kubernetes.io/component", ""))
        observed.add((kind, component))
        name = str(metadata.get("name", ""))
        require(DNS_LABEL.fullmatch(name) is not None, f"{kind}/{name}: invalid resource name")
        require((kind, name) not in names, f"duplicate resource identity: {kind}/{name}")
        names.add((kind, name))
        require(labels.get("app.kubernetes.io/name") == slug, f"{kind}/{name}: wrong project slug")
        require(
            labels.get("app.kubernetes.io/part-of") == slug, f"{kind}/{name}: wrong part-of label"
        )
        require(
            labels.get("app.kubernetes.io/instance") == release_name,
            f"{kind}/{name}: wrong release label",
        )
        require(
            component in {"backend", "frontend", "database", "migration"}
            and (kind, component) in expected,
            f"{kind}/{name}: forbidden component",
        )
        require(
            annotations.get("scaffold.kt.internal/product-name") == product_name,
            f"{kind}/{name}: product name drift",
        )
        require(
            annotations.get("scaffold.kt.internal/product-slug") == slug,
            f"{kind}/{name}: product slug drift",
        )
        require(
            annotations.get("scaffold.kt.internal/release-namespace") == namespace,
            f"{kind}/{name}: namespace identity drift",
        )
        require(
            labels.get(WORKLOAD_LABEL) == workloads[component],
            f"{kind}/{name}: workload identity drift",
        )
        if kind != "Job":
            require(
                not any(key.startswith("helm.sh/hook") for key in annotations),
                f"{kind}/{name}: only the migration Job may run as a Helm hook",
            )

        if kind == "Service":
            require(
                document.get("spec", {}).get("type") == "ClusterIP",
                f"{name}: only ClusterIP is allowed",
            )
            require(
                "externalName" not in document.get("spec", {}), f"{name}: ExternalName is forbidden"
            )
            continue

        if kind == "Ingress":
            require(
                document.get("apiVersion") == "networking.k8s.io/v1",
                f"{name}: unsupported Ingress API",
            )
            ingress = values["frontend"]["ingress"]
            ingress_spec = document.get("spec", {})
            require(
                ingress_spec.get("ingressClassName") == ingress["className"],
                f"{name}: ingress class drift",
            )
            require(
                ingress_spec.get("tls")
                == [{"hosts": [ingress["host"]], "secretName": ingress["tlsSecretName"]}],
                f"{name}: TLS ingress facts drift",
            )
            rules = ingress_spec.get("rules", [])
            require(
                len(rules) == 1 and rules[0].get("host") == ingress["host"],
                f"{name}: ingress host drift",
            )
            paths = rules[0].get("http", {}).get("paths", [])
            require(
                [path.get("path") for path in paths] == ["/api/dwhcodereview/v1", "/"],
                f"{name}: API/frontend routes drift",
            )
            backend_names = [
                path.get("backend", {}).get("service", {}).get("name") for path in paths
            ]
            require(
                backend_names == [workloads["backend"], workloads["frontend"]],
                f"{name}: ingress service routing drift",
            )
            continue

        if kind == "NetworkPolicy":
            validate_network_policy(document, component, values, workloads)
            continue

        if kind == "StatefulSet":
            validate_database(document, values, workloads["database"])
            continue

        if kind == "Job":
            validate_migration(document, values, workloads, migration_mode)
            continue

        require(
            kind == "Deployment" and document.get("apiVersion") == "apps/v1",
            f"{name}: unsupported workload",
        )
        spec = pod_spec(document)
        container = validate_pod_hardening(spec, name)
        require(
            container.get("image") == image_reference(values[component]["image"], name),
            f"{name}: image identity drift",
        )
        require(
            all(
                container.get(probe)
                for probe in ("startupProbe", "readinessProbe", "livenessProbe")
            ),
            f"{name}: probes incomplete",
        )
        if component == "backend":
            require(
                container.get("envFrom")
                == [{"secretRef": {"name": values["backend"]["existingSecret"]}}],
                f"{name}: backend must consume one pre-created Secret",
            )
            require("env" not in container, f"{name}: per-key environment values are forbidden")
        else:
            require(
                "env" not in container and "envFrom" not in container,
                f"{name}: frontend environment injection is forbidden",
            )
    observed_summary = sorted(observed)
    require(
        observed == expected,
        f"rendered resources must match the enabled components: {observed_summary}",
    )


def resource_names(documents: Iterable[dict[str, Any]]) -> set[str]:
    return {str(item.get("metadata", {}).get("name", "")) for item in documents}


def self_test_values(values: dict[str, Any], chart: dict[str, Any]) -> int:
    rendered = render_chart(values, release_name="generated", namespace="team-a")
    validate_documents(
        rendered,
        values,
        chart,
        release_name="generated",
        namespace="team-a",
    )
    other_namespace = render_chart(values, release_name="generated", namespace="team-b")
    other_release = render_chart(values, release_name="candidate", namespace="team-a")
    require(
        resource_names(rendered).isdisjoint(resource_names(other_namespace)),
        "namespace did not contribute to Kubernetes resource identity",
    )
    require(
        resource_names(rendered).isdisjoint(resource_names(other_release)),
        "Helm release name did not contribute to Kubernetes resource identity",
    )
    return len(rendered)


def self_test(values: dict[str, Any], chart: dict[str, Any]) -> tuple[int, int]:
    """Prove the default render and the render with the optional database and migration."""

    count = self_test_values(values, chart)
    database_values = database_deployment_values(values, str(chart["name"]))
    database_count = self_test_values(database_values, chart)
    return count, database_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--values", type=Path)
    parser.add_argument("--release-name", default="generated")
    parser.add_argument("--namespace", default="default")
    args = parser.parse_args()
    try:
        chart, canonical = validate_chart_layout()
        if args.values is None:
            values = deployment_values(canonical, str(chart["name"]))
            count, database_count = self_test(values, chart)
            print(
                f"chart contract passed: {count} resources, {database_count} with the optional "
                "database and migration, one chart, one values file"
            )
            return 0
        supplied = load_yaml(args.values.resolve(strict=True))
        require(
            {"backend", "frontend"} <= set(supplied) <= VALUE_SECTIONS,
            "supplied values must contain backend/frontend and the optional postgres/migration only",
        )
        documents = render_chart(
            supplied,
            release_name=args.release_name,
            namespace=args.namespace,
        )
        validate_documents(
            documents,
            merge_values(canonical, supplied),
            chart,
            release_name=args.release_name,
            namespace=args.namespace,
        )
        print(f"chart contract passed: {len(documents)} resources")
        return 0
    except (OSError, PolicyError) as exc:
        print(f"chart contract failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
