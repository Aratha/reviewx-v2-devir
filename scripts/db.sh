#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
answers="$root/.kt-scaffold/answers.yml"
profile="$(sed -n 's/^backend_profile: //p' "$answers")"
schema_profile="$(sed -n 's/^backend_profile: //p' "$root/schema/profile.yml")"
env_prefix="$(sed -n 's/^env_prefix: //p' "$answers")"
database_env="${env_prefix}DATABASE_URL"
test_database="${KT_SCAFFOLD_TEST_DATABASE:-}"
action="${1:-status}"
name="${2:-change}"

if [ "$profile" != "$schema_profile" ]; then
  echo "answers and schema profile disagree" >&2
  exit 2
fi
if ! printf '%s\n' "$env_prefix" | grep -Eq '^[A-Z][A-Z0-9_]*_$'; then
  echo "unsafe environment prefix in answers" >&2
  exit 2
fi
if [ -n "$test_database" ] && ! printf '%s\n' "$test_database" | grep -Eq '^[a-z0-9_]+_test$'; then
  echo "KT_SCAFFOLD_TEST_DATABASE must name a disposable database ending in _test" >&2
  exit 2
fi

stack_backend() {
  if [ -n "$test_database" ]; then
    # The backend keeps its configured credentials; only the database name is replaced, so the
    # local password never appears on this script's command line.
    "$root/scripts/stack.sh" exec -T \
      -e "KT_SCAFFOLD_TEST_DATABASE=$test_database" \
      backend sh -c "export $database_env=\"\${$database_env%/*}/\$KT_SCAFFOLD_TEST_DATABASE\" && exec \"\$@\"" \
      db-test "$@"
  else
    "$root/scripts/stack.sh" exec -T backend "$@"
  fi
}

case "$action" in
  generate)
    stack_backend alembic revision --autogenerate -m "$name"
    ;;
  apply)
    stack_backend alembic upgrade head
    ;;
  status)
    stack_backend alembic current
    ;;
  validate)
    stack_backend sh -lc 'alembic check && alembic heads && alembic current --check-heads'
    ;;
  *)
    echo "unsupported database action: $action" >&2
    exit 2
    ;;
esac
