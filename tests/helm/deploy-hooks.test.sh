#!/usr/bin/env bash
# Regression test of helm/dwhcodereview/deploy-hooks.sh against a fake kubectl on PATH
# (specs/application-foundation/PRDs/002-kubernetes-delivery Requirement 5, Acceptance 1).
# Needs bash and openssl only; the fake stores Secret values as files and records every argv, so the
# test proves that no value reaches a command argument, stdout or stderr.
# Run: tests/helm/deploy-hooks.test.sh
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
hook="$root/helm/dwhcodereview/deploy-hooks.sh"
layer="$root/helm/dwhcodereview/values-project.yaml"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/deploy-hooks-test.XXXXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT
failures=0
current=""

# --- fake kubectl ----------------------------------------------------------------------------------
mkdir "$scratch/bin"
cat > "$scratch/bin/kubectl" <<'FAKE'
#!/usr/bin/env bash
# Minimal kubectl for the hook: Secrets live in $FAKE_STATE/secrets/<name>/<key> as raw values.
set -euo pipefail
printf '%s\n' "$*" >> "$FAKE_STATE/argv.log"
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
set -- "${args[@]}"
store="$FAKE_STATE/secrets"
case "$1 $2" in
  "get secret")
    [[ -z "${FAKE_GET_FAILS:-}" ]] || { echo 'Error from server (Forbidden)' >&2; exit 1; }
    name="$3"; key=""
    for arg in "$@"; do
      case "$arg" in jsonpath=*) key="${arg#jsonpath=\{.data.}"; key="${key%\}}" ;; esac
    done
    if [[ -f "$store/$name/$key" ]]; then base64 < "$store/$name/$key" | tr -d '\n'; fi
    ;;
  "create secret")
    name="$4"; shift 4
    printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\ndata:\n' "$name"
    for arg in "$@"; do
      case "$arg" in
        --from-file=*) spec="${arg#--from-file=}"
          printf '  %s: %s\n' "${spec%%=*}" "$(base64 < "${spec#*=}" | tr -d '\n')" ;;
      esac
    done
    ;;
  "apply --filename")
    [[ -z "${FAKE_APPLY_FAILS:-}" ]] || exit 1
    name="$(sed -n 's/^  name: //p' "$3")"
    mkdir -p "$store/$name"
    sed -n '/^data:/,$p' "$3" | sed -n 's/^  \([A-Z0-9_]*\): \(.*\)$/\1 \2/p' | \
      while read -r key value; do printf '%s' "$value" | base64 --decode > "$store/$name/$key"; done
    echo applied >> "$FAKE_STATE/apply.log"
    ;;
  "get deployment")
    cat "$FAKE_STATE/deployments" 2>/dev/null || true
    ;;
  "get persistentvolumeclaim")
    [[ -z "${FAKE_PVC_GET_FAILS:-}" ]] || exit 1
    if [[ -e "$FAKE_STATE/claims/$3" ]]; then echo "persistentvolumeclaim/$3"; fi
    ;;
  "get pods")
    [[ -z "${FAKE_PODS_GET_FAILS:-}" ]] || exit 1
    cat "$FAKE_STATE/mounted-claims" 2>/dev/null || true
    ;;
  "delete persistentvolumeclaim")
    [[ -z "${FAKE_PVC_DELETE_FAILS:-}" ]] || exit 1
    rm -f "$FAKE_STATE/claims/$3"; echo "$3" >> "$FAKE_STATE/delete.log"
    ;;
  "rollout restart") echo "$3" >> "$FAKE_STATE/restart.log" ;;
  "rollout status") ;;
  *) echo "fake kubectl: unexpected call: $*" >&2; exit 97 ;;
esac
FAKE
chmod +x "$scratch/bin/kubectl"

# --- helpers ---------------------------------------------------------------------------------------
new_state() {
  current="$scratch/state-$1"
  mkdir -p "$current/secrets"
  : > "$current/argv.log"
}

