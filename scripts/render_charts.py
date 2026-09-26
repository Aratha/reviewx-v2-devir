#!/usr/bin/env python3
"""Render and validate the generated project's single application Helm chart."""

from __future__ import annotations

import argparse
import copy
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
}
FORBIDDEN_COMPONENTS = {
    "postgres",
    "redis",
    "worker",
    "migrate",
    "migration",
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
        template_files == EXPECTED_TEMPLATES, "chart templates must contain backend/frontend only"
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

    require(set(values) == {"backend", "frontend"}, "values must contain backend/frontend only")
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
    return chart, values


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


def validate_documents(
    documents: list[dict[str, Any]],
    values: dict[str, Any],
    chart: dict[str, Any],
    *,
    release_name: str,
    namespace: str,
) -> None:
    expected = {
        ("Deployment", "backend"),
        ("Deployment", "frontend"),
        ("Ingress", "frontend"),
        ("NetworkPolicy", "backend"),
        ("NetworkPolicy", "frontend"),
        ("Service", "backend"),
        ("Service", "frontend"),
    }
    observed: set[tuple[str, str]] = set()
    names: set[tuple[str, str]] = set()
    slug = str(chart["name"])
    product_name = str(chart["annotations"]["scaffold.kt.internal/product-name"])
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
        require(component in {"backend", "frontend"}, f"{kind}/{name}: forbidden component")
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
                backend_names
                == [
                    next(
                        item["metadata"]["name"]
                        for item in documents
                        if item.get("kind") == "Service"
                        and item.get("metadata", {})
                        .get("labels", {})
                        .get("app.kubernetes.io/component")
                        == "backend"
                    ),
                    next(
                        item["metadata"]["name"]
                        for item in documents
                        if item.get("kind") == "Service"
                        and item.get("metadata", {})
                        .get("labels", {})
                        .get("app.kubernetes.io/component")
                        == "frontend"
                    ),
                ],
                f"{name}: ingress service routing drift",
            )
            continue

        if kind == "NetworkPolicy":
            require(
                document.get("apiVersion") == "networking.k8s.io/v1",
                f"{name}: unsupported NetworkPolicy API",
            )
            policy = document.get("spec", {})
            require(
                policy.get("policyTypes") == ["Ingress", "Egress"],
                f"{name}: ingress/egress policy required",
            )
            require(
                "ingress" in policy and "egress" in policy, f"{name}: policy directions incomplete"
            )
            expected_policy = values[component]["networkPolicy"]
            require(
                policy.get("ingress") == expected_policy["ingress"], f"{name}: ingress peer drift"
            )
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
            continue

        require(
            kind == "Deployment" and document.get("apiVersion") == "apps/v1",
            f"{name}: unsupported workload",
        )
        spec = pod_spec(document)
        require(
            spec.get("automountServiceAccountToken") is False,
            f"{name}: service account token enabled",
        )
        security = spec.get("securityContext", {})
        require(security.get("runAsNonRoot") is True, f"{name}: runAsNonRoot required")
        require(
            security.get("seccompProfile", {}).get("type") == "RuntimeDefault",
            f"{name}: RuntimeDefault seccomp required",
        )
        containers = spec.get("containers", [])
        require(
            isinstance(containers, list) and len(containers) == 1,
            f"{name}: exactly one container required",
        )
        container = containers[0]
        expected_image = values[component]["image"]
        repository = str(expected_image.get("repository", ""))
        digest = str(expected_image.get("digest", ""))
        tag = str(expected_image.get("tag", ""))
        require(bool(repository), f"{name}: image repository is required")
        if digest:
            require(DIGEST.fullmatch(digest) is not None, f"{name}: invalid image digest")
            expected_reference = f"{repository}@{digest}"
        else:
            require(OCI_TAG.fullmatch(tag) is not None, f"{name}: invalid image tag")
            expected_reference = f"{repository}:{tag}"
        require(container.get("image") == expected_reference, f"{name}: image identity drift")
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
        require(
            all(
                container.get(probe)
                for probe in ("startupProbe", "readinessProbe", "livenessProbe")
            ),
            f"{name}: probes incomplete",
        )
        resources = container.get("resources", {})
        require(
            bool(resources.get("requests")) and bool(resources.get("limits")),
            f"{name}: resources incomplete",
        )
        for volume in spec.get("volumes", []):
            if "emptyDir" in volume:
                require(
                    bool(volume["emptyDir"].get("sizeLimit")), f"{name}: emptyDir must be bounded"
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
        f"rendered resources must be backend/frontend only: {observed_summary}",
    )


def resource_names(documents: Iterable[dict[str, Any]]) -> set[str]:
    return {str(item.get("metadata", {}).get("name", "")) for item in documents}


def self_test(values: dict[str, Any], chart: dict[str, Any]) -> int:
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
            count = self_test(values, chart)
            print(f"chart contract passed: {count} resources, one chart, one values file")
            return 0
        supplied = load_yaml(args.values.resolve(strict=True))
        require(
            set(supplied) == {"backend", "frontend"},
            "supplied values must contain backend/frontend only",
        )
        documents = render_chart(
            supplied,
            release_name=args.release_name,
            namespace=args.namespace,
        )
        validate_documents(
            documents,
            supplied,
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
