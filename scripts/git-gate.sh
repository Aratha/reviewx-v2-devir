#!/usr/bin/env sh
# Commit öncesi yönetişim tutarlılığı kapısını bu Git deposunda etkinleştir.
# Mevcut core.hooksPath değerinin üzerine yazmaz; yalnız uyarır.
set -eu

gate=".kt-scaffold/hooks/git"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "uyarı: Git deposu değil; git init sonrasında scripts/git-gate.sh komutunu yeniden çalıştırın" >&2
  exit 0
fi
cd "$(git rev-parse --show-toplevel)"
current="$(git config --get core.hooksPath || true)"
if [ -z "$current" ]; then
  git config --local core.hooksPath "$gate"
  echo "git gate ok: core.hooksPath=$gate"
elif [ "$current" = "$gate" ]; then
  echo "git gate ok: core.hooksPath=$gate"
else
  echo "uyarı: core.hooksPath=$current; kt-scaffold Git kapısı etkinleştirilmedi. $gate/pre-commit kancasını mevcut kanca zincirinize ekleyin" >&2
fi
