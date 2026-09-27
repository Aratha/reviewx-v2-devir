#!/usr/bin/env sh
set -eu
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
scaffold_bin="$(command -v kt-iskelet || true)"
if [ -z "$scaffold_bin" ]; then
  echo "chart politikası sabitlenmiş kt-iskelet CLI'ının PATH üzerinde olmasını gerektirir" >&2
  exit 2
fi
python_bin="$(sed -n '1s/^#!//p' "$scaffold_bin")"
if [ ! -x "$python_bin" ]; then
  echo "sabitlenmiş kt-iskelet Python yorumlayıcısı çözümlenemedi" >&2
  exit 2
fi
exec "$python_bin" "$root/scripts/render_charts.py" "$@"
