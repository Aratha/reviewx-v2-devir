#!/usr/bin/env sh
set -eu

# Print one disposable local development secret and create every missing one on first use:
#   jwt-private-key    ES256 (P-256) PEM signing key for the backend
#   postgres-password  password of the local PostgreSQL `app` role
#   redis-password     password of the local Redis server
# The secrets live only in the Git-ignored app/infra/.data/ directory with owner-only permissions
# and serve only the local Compose stack and host development runs. Deployed environments receive
# their secrets in the cluster: the project's helm deploy hook prepares backend.existingSecret and
# deploy.sh generates the database Secrets; nothing here reaches a cluster.
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
data="$root/app/infra/.data"

case "${1:-}" in
  jwt-private-key) secret="$data/dev-jwt-signing-key.pem" ;;
  postgres-password) secret="$data/postgres-password" ;;
  redis-password) secret="$data/redis-password" ;;
  *)
    echo "usage: dev-secrets.sh jwt-private-key|postgres-password|redis-password" >&2
    exit 2
    ;;
esac

if [ ! -s "$data/dev-jwt-signing-key.pem" ] || [ ! -s "$data/postgres-password" ] ||
  [ ! -s "$data/redis-password" ]; then
  if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required to create the local development secrets" >&2
    exit 1
  fi
  (
    umask 077
    mkdir -p "$data"
    if [ ! -s "$data/dev-jwt-signing-key.pem" ]; then
      openssl ecparam -name prime256v1 -genkey -noout -out "$data/dev-jwt-signing-key.pem.tmp"
      mv "$data/dev-jwt-signing-key.pem.tmp" "$data/dev-jwt-signing-key.pem"
    fi
    # Hex keeps the passwords safe inside the Compose database URL and the Redis configuration.
    for name in postgres-password redis-password; do
      if [ ! -s "$data/$name" ]; then
        openssl rand -hex 32 >"$data/$name.tmp"
        mv "$data/$name.tmp" "$data/$name"
      fi
    done
  )
fi
cat "$secret"
