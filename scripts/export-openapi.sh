#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
output="$root/specs/openapi/dwhcodereview-api.yaml"
temporary="$root/specs/openapi/.kt-scaffold-openapi.$$"
container_output="/tmp/kt-scaffold-openapi.$$"
trap 'rm -f "$temporary"' EXIT

"$root/scripts/stack.sh" exec -T backend \
  sh -eu -c 'trap '\''rm -f "$1"'\'' EXIT; python -m app.scripts.export_openapi --output "$1" >/dev/null; cat "$1"' \
  sh "$container_output" > "$temporary"

if [ "${1:-}" = "--check" ]; then
  diff -u "$output" "$temporary"
else
  mv "$temporary" "$output"
fi
