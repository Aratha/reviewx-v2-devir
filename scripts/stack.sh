#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
base="$root/app/infra/docker-compose.local.yml"
observability="$root/app/infra/docker-compose.observability.yml"
dotenv="$root/app/infra/.env"
. "$root/scripts/compose-project.sh"
project="$(compose_project_name "$root")" || exit 1

# Hand the disposable local secrets to Compose. A value already in the shell environment or in the
# developer's Git-ignored app/infra/.env takes precedence over the generated one.
provide() {
  eval "current=\${$1:-}"
  if [ -n "$current" ]; then
    return 0
  fi
  if [ -f "$dotenv" ] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?$1=" "$dotenv"; then
    return 0
  fi
  value="$(sh "$root/scripts/dev-secrets.sh" "$2")"
  export "$1=$value"
}
provide JWT_PRIVATE_KEY jwt-private-key
provide POSTGRES_PASSWORD postgres-password
provide REDIS_PASSWORD redis-password

if [ -f "$observability" ]; then
  set -- docker compose --project-directory "$root/app/infra" -p "$project" -f "$base" -f "$observability" "$@"
else
  set -- docker compose --project-directory "$root/app/infra" -p "$project" -f "$base" "$@"
fi
exec "$@"
