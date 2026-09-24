#!/usr/bin/env bash
# KT Verim convention: GitHub builds/pushes; the approved Azure job runs Helm.
# The Azure job calls this entry point without arguments; KUBECONFIG comes from
# its Secure File. No release manifest, registry lookup, Python or gh requirement.
set +x
set -euo pipefail

RELEASE="${RELEASE:-dwhcodereview}"
NAMESPACE="${NAMESPACE:-dwhcodereview}"
CHART_DIR="${CHART_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VALUES_FILE="${VALUES_FILE:-$CHART_DIR/values.yaml}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
HELM_TIMEOUT="${HELM_TIMEOUT:-30m}"
INGRESS_HOST="${INGRESS_HOST:-}"
TLS_SECRET="${TLS_SECRET:-}"
TLS_SOURCE_NAMESPACE="${TLS_SOURCE_NAMESPACE:-kt-verim}"
TLS_SOURCE_SECRET="${TLS_SOURCE_SECRET:-ailab-tls}"
RUNTIME_SECRET="${RUNTIME_SECRET:-dwhcodereview-runtime}"
# Non-empty pipeline values of these keys are written to the runtime Secret;
# absent or empty ones keep the live cluster value.
RUNTIME_SECRET_KEYS=(MSSQL_CONNECTION_STRING MSSQL_PASSWORD API_ACCESS_TOKEN API_ADMIN_TOKEN LLM_API_KEY)
mode=apply

usage() {
  printf 'Usage: bash helm/dwhcodereview/deploy.sh [--render|--apply]\n'
  printf 'IMAGE_TAG=latest; RELEASE/NAMESPACE=dwhcodereview; HELM_TIMEOUT=30m.\n'
  printf 'KUBECONFIG comes from the Azure Secure File. See README for optional overrides.\n'
  printf 'In Azure, latest resolves to the full BUILD_SOURCEVERSION commit; explicit tags are preserved.\n'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --render) mode=render; shift ;;
    --apply) mode=apply; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

dns_label='^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
[[ -f "$VALUES_FILE" ]] || { echo 'VALUES_FILE must name an existing values file' >&2; exit 2; }
[[ "$RELEASE" =~ $dns_label && "$NAMESPACE" =~ $dns_label && "$RUNTIME_SECRET" =~ $dns_label ]] || {
  echo 'RELEASE, NAMESPACE and RUNTIME_SECRET must be DNS labels' >&2
  exit 2
}

# The existing Azure task exports latest and starts on the same push as GitHub.
# Bind that request to its build commit, whose tag GitHub publishes for both images.
# Helm --wait/rollback handles a not-yet-published image without selecting an older latest.
if [[ "$IMAGE_TAG" == latest ]] && \
  { [[ "${BUILD_SOURCEVERSION+x}" == x ]] || [[ "${TF_BUILD:-}" =~ ^[tT][rR][uU][eE]$ ]]; }; then
  if ! [[ "${BUILD_SOURCEVERSION:-}" =~ ^[0123456789abcdef]{40}$ ]]; then
    printf '[IMAGE] ERROR Azure latest requires a valid full BUILD_SOURCEVERSION commit; no deployment attempted.\n' >&2
    exit 2
  fi
  IMAGE_TAG="$BUILD_SOURCEVERSION"
  # stderr keeps --render output a clean manifest stream.
  printf '[IMAGE] Azure latest resolved to build commit %s\n' "$IMAGE_TAG" >&2