# run_hook [VAR=value ...]: runs the hook in a clean environment; sets status, captures output.
run_hook() {
  status=0
  env -i PATH="$scratch/bin:$PATH" HOME="$scratch" TMPDIR="$scratch" FAKE_STATE="$current" \
    KT_DEPLOY_RELEASE=dwhcodereview KT_DEPLOY_NAMESPACE=dwhcodereview \
    KT_DEPLOY_CHART_DIR="$root/helm/dwhcodereview" KT_DEPLOY_IMAGE_TAG="${tag:-$(printf 'a%.0s' {1..40})}" \
    KT_DEPLOY_DATABASE_ENABLED=true "$@" \
    bash "$hook" > "$current/stdout" 2> "$current/stderr" || status=$?
}

stored() { cat "$current/secrets/dwhcodereview-runtime/$1" 2>/dev/null; }
has_key() { [[ -f "$current/secrets/dwhcodereview-runtime/$1" ]]; }

check() {
  local description="$1"; shift
  if "$@"; then
    echo "ok   $description"
  else
    echo "FAIL $description"
    failures=$((failures + 1))
  fi
}

# No value may reach stdout, stderr or any kubectl argument.
never_printed() {
  local value="$1"
  ! grep -qF -- "$value" "$current/stdout" "$current/stderr" "$current/argv.log"
}

valid_p256_key() {
  local text
  text="$(openssl pkey -in "$current/secrets/dwhcodereview-runtime/DWHCODEREVIEW_JWT_PRIVATE_KEY" \
    -pubout 2>/dev/null | openssl pkey -pubin -noout -text 2>/dev/null)" || return 1
  [[ "$text" == *prime256v1* || "$text" == *P-256* ]]
}

user='dwh_okuyucu_test'
password='Parola;=}{ with spaces 42'
llm_key='test-llm-key-not-real'
# Not a usable password of any environment; shell metacharacters, spaces and non-ASCII letters prove
# the value reaches the Secret byte for byte.
admin_password='test-başlangıç $(yok) `x` "q" parolası 42'

# --- cases -----------------------------------------------------------------------------------------
new_state first-run
run_hook
check 'first run without pipeline secrets succeeds' test "$status" -eq 0
check 'first run generates a P-256 signing key' valid_p256_key
check 'first run writes no SQL Server keys' eval '! has_key DWHCODEREVIEW_MSSQL_USER && ! has_key DWHCODEREVIEW_MSSQL_PASSWORD'
check 'first run writes no LLM key' eval '! has_key DWHCODEREVIEW_LLM_API_KEY'
check 'first run writes no super admin start-up password' eval '! has_key DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD'
check 'an absent DWHCODEREVIEW_ADMIN_PASSWORD is reported by key name' \
  grep -q 'DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD not provided; DWHCODEREVIEW_ADMIN_PASSWORD is absent' "$current/stdout"
check 'first run reports the generated key by name' grep -q 'DWHCODEREVIEW_JWT_PRIVATE_KEY generated' "$current/stdout"
check 'no private key material is printed' never_printed 'PRIVATE KEY'
check 'no private key material reaches kubectl arguments' never_printed "$(sed -n 2p "$current/secrets/dwhcodereview-runtime/DWHCODEREVIEW_JWT_PRIVATE_KEY")"
first_key="$(stored DWHCODEREVIEW_JWT_PRIVATE_KEY)"

: > "$current/apply.log"
run_hook
check 'second run succeeds' test "$status" -eq 0
check 'second run reuses the signing key from the cluster' test "$(stored DWHCODEREVIEW_JWT_PRIVATE_KEY)" = "$first_key"
check 'second run leaves the Secret unchanged' grep -q 'unchanged' "$current/stdout"
check 'second run writes nothing' test ! -s "$current/apply.log"

