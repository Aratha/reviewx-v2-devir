#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
mode="write"
case "${1:-}" in
  --check) exec python3 "$root/scripts/check-governance-drift.py" ;;
  --validate) exec python3 "$root/scripts/check-governance-drift.py" ;;
  "") ;;
  *) echo "usage: scripts/render-clients.sh [--check|--validate]" >&2; exit 2 ;;
esac
if ! command -v kt-iskelet >/dev/null 2>&1; then
  echo "yazma kipi yerel ajan uzlaştırması veya isteğe bağlı yerel CLI gerektirir" >&2
  exit 2
fi
public_mode="yaz"
[ "$mode" = "check" ] && public_mode="denetle"
exec kt-iskelet yansit --hedef-dizin "$root" --kip "$public_mode"