elif ! [[ "$IMAGE_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  printf '[IMAGE] ERROR IMAGE_TAG must be a valid OCI tag; no deployment attempted.\n' >&2
  exit 2
fi

# Empty digest overrides ensure an existing digest cannot silently override IMAGE_TAG.
values=(--values "$VALUES_FILE"
        --set-string "backend.image.tag=$IMAGE_TAG" --set-string backend.image.digest=
        --set-string "frontend.image.tag=$IMAGE_TAG" --set-string frontend.image.digest=
        --set-string "backend.existingSecret=$RUNTIME_SECRET")
if [[ -n "$INGRESS_HOST" ]]; then values+=(--set-string "frontend.ingress.host=$INGRESS_HOST"); fi
if [[ -n "$TLS_SECRET" ]]; then values+=(--set-string "frontend.ingress.tlsSecretName=$TLS_SECRET"); fi

helm lint "$CHART_DIR" --namespace "$NAMESPACE" "${values[@]}" >&2
if [[ "$mode" == render ]]; then
  exec helm template "$RELEASE" "$CHART_DIR" --namespace "$NAMESPACE" "${values[@]}"
fi

command -v kubectl >/dev/null || { echo 'kubectl is required for deployment' >&2; exit 1; }
umask 077
work="$(mktemp -d "${TMPDIR:-/tmp}/dwhcodereview-deploy.XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Use the existing Azure KUBECONFIG. Report authorization decisions, never Secret
# data, kubeconfig content, or raw credential-plugin diagnostics. A denied probe
# is informational: the real Helm/rollout command must retain its own exit code.
report_permission() {
  local verb="$1" resource="$2" namespace="$3" answer code=0 decision=UNKNOWN
  answer="$(kubectl auth can-i "$verb" "$resource" --namespace "$namespace" \
    --request-timeout 10s 2>/dev/null)" || code=$?
  if [ "$code" -eq 0 ] && [ "$answer" = yes ]; then
    decision=ALLOW
  elif [ "$code" -eq 1 ] && [[ "$answer" = no || "$answer" = "no - "* ]]; then
    decision=DENY
  fi
  printf '[RBAC] %s namespace=%s verb=%s resource=%s (exit=%s)\n' \
    "$decision" "$namespace" "$verb" "$resource" "$code"
  RBAC_DECISION="$decision"
}

printf '[RBAC] BEGIN existing deployment identity; UNKNOWN means no authorization decision obtained\n'
for verb in get update; do report_permission "$verb" "secrets/$RUNTIME_SECRET" "$NAMESPACE"; done
report_permission get "secrets/${TLS_SECRET:-ailab-tls}" "$NAMESPACE"
for verb in list create; do report_permission "$verb" secrets "$NAMESPACE"; done
# Probe only the named candidate used by kt-verim; this does not read its contents
# or establish that the source Secret exists or holds the matching private key.
report_permission get "secrets/$TLS_SOURCE_SECRET" "$TLS_SOURCE_NAMESPACE"
report_permission list ingresses.networking.k8s.io "$NAMESPACE"
for verb in get patch watch; do report_permission "$verb" deployments.apps "$NAMESPACE"; done
printf '[RBAC] END authorization only; resource existence and admission remain separate\n'

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"

# Runs before Helm so the backend Pod starts with its Secret. Live values are kept
# as their base64 text and pipeline values never pass through argv; only key names
# reach the log. An unmapped Azure secret variable arrives as its literal macro
# text and is rejected instead of stored.
runtime_secret_written=false
ensure_runtime_secret() {
  local key encoded existing live_keys i found macro='^\$\([A-Za-z0-9_.]+\)$'
  local provided=() changed=() keys=() data=()
  runtime_error() { printf '[RUNTIME] ERROR %s\n' "$1" >&2; exit 1; }
  for key in "${RUNTIME_SECRET_KEYS[@]}"; do
    [[ -n "${!key:-}" ]] || continue
    if [[ "${!key}" =~ $macro ]]; then
      runtime_error "$key is an unresolved Azure variable; no Secret was changed."
    fi
    provided+=("$key")
  done
  existing="$(kubectl get secret "$RUNTIME_SECRET" --namespace "$NAMESPACE" \
    --request-timeout 10s --ignore-not-found --output name 2>/dev/null)" \
    || runtime_error "Cannot check Secret $NAMESPACE/$RUNTIME_SECRET; no Secret was changed."
  if [[ -n "$existing" && ${#provided[@]} -eq 0 ]]; then
    printf '[RUNTIME] EXISTS namespace=%s secret=%s; preserved\n' "$NAMESPACE" "$RUNTIME_SECRET"
    return 0
  fi
  if [[ -n "$existing" ]]; then
    live_keys="$(kubectl get secret "$RUNTIME_SECRET" --namespace "$NAMESPACE" --request-timeout 10s \
      --output 'go-template={{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}' 2>/dev/null)" \
      || runtime_error "Cannot read Secret $NAMESPACE/$RUNTIME_SECRET; no Secret was changed."
    while IFS= read -r key; do
      [[ -n "$key" ]] || continue
      [[ "$key" =~ ^[-._a-zA-Z0-9]+$ ]] \
        || runtime_error "Secret $NAMESPACE/$RUNTIME_SECRET has an invalid key; no Secret was changed."
      encoded="$(kubectl get secret "$RUNTIME_SECRET" --namespace "$NAMESPACE" --request-timeout 10s \
        --output "go-template={{index .data \"$key\"}}" 2>/dev/null)" \
        || runtime_error "Cannot read Secret $NAMESPACE/$RUNTIME_SECRET; no Secret was changed."
      keys+=("$key")
      data+=("$encoded")
    done <<< "$live_keys"
  fi
  for key in ${provided[@]+"${provided[@]}"}; do
    command -v openssl >/dev/null || runtime_error 'OpenSSL is required to encode the runtime Secret.'
    encoded="$(printf '%s' "${!key}" | openssl base64 -A)" \
      || runtime_error "Cannot encode $key; no Secret was changed."
    found=false
    for i in ${keys[@]+"${!keys[@]}"}; do
      [[ "${keys[$i]}" == "$key" ]] || continue
      found=true
      [[ "${data[$i]}" != "$encoded" ]] || continue 2
      data[$i]="$encoded"
    done
    if [[ "$found" == false ]]; then keys+=("$key"); data+=("$encoded"); fi
    changed+=("$key")
  done
  if [[ -n "$existing" && ${#changed[@]} -eq 0 ]]; then
    printf '[RUNTIME] UNCHANGED namespace=%s secret=%s\n' "$NAMESPACE" "$RUNTIME_SECRET"
    return 0
  fi
  {
    printf 'apiVersion: v1\nkind: Secret\ntype: Opaque\nmetadata:\n  name: %s\n  namespace: %s\n' \
      "$RUNTIME_SECRET" "$NAMESPACE"
    if [[ ${#keys[@]} -eq 0 ]]; then printf 'data: {}\n'; else printf 'data:\n'; fi
    for i in ${keys[@]+"${!keys[@]}"}; do printf '  %s: "%s"\n' "${keys[$i]}" "${data[$i]}"; done
  } > "$work/runtime.yaml"
  # API errors may echo submitted data, so only a fixed error message reaches logs.
  if [[ -n "$existing" ]]; then
    kubectl replace --filename "$work/runtime.yaml" --request-timeout 10s >/dev/null 2>&1 \
      || runtime_error "Update failed for $NAMESPACE/$RUNTIME_SECRET (API/admission)."
    printf '[RUNTIME] UPDATED namespace=%s secret=%s keys=%s\n' \
      "$NAMESPACE" "$RUNTIME_SECRET" "${changed[*]}"
  else
    # Create only: a concurrent Secret is never overwritten or adopted.
    kubectl create --filename "$work/runtime.yaml" --request-timeout 10s >/dev/null 2>&1 \
      || runtime_error "Create failed for $NAMESPACE/$RUNTIME_SECRET (API/admission/race)."
    printf '[RUNTIME] CREATED namespace=%s secret=%s keys=%s\n' \
      "$NAMESPACE" "$RUNTIME_SECRET" "${changed[*]:-none}"
  fi
  runtime_secret_written=true
}
ensure_runtime_secret

# Runs after Helm has created the Ingress. The installed Ingress supplies the
# effective Secret name and host; an existing Secret is never replaced.
ensure_tls_secret() (
  set +x
  tls_error() { printf '[TLS] ERROR %s\n' "$1" >&2; exit 1; }
  routes="$(kubectl get ingress --namespace "$NAMESPACE" --request-timeout 10s \
    --selector "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=frontend" \
    --output 'jsonpath={range .items[*]}{.spec.tls[0].secretName}{"\t"}{.spec.tls[0].hosts[0]}{"\n"}{end}' \
    2>/dev/null)" || tls_error "Cannot read the deployed Ingress in $NAMESPACE."
  IFS=$'\t' read -r tls_name tls_host <<< "$routes" || true
  if [ -z "$tls_name" ] && [ -z "$tls_host" ]; then
    printf '[TLS] SKIP no TLS Ingress for namespace=%s release=%s\n' "$NAMESPACE" "$RELEASE"
    exit 0
  fi
  [ -n "$tls_name" ] && [ -n "$tls_host" ] || tls_error 'Ingress TLS name/host is incomplete.'
  existing="$(kubectl get secret "$tls_name" --namespace "$NAMESPACE" \
    --request-timeout 10s --ignore-not-found --output name 2>/dev/null)" \
    || tls_error "Cannot check target Secret $NAMESPACE/$tls_name; no Secret was changed."
  if [ -n "$existing" ]; then
    printf '[TLS] EXISTS namespace=%s secret=%s; preserved, certificate not verified\n' \
      "$NAMESPACE" "$tls_name"
    exit 0
  fi

  report_permission create secrets "$NAMESPACE"
  [ "$RBAC_DECISION" = ALLOW ] || tls_error "Secret create permission is $RBAC_DECISION in $NAMESPACE."
  report_permission get "secrets/$TLS_SOURCE_SECRET" "$TLS_SOURCE_NAMESPACE"
  [ "$RBAC_DECISION" = ALLOW ] \
    || tls_error "Source Secret read permission is $RBAC_DECISION in $TLS_SOURCE_NAMESPACE."
  command -v openssl >/dev/null || tls_error 'OpenSSL is required for TLS certificate validation.'
  tls_tmp="$work/tls"
  mkdir "$tls_tmp" || tls_error 'Cannot create a private temporary directory.'

  cert_file="$CHART_DIR/certs/ailab-test.crt"
  [ -s "$cert_file" ] || tls_error 'The repository certificate chain is missing.'
  # Trust the versioned issuer chain, not an arbitrary source Secret certificate.
  awk '/-----BEGIN CERTIFICATE-----/ { cert++ } cert > 1 { print }' \
    "$cert_file" > "$tls_tmp/ca.crt"
  openssl verify -purpose sslserver -verify_hostname "$tls_host" \
    -CAfile "$tls_tmp/ca.crt" "$cert_file" >/dev/null 2>&1 \
    || tls_error 'Repository certificate chain, validity or hostname validation failed.'

  kubectl get secret "$TLS_SOURCE_SECRET" --namespace "$TLS_SOURCE_NAMESPACE" \
    --request-timeout 10s \
    --output 'jsonpath={.type}{"\n"}{.data.tls\.crt}{"\n"}{.data.tls\.key}{"\n"}' \
    > "$tls_tmp/source" 2>/dev/null \
    || tls_error "Cannot read source Secret $TLS_SOURCE_NAMESPACE/$TLS_SOURCE_SECRET."
  {
    IFS= read -r secret_type
    IFS= read -r encoded_cert
    IFS= read -r encoded_key
  } < "$tls_tmp/source" || tls_error 'Source TLS Secret fields are incomplete.'
  [ "$secret_type" = kubernetes.io/tls ] && [ -n "$encoded_cert" ] && [ -n "$encoded_key" ] \
    || tls_error 'Source must be a kubernetes.io/tls Secret containing tls.crt and tls.key.'
  printf '%s' "$encoded_key" | openssl base64 -d -A > "$tls_tmp/tls.key" 2>/dev/null \
    || tls_error 'Cannot decode the source private key.'
  unset encoded_cert encoded_key

  # Real kubectl validates the PEM certificate/key pair without writing a resource.
  # Keep compatibility with the older Azure kubectl's boolean dry-run flag.
  create_help="$(kubectl create secret tls --help 2>/dev/null)" \
    || tls_error 'Cannot inspect kubectl TLS Secret support.'
  dry_run=--dry-run=client
  if [[ "$create_help" == *"--dry-run=false"* ]]; then dry_run=--dry-run=true; fi
  kubectl create secret tls "$tls_name" --namespace "$NAMESPACE" \
    --cert "$cert_file" --key "$tls_tmp/tls.key" "$dry_run" --output json \
    > "$tls_tmp/secret.json" 2>/dev/null \
    || tls_error 'Source private key does not form a valid pair with the repository certificate.'
  printf '[TLS] VALIDATED namespace=%s secret=%s key-source=%s/%s\n' \
    "$NAMESPACE" "$tls_name" "$TLS_SOURCE_NAMESPACE" "$TLS_SOURCE_SECRET"

  # Create only: a concurrent/existing Secret is never overwritten or adopted.
  kubectl create --filename "$tls_tmp/secret.json" --namespace "$NAMESPACE" \
    --request-timeout 10s >/dev/null 2>&1 \
    || tls_error "Create failed for $NAMESPACE/$tls_name (API/admission/race); no overwrite attempted."
  printf '[TLS] CREATED namespace=%s secret=%s; served HTTPS certificate not verified\n' \
    "$NAMESPACE" "$tls_name"
)

# An interrupted Helm operation leaves the release pending and blocks every later
# upgrade. A never-installed release is removed; others return to the last
# deployed revision. The data PVC carries helm.sh/resource-policy=keep.
release_state="$(helm list --namespace "$NAMESPACE" --all \
  --filter "^${RELEASE}\$" --output json 2>/dev/null)" \
  || { echo 'Helm release state could not be read' >&2; exit 1; }
release_status=""
status_pattern='"status"[[:space:]]*:[[:space:]]*"([^"]*)"'
if [[ "$release_state" =~ $status_pattern ]]; then release_status="${BASH_REMATCH[1]}"; fi
case "$release_status" in
  pending-install) helm uninstall "$RELEASE" --namespace "$NAMESPACE" --wait || true ;;
  pending-upgrade|pending-rollback) helm rollback "$RELEASE" --namespace "$NAMESPACE" --wait || true ;;
esac

# The previous chart named its Ingress after its fullname; the new entry name is
# hashed. Remove that legacy object first so ingress-nginx never sees two owners
# of the same host/path during Helm's create-before-delete transition.
case "$RELEASE" in
  *dwhcodereview*) legacy_ingress="$RELEASE" ;;
  *) legacy_ingress="$RELEASE-dwhcodereview" ;;
esac
legacy_owner="$(kubectl get ingress "$legacy_ingress" --namespace "$NAMESPACE" --request-timeout 10s \
  --ignore-not-found --output 'jsonpath={.metadata.annotations.meta\.helm\.sh/release-name}' \
  2>/dev/null)" || { echo 'Cannot inspect the legacy Ingress' >&2; exit 1; }
if [[ "$legacy_owner" == "$RELEASE" ]]; then
  kubectl delete ingress "$legacy_ingress" --namespace "$NAMESPACE" --wait=true
fi

backend_generation() {
  kubectl get deployments --namespace "$NAMESPACE" --request-timeout 10s \
    --selector "app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=backend" \
    --output 'jsonpath={.items[*].metadata.generation}' 2>/dev/null || true
}
generation_before="$(backend_generation)"

# Helm 3/4 spelling compatibility for the same rollback behavior as KT Verim.
upgrade_help="$(helm upgrade --help)"
if [[ "$upgrade_help" == *"--atomic"* ]]; then rollback_flag=--atomic
else rollback_flag=--rollback-on-failure; fi

helm upgrade --install "$RELEASE" "$CHART_DIR" \
  --namespace "$NAMESPACE" --create-namespace --reset-values \
  "$rollback_flag" --wait --timeout "$HELM_TIMEOUT" "${values[@]}"

ensure_tls_secret

# Like KT Verim: an unchanged latest tag alone does not change the pod template.
# An updated runtime Secret reaches the process env only through new backend Pods.
restart_selector=""
if [[ "$IMAGE_TAG" == latest ]]; then
  restart_selector="app.kubernetes.io/instance=$RELEASE"
elif [[ "$runtime_secret_written" == true && -n "$generation_before" \
  && "$(backend_generation)" == "$generation_before" ]]; then
  restart_selector="app.kubernetes.io/instance=$RELEASE,app.kubernetes.io/component=backend"
fi
if [[ -n "$restart_selector" ]]; then
  # Older kubectl rollout restart lacks --selector; restart each Deployment by name.
  deployments="$(kubectl get deployments --namespace "$NAMESPACE" \
    --selector "$restart_selector" --output 'jsonpath={.items[*].metadata.name}')"
  for deployment in $deployments; do
    kubectl rollout restart "deployment/$deployment" --namespace "$NAMESPACE"
    kubectl rollout status "deployment/$deployment" --namespace "$NAMESPACE" --timeout "$HELM_TIMEOUT"
  done
fi
helm status "$RELEASE" --namespace "$NAMESPACE"
