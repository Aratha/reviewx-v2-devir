#!/usr/bin/env bash
# GitHub publishes images; the existing Azure job supplies KUBECONFIG and runs Helm.
set +x
set -euo pipefail

chart="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
release="${RELEASE:-dwhcodereview}"
namespace="${NAMESPACE:-dwhcodereview}"
values_file="${VALUES_FILE:-$chart/values.yaml}"
image_tag="${IMAGE_TAG:-latest}"
mode=apply

usage() {
  echo 'Usage: helm/dwhcodereview/deploy.sh [--render|--apply] [--values <values.yaml>] [--release <name>] [--namespace <name>]' >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --render) mode=render; shift ;;
    --apply) mode=apply; shift ;;
    --values) [[ $# -ge 2 ]] || { usage; exit 2; }; values_file="$2"; shift 2 ;;
    --release) [[ $# -ge 2 ]] || { usage; exit 2; }; release="$2"; shift 2 ;;
    --namespace) [[ $# -ge 2 ]] || { usage; exit 2; }; namespace="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[[ -n "$values_file" && -f "$values_file" ]] || { usage; exit 2; }
[[ "$release" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || { usage; exit 2; }
[[ "$namespace" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || { usage; exit 2; }

if [[ "$image_tag" == latest ]] && \
  { [[ "${BUILD_SOURCEVERSION+x}" == x ]] || [[ "${TF_BUILD:-}" =~ ^[tT][rR][uU][eE]$ ]]; }; then
  [[ "${BUILD_SOURCEVERSION:-}" =~ ^[0123456789abcdef]{40}$ ]] || {
    echo 'BUILD_SOURCEVERSION must contain exactly 40 lowercase hexadecimal characters' >&2
    exit 2
  }
  image_tag="$BUILD_SOURCEVERSION"
elif [[ ! "$image_tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo 'IMAGE_TAG must be a valid OCI tag' >&2
  exit 2
fi

image_args=(
  --set-string "backend.image.tag=$image_tag"
  --set-string backend.image.digest=
  --set-string "frontend.image.tag=$image_tag"
  --set-string frontend.image.digest=
)
common=(--values "$values_file" --namespace "$namespace" "${image_args[@]}")

helm lint "$chart" "${common[@]}" >&2
if [[ "$mode" == render ]]; then
  exec helm template "$release" "$chart" "${common[@]}"
fi

# Registry answer for one rendered image: 0 published, 1 absent, 2 not established.
# The GHCR proxy cache answers anonymous pulls with a bearer challenge; the token
# never reaches the log.
registry_manifest_state() {
  local reference="$1" name reference_tag host repository url code challenge realm service scope token
  local accept='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'
  if [[ "$reference" == *@* ]]; then
    name="${reference%@*}"; reference_tag="${reference##*@}"
  else
    name="${reference%:*}"; reference_tag="${reference##*:}"
  fi
  host="${name%%/*}"; repository="${name#*/}"
  [[ -n "$reference_tag" && "$host" != "$name" ]] || return 2
  url="https://$host/v2/$repository/manifests/$reference_tag"
  challenge="$(curl --silent --max-time 20 --head --output /dev/null --dump-header - \
    --header "Accept: $accept" "$url" 2>/dev/null | tr -d '\r')" || return 2
  code="$(sed -nE 's#^HTTP/[0-9.]+ ([0-9]{3}).*#\1#p' <<< "$challenge" | tail -n 1)"
  if [[ "$code" == 401 ]]; then
    challenge="$(grep -i '^www-authenticate: *bearer ' <<< "$challenge" | head -n 1)"
    realm="$(sed -nE 's/.*realm="([^"]+)".*/\1/p' <<< "$challenge")"
    service="$(sed -nE 's/.*service="([^"]+)".*/\1/p' <<< "$challenge")"
    scope="$(sed -nE 's/.*scope="([^"]+)".*/\1/p' <<< "$challenge")"
    [[ "$realm" == https://* ]] || return 2
    token="$(curl --silent --max-time 20 --get "$realm" --data-urlencode "service=$service" \
      --data-urlencode "scope=$scope" 2>/dev/null \
      | sed -nE 's/.*"(token|access_token)"[[:space:]]*:[[:space:]]*"([^"]+)".*/\2/p' | head -n 1)"
    [[ -n "$token" ]] || return 2
    code="$(curl --silent --max-time 20 --head --output /dev/null --write-out '%{http_code}' \
      --header "Accept: $accept" --header "Authorization: Bearer $token" "$url" 2>/dev/null)" \
      || return 2
  fi
  case "$code" in
    200) return 0 ;;
    404) return 1 ;;
    *) return 2 ;;
  esac
}

# Azure starts on the same push that GitHub builds, and a failed scan never publishes.
# Wait for every rendered image before any cluster change; a missing image stops here.
# When the registry cannot answer, Helm still keeps the ready pods of the last release.
wait_for_published_images() {
  local rendered references reference state missing unknown deadline
  rendered="$(helm template "$release" "$chart" "${common[@]}")" || return 1
  references="$(sed -nE 's/^[[:space:]]*image:[[:space:]]*"?([^"[:space:]]+)"?[[:space:]]*$/\1/p' \
    <<< "$rendered" | sort -u)"
  [[ -n "$references" ]] || { echo '[IMAGE] no workload image was rendered' >&2; return 1; }
  if ! command -v curl >/dev/null; then
    echo '[IMAGE] UNKNOWN curl is unavailable; publication was not checked' >&2
    return 0
  fi
  deadline=$((SECONDS + ${IMAGE_WAIT_SECONDS:-1200}))
  while :; do
    missing=""; unknown=""
    for reference in $references; do
      state=0
      registry_manifest_state "$reference" || state=$?
      case "$state" in
        0) ;;
        1) missing="$missing $reference" ;;
        *) unknown="$unknown $reference" ;;
      esac
    done
    if [[ -z "$missing" ]]; then
      if [[ -n "$unknown" ]]; then
        echo "[IMAGE] UNKNOWN the registry did not answer for:$unknown" >&2
      else
        echo '[IMAGE] PUBLISHED every rendered image'
      fi
      return 0
    fi
    (( SECONDS < deadline )) || break
    echo "[IMAGE] WAITING for:$missing"
    sleep "${IMAGE_POLL_SECONDS:-30}"
  done
  echo "[IMAGE] MISSING$missing; the build did not publish them, no cluster change was made" >&2
  return 1
}

release_field() {
  local state pattern
  state="$(helm --namespace "$namespace" list --all --filter "^${release}$" --output json \
    2>/dev/null || true)"
  pattern="\"$1\"[[:space:]]*:[[:space:]]*\"([^\"]*)\""
  if [[ "$state" =~ $pattern ]]; then printf '%s' "${BASH_REMATCH[1]}"; fi
}

# A pending release is either another run's live operation or an interrupted one.
# Wait for a live operation to settle; recover an interrupted upgrade by rollback,
# which keeps the served workloads. Only a never-installed release is uninstalled.
settle_pending_release() {
  local status updated started limit
  status="$(release_field status)"
  [[ "$status" == pending-* ]] || return 0
  limit="${PENDING_WAIT_SECONDS:-1800}"
  updated="$(release_field updated)"
  # GNU date reads an empty value as midnight, so only a reported time is aged.
  if [[ -n "$updated" ]] && started="$(date -u -d "${updated% UTC}" +%s 2>/dev/null)"; then
    limit=$(( limit - ($(date -u +%s) - started) ))
  fi
  local deadline=$((SECONDS + (limit > 0 ? limit : 0)))
  while [[ "$status" == pending-* ]] && (( SECONDS < deadline )); do
    echo "[RELEASE] $status; waiting for the running deployment to finish"
    sleep "${PENDING_POLL_SECONDS:-20}"
    status="$(release_field status)"
  done
  case "$status" in
    pending-install)
      echo '[RELEASE] pending-install never served; removing it'
      helm uninstall "$release" --namespace "$namespace" --wait || return 1
      ;;
    pending-upgrade|pending-rollback)
      echo "[RELEASE] $status is interrupted; rolling back to the last release"
      helm rollback "$release" --namespace "$namespace" --wait --timeout "${HELM_TIMEOUT:-30m}" || {
        echo "[RELEASE] rollback failed; the release is left in place for an operator" >&2
        return 1
      }
      ;;
  esac
}

command -v kubectl >/dev/null || {
  echo 'kubectl is required for deployment' >&2
  exit 1
}
wait_for_published_images || exit 1
kubectl get namespace "$namespace" >/dev/null 2>&1 || kubectl create namespace "$namespace"

# The shared wildcard TLS Secret is namespace-scoped. The established nonprod
# runner may copy its public certificate and private key into a new application
# namespace without putting either value in Git, Helm arguments or logs.
if [[ "${TF_BUILD:-}" =~ ^[tT][rR][uU][eE]$ ]] \
  && [[ "${TLS_COPY_ENABLED:-true}" == true ]]; then
  tls_source_namespace="${TLS_SOURCE_NAMESPACE:-kt-verim}"
  tls_source_secret="${TLS_SOURCE_SECRET:-ailab-tls}"
  tls_target_secret="${TLS_TARGET_SECRET:-ailab-tls}"
  if ! kubectl --namespace "$namespace" get secret "$tls_target_secret" >/dev/null 2>&1; then
    command -v openssl >/dev/null || {
      echo 'openssl is required to copy the shared TLS Secret' >&2
      exit 1
    }
    temporary="$(mktemp -d)"
    trap 'rm -rf "$temporary"' EXIT
    umask 077
    kubectl --namespace "$tls_source_namespace" get secret "$tls_source_secret" \
      --output 'jsonpath={.data.tls\.crt}' | openssl base64 -d -A > "$temporary/tls.crt"
    kubectl --namespace "$tls_source_namespace" get secret "$tls_source_secret" \
      --output 'jsonpath={.data.tls\.key}' | openssl base64 -d -A > "$temporary/tls.key"
    [[ -s "$temporary/tls.crt" && -s "$temporary/tls.key" ]] || {
      echo 'shared TLS source is incomplete' >&2
      exit 1
    }
    kubectl --namespace "$namespace" create secret tls "$tls_target_secret" \
      --cert="$temporary/tls.crt" --key="$temporary/tls.key" >/dev/null
  fi
fi

settle_pending_release || exit 1

exec helm upgrade --install "$release" "$chart" \
  --create-namespace --reset-values --atomic --wait \
  --timeout "${HELM_TIMEOUT:-30m}" "${common[@]}"
