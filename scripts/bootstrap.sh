#!/usr/bin/env sh
set -eu

required="0.4.0"
if command -v kt-iskelet >/dev/null 2>&1; then
  actual="$(kt-iskelet --surum)"
  if [ "$actual" != "$required" ]; then
    echo "kt-iskelet sürüm uyuşmazlığı: beklenen $required, bulunan $actual" >&2
    exit 1
  fi
  generator="yerel kt-iskelet $actual"
else
  generator="global Streamable HTTP MCP (proje kt-iskelet $required bekliyor)"
fi

python3 scripts/check-governance-drift.py >/dev/null
sh scripts/git-gate.sh
python3 scripts/check-dependency-admission.py >/dev/null
docker info >/dev/null
echo "bootstrap ok: $generator, Docker reachable, governance and dependency admission current"
