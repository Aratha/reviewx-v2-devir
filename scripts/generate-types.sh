#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
contract="$root/specs/openapi/dwhcodereview-api.yaml"
output="$root/app/frontend/src/types/api.d.ts"
temporary="$output.tmp.$$"
trap 'rm -f "$temporary"' EXIT

"$root/scripts/stack.sh" exec -T frontend \
  sh -lc './node_modules/.bin/openapi-typescript /dev/stdin' \
  < "$contract" > "$temporary"

if [ "${1:-}" = "--check" ]; then
  diff -u "$output" "$temporary"
else
  mv "$temporary" "$output"
fi