run_hook MSSQL_USER="$user" MSSQL_PASSWORD="$password" LLM_API_KEY="$llm_key"
check 'pipeline SQL Server credentials are accepted' test "$status" -eq 0
check 'MSSQL_USER maps to DWHCODEREVIEW_MSSQL_USER' test "$(stored DWHCODEREVIEW_MSSQL_USER)" = "$user"
check 'MSSQL_PASSWORD maps to DWHCODEREVIEW_MSSQL_PASSWORD' test "$(stored DWHCODEREVIEW_MSSQL_PASSWORD)" = "$password"
check 'LLM_API_KEY maps to DWHCODEREVIEW_LLM_API_KEY' test "$(stored DWHCODEREVIEW_LLM_API_KEY)" = "$llm_key"
check 'the signing key survives a credential change' test "$(stored DWHCODEREVIEW_JWT_PRIVATE_KEY)" = "$first_key"
check 'the SQL Server user is never printed or passed as an argument' never_printed "$user"
check 'the SQL Server password is never printed or passed as an argument' never_printed "$password"
check 'the LLM key is never printed or passed as an argument' never_printed "$llm_key"

run_hook
check 'a later run without pipeline credentials succeeds' test "$status" -eq 0
check 'absent MSSQL_USER keeps the cluster value' test "$(stored DWHCODEREVIEW_MSSQL_USER)" = "$user"
check 'absent MSSQL_PASSWORD keeps the cluster value' test "$(stored DWHCODEREVIEW_MSSQL_PASSWORD)" = "$password"

new_state admin-password
: > "$current/apply.log"
run_hook DWHCODEREVIEW_ADMIN_PASSWORD="$admin_password"
check 'a pipeline super admin start-up password is accepted' test "$status" -eq 0
check 'DWHCODEREVIEW_ADMIN_PASSWORD maps to DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD' \
  test "$(stored DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD)" = "$admin_password"
check 'the start-up password reaches kubectl only as a file' \
  grep -q -- '--from-file=DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD=/' "$current/argv.log"
check 'the start-up password is never printed or passed as an argument' never_printed "$admin_password"
check 'the start-up password is reported by key name only' \
  grep -q 'DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD set from DWHCODEREVIEW_ADMIN_PASSWORD' "$current/stdout"
: > "$current/apply.log"
run_hook
check 'a later run without DWHCODEREVIEW_ADMIN_PASSWORD succeeds' test "$status" -eq 0
check 'absent DWHCODEREVIEW_ADMIN_PASSWORD keeps the cluster value' \
  test "$(stored DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD)" = "$admin_password"
check 'a kept start-up password rewrites nothing' test ! -s "$current/apply.log"
check 'a kept start-up password is never printed' never_printed "$admin_password"

new_state unresolved-macro
run_hook MSSQL_USER='$(MSSQL_USER)' MSSQL_PASSWORD='$(MSSQL_PASSWORD)' \
  DWHCODEREVIEW_ADMIN_PASSWORD='$(DWHCODEREVIEW_ADMIN_PASSWORD)'
check 'unresolved Azure macros do not stop the deployment' test "$status" -eq 0
check 'an unresolved macro is never stored' eval '! has_key DWHCODEREVIEW_MSSQL_USER && ! has_key DWHCODEREVIEW_MSSQL_PASSWORD'
check 'an unresolved start-up password macro is never stored' \
  eval '! has_key DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD'
check 'an unresolved macro is reported by name' grep -q 'MSSQL_USER is an unresolved Azure variable' "$current/stdout"

new_state read-failure
: > "$current/apply.log"
run_hook FAKE_GET_FAILS=1 MSSQL_USER="$user"
check 'an unreadable Secret stops the hook' test "$status" -ne 0
check 'an unreadable Secret is never overwritten' test ! -s "$current/apply.log"

new_state write-failure
run_hook FAKE_APPLY_FAILS=1 MSSQL_PASSWORD="$password"
check 'a failed write stops the hook' test "$status" -ne 0
check 'a failed write does not print the value' never_printed "$password"

