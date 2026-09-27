#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
answers="$root/.kt-scaffold/answers.yml"
scope="${1:-all}"
browser="${2:-}"
profile="$(sed -n 's/^backend_profile: //p' "$answers")"
schema_profile="$(sed -n 's/^backend_profile: //p' "$root/schema/profile.yml")"
env_prefix="$(sed -n 's/^env_prefix: //p' "$answers")"
product_slug="$(sed -n 's/^product_slug: //p' "$answers")"
database_env="${env_prefix}DATABASE_URL"
postgres_integration="0"
test_database=""
test_database_active="false"

run_step() {
  step_name="$1"
  shift
  echo "KT_GATE_STEP name=$step_name status=started"
  if "$@"; then
    echo "KT_GATE_STEP name=$step_name status=passed"
  else
    step_status=$?
    echo "KT_GATE_STEP name=$step_name status=failed exit_code=$step_status"
    return "$step_status"
  fi
}

validate_configuration() {
  case "$scope" in
    backend|frontend|all) ;;
    *) echo "scope must be backend, frontend or all" >&2; return 2 ;;
  esac
  case "$browser" in
    ""|--include-browser) ;;
    *) echo "second argument must be --include-browser" >&2; return 2 ;;
  esac
  if [ "$profile" != "python-fastapi" ]; then
    echo "unsupported backend profile: $profile" >&2
    return 2
  fi
  if [ "$profile" != "$schema_profile" ]; then
    echo "answers and schema profile disagree" >&2
    return 2
  fi
  if ! printf '%s\n' "$env_prefix" | grep -Eq '^[A-Z][A-Z0-9_]*_$'; then
    echo "unsafe environment prefix in answers" >&2
    return 2
  fi
  if ! printf '%s\n' "$product_slug" | grep -Eq '^[a-z][a-z0-9-]*$'; then
    echo "unsafe product slug in answers" >&2
    return 2
  fi
}

backend_shell() {
  backend_command="$1"
  if [ "$test_database_active" = "true" ]; then
    # The backend keeps its configured credentials; only the database name is replaced, so the
    # local password never appears on this script's command line.
    "$root/scripts/stack.sh" exec -T \
      -e "KT_SCAFFOLD_TEST_DATABASE=$test_database" \
      -e "RUN_POSTGRES_INTEGRATION=$postgres_integration" \
      backend sh -lc "export $database_env=\"\${$database_env%/*}/\$KT_SCAFFOLD_TEST_DATABASE\"; $backend_command"
  else
    "$root/scripts/stack.sh" exec -T backend sh -lc "$backend_command"
  fi
}

frontend_shell() {
  "$root/scripts/stack.sh" exec -T frontend sh -lc "$1"
}

backend_static() {
  backend_shell 'ruff check app tests && black --check app tests && isort --check-only app tests && mypy app'
}

backend_tests() {
  backend_shell "rm -f /tmp/kt-gate-pytest.xml; pytest -q --junitxml=/tmp/kt-gate-pytest.xml; test_status=\$?; python -c 'import xml.etree.ElementTree as E; r=E.parse(\"/tmp/kt-gate-pytest.xml\").getroot(); suites=[r] if r.tag==\"testsuite\" else list(r.iter(\"testsuite\")); total=sum(int(s.attrib.get(\"tests\", 0)) for s in suites); failed=sum(int(s.attrib.get(\"failures\", 0))+int(s.attrib.get(\"errors\", 0)) for s in suites); skipped=sum(int(s.attrib.get(\"skipped\", 0)) for s in suites); print(\"KT_GATE_TESTS name=backend-tests runner=pytest total=%d passed=%d failed=%d skipped=%d\" % (total, total-failed-skipped, failed, skipped))'; exit \$test_status"
}

database_validate() {
  if [ "$test_database_active" = "true" ]; then
    KT_SCAFFOLD_TEST_DATABASE="$test_database" "$root/scripts/db.sh" validate
  else
    "$root/scripts/db.sh" validate
  fi
}

database_apply() {
  KT_SCAFFOLD_TEST_DATABASE="$test_database" "$root/scripts/db.sh" apply
}

openapi_contract() {
  "$root/scripts/export-openapi.sh" --check
}

backend_gate() {
  run_step backend-static backend_static
  run_step backend-tests backend_tests
  run_step database-validate database_validate
  run_step openapi-contract openapi_contract
}

frontend_static() {
  frontend_shell 'npm run lint && npm run build'
}

frontend_tests() {
  frontend_shell "rm -f /tmp/kt-gate-vitest.json; npm test -- --reporter=default --reporter=json --outputFile.json=/tmp/kt-gate-vitest.json; test_status=\$?; node -e 'const r=JSON.parse(require(\"node:fs\").readFileSync(\"/tmp/kt-gate-vitest.json\",\"utf8\")); console.log(\"KT_GATE_TESTS name=frontend-tests runner=vitest total=\"+r.numTotalTests+\" passed=\"+r.numPassedTests+\" failed=\"+r.numFailedTests+\" skipped=\"+r.numPendingTests)'; exit \$test_status"
}