new_state invalid-key
: > "$current/apply.log"
run_hook JWT_PRIVATE_KEY='not-a-pem-key-value'
check 'an invalid JWT_PRIVATE_KEY stops the hook' test "$status" -ne 0
check 'an invalid JWT_PRIVATE_KEY is never written' test ! -s "$current/apply.log"
check 'an invalid JWT_PRIVATE_KEY is not echoed' never_printed 'not-a-pem-key-value'

new_state pipeline-key
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$scratch/pipeline.pem" 2>/dev/null
run_hook JWT_PRIVATE_KEY="$(cat "$scratch/pipeline.pem")"
check 'a pipeline JWT_PRIVATE_KEY is used' test "$(stored DWHCODEREVIEW_JWT_PRIVATE_KEY)" = "$(cat "$scratch/pipeline.pem")"

new_state control-character
run_hook MSSQL_USER="$(printf 'user\tname')"
check 'a control character in MSSQL_USER stops the hook' test "$status" -ne 0

new_state restart-same-tag
tag="$(printf 'b%.0s' {1..40})"
printf 'dwhcodereview-dwhcodereview-backend-f5594230b40d\texample.test/dwhcodereview-backend:%s\n' "$tag" \
  > "$current/deployments"
run_hook
check 'a changed Secret restarts a backend that keeps its image tag' \
  grep -qx 'deployment/dwhcodereview-dwhcodereview-backend-f5594230b40d' "$current/restart.log"
: > "$current/restart.log"
run_hook
check 'an unchanged Secret restarts nothing' test ! -s "$current/restart.log"

new_state restart-new-tag
printf 'dwhcodereview-dwhcodereview-backend-f5594230b40d\texample.test/dwhcodereview-backend:%s\n' \
  "$(printf 'c%.0s' {1..40})" > "$current/deployments"
run_hook
check 'a backend moving to a new image tag is left to Helm' test ! -e "$current/restart.log"
unset tag

legacy=dwhcodereview-backend-data
with_legacy_claim() { mkdir -p "$current/claims"; : > "$current/claims/$legacy"; }

new_state legacy-unmounted
with_legacy_claim
run_hook
check 'an unmounted legacy rules disk is deleted' grep -qx "$legacy" "$current/delete.log"
check 'the legacy disk deletion is reported' grep -q "\[LEGACY\] $legacy deleted" "$current/stdout"
: > "$current/delete.log"
run_hook
check 'a deleted legacy disk is not deleted again' test ! -s "$current/delete.log"
check 'a missing legacy disk leaves the run green' test "$status" -eq 0

new_state legacy-mounted
with_legacy_claim
printf 'data-dwhcodereview-database-0\n%s\n' "$legacy" > "$current/mounted-claims"
run_hook
check 'a mounted legacy disk is kept' test -e "$current/claims/$legacy"
check 'a mounted legacy disk is never deleted' test ! -e "$current/delete.log"

new_state legacy-pods-unreadable
with_legacy_claim
run_hook FAKE_PODS_GET_FAILS=1
check 'a legacy disk with unknown use is kept' test -e "$current/claims/$legacy"
check 'unknown disk use does not stop the deployment' test "$status" -eq 0

new_state legacy-unreadable
with_legacy_claim
run_hook FAKE_PVC_GET_FAILS=1
check 'an unreadable legacy disk is kept' test -e "$current/claims/$legacy"
check 'an unreadable legacy disk does not stop the deployment' test "$status" -eq 0

new_state legacy-delete-denied
with_legacy_claim
run_hook FAKE_PVC_DELETE_FAILS=1
check 'a refused legacy disk deletion does not stop the deployment' test "$status" -eq 0
check 'a refused legacy disk deletion is reported' grep -q "$legacy could not be deleted" "$current/stdout"

check 'the hook writes the Secret values-project.yaml names' \
  grep -qx '  existingSecret: dwhcodereview-runtime' "$layer"
check 'the hook parses' bash -n "$hook"

if [[ "$failures" -ne 0 ]]; then
  echo "deploy-hooks: $failures check(s) failed" >&2
  exit 1
fi
echo 'deploy-hooks: all checks passed'