frontend_types_contract() {
  "$root/scripts/generate-types.sh" --check
}

frontend_gate() {
  run_step frontend-static frontend_static
  run_step frontend-tests frontend_tests
  run_step frontend-types-contract frontend_types_contract
}

postgres_sql() {
  "$root/scripts/stack.sh" exec -T postgres \
    psql -v ON_ERROR_STOP=1 --username app --dbname postgres --command "$1"
}

create_test_database() {
  product_package="$(printf '%s' "$product_slug" | tr '-' '_')"
  short_package="$(printf '%s' "$product_package" | cut -c1-28)"
  profile_code="python"
  test_database="${short_package}_${profile_code}_gate_$$_test"
  if ! printf '%s\n' "$test_database" | grep -Eq '^[a-z0-9_]+_test$'; then
    echo "refusing unsafe disposable database name" >&2
    return 2
  fi
  # run_step calls this function as an `if` condition, where `set -e` does not apply; every
  # command that can fail must return its own status.
  postgres_sql "DROP DATABASE IF EXISTS \"$test_database\" WITH (FORCE);" || return
  postgres_sql "CREATE DATABASE \"$test_database\";" || return
  test_database_active="true"
}

drop_test_database() {
  postgres_sql "DROP DATABASE IF EXISTS \"$test_database\" WITH (FORCE);"
}

drop_test_database_step() {
  echo "KT_GATE_STEP name=database-test-drop status=started"
  if drop_test_database; then
    test_database_active="false"
    echo "KT_GATE_STEP name=database-test-drop status=passed"
  else
    drop_status=$?
    echo "KT_GATE_STEP name=database-test-drop status=failed exit_code=$drop_status"
    return "$drop_status"
  fi
}

cleanup_on_exit() {
  cleanup_status=$?
  trap - EXIT HUP INT TERM
  if [ "$test_database_active" = "true" ]; then
    if ! drop_test_database_step && [ "$cleanup_status" -eq 0 ]; then
      cleanup_status=1
    fi
  fi
  exit "$cleanup_status"
}

trap cleanup_on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

run_step configuration validate_configuration
run_step dependency-admission python3 "$root/scripts/check-dependency-admission.py"
if [ "$scope" != "frontend" ]; then
  run_step configuration-sync python3 "$root/scripts/check-config-sync.py"
fi

case "$scope" in
  backend)
    echo "KT_GATE_SCOPE scope=backend postgres_integration=skipped database_mode=configured-read-only"
    backend_gate
    ;;
  frontend)
    echo "KT_GATE_SCOPE scope=frontend postgres_integration=skipped database_mode=none"
    frontend_gate
    ;;
  all)
    echo "KT_GATE_SCOPE scope=all postgres_integration=required database_mode=disposable-test"
    run_step database-test-create create_test_database
    postgres_integration="1"
    run_step database-migrations-apply database_apply
    backend_gate
    frontend_gate
    run_step governance-drift "$root/scripts/render-clients.sh" --check
    run_step charts-render "$root/scripts/render-charts.sh"
    drop_test_database_step
    ;;
esac

browser_readiness() {
  base_url="${APP_E2E_BASE:-http://localhost:8080}"
  api_prefix="$(sed -n 's/^api_prefix: //p' "$answers")"
  attempt=0
  while [ "$attempt" -lt 60 ]; do
    if curl -fsS "$base_url$api_prefix/readiness" >/dev/null 2>&1; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  echo "backend did not become ready for browser verification" >&2
  return 1
}

browser_scenarios() {
  cd "$root/e2e" || return
  scenario_count=0
  for runner in ./*/run-all.mjs; do
    [ -f "$runner" ] || continue
    if node "$runner"; then
      scenario_count=$((scenario_count + 1))
    else
      scenario_status=$?
      echo "KT_GATE_TESTS name=browser-scenarios runner=playwright total=$((scenario_count + 1)) passed=$scenario_count failed=1 skipped=0"
      return "$scenario_status"
    fi
  done
  if [ "$scenario_count" -eq 0 ]; then
    echo "no browser suite runners were found" >&2
    return 2
  fi
  echo "KT_GATE_TESTS name=browser-scenarios runner=playwright total=$scenario_count passed=$scenario_count failed=0 skipped=0"
}

if [ "$browser" = "--include-browser" ]; then
  run_step browser-readiness browser_readiness
  run_step browser-scenarios browser_scenarios
fi

echo "quality gate passed: $scope ($profile)"
