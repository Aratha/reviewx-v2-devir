#!/usr/bin/env sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
default_root="$(CDPATH= cd -- "$script_dir/.." && pwd)"
root="${KT_SECURITY_ROOT:-$default_root}"
ledger="${KT_DEPENDENCY_ADMISSION_LEDGER:-$root/dependency-admission.json}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "zorunlu çevrimdışı güvenlik aracı kullanılamıyor: $1" >&2
    exit 2
  }
}

require_command python3
require_command gitleaks
require_command semgrep
require_command trivy
require_command sha256sum

: "${INTERNAL_SCANNER_MATERIAL_DIR:?INTERNAL_SCANNER_MATERIAL_DIR değişkenini kabul edilmiş tarayıcı anlık görüntüsüne ayarlayın}"
: "${INTERNAL_SCANNER_SHA256SUMS:?INTERNAL_SCANNER_SHA256SUMS değişkenini anlık görüntünün SHA256SUMS dosyasına ayarlayın}"
: "${INTERNAL_SCANNER_SHA256SUMS_SHA256:?bant dışı banka kabul özetini ayarlayın}"
: "${INTERNAL_SCANNER_ADMITTED_ON:?banka kabul tarihini YYYY-MM-DD biçiminde ayarlayın}"
: "${INTERNAL_SEMGREP_RULESET:?INTERNAL_SEMGREP_RULESET değişkenini kabul edilmiş çevrimdışı kural kümesine ayarlayın}"
: "${TRIVY_CACHE_DIR:?TRIVY_CACHE_DIR değişkenini kabul edilmiş çevrimdışı Trivy önbelleğine ayarlayın}"
max_age_days="${INTERNAL_SCANNER_MAX_AGE_DAYS:-7}"

scanner_root="$(CDPATH= cd -- "$INTERNAL_SCANNER_MATERIAL_DIR" && pwd -P)"
sums="$(CDPATH= cd -- "$(dirname -- "$INTERNAL_SCANNER_SHA256SUMS")" && pwd -P)/$(basename -- "$INTERNAL_SCANNER_SHA256SUMS")"
ruleset="$(CDPATH= cd -- "$(dirname -- "$INTERNAL_SEMGREP_RULESET")" && pwd -P)/$(basename -- "$INTERNAL_SEMGREP_RULESET")"
trivy_cache="$(CDPATH= cd -- "$TRIVY_CACHE_DIR" && pwd -P)"
case "$sums" in "$scanner_root"/*) ;; *) echo "tarayıcı sağlama toplamı manifesti kabul edilmiş anlık görüntünün dışına çıkıyor" >&2; exit 2 ;; esac
case "$ruleset" in "$scanner_root"/*) ;; *) echo "Semgrep kural kümesi kabul edilmiş anlık görüntünün dışına çıkıyor" >&2; exit 2 ;; esac
case "$trivy_cache" in "$scanner_root"/*|"$scanner_root") ;; *) echo "Trivy önbelleği kabul edilmiş anlık görüntünün dışına çıkıyor" >&2; exit 2 ;; esac
[ -f "$sums" ] && [ ! -L "$sums" ] || { echo "tarayıcı sağlama toplamı manifesti normal bir dosya olmalıdır" >&2; exit 2; }
[ -f "$ruleset" ] && [ ! -L "$ruleset" ] || { echo "Semgrep kural kümesi normal bir dosya olmalıdır" >&2; exit 2; }
[ -d "$trivy_cache" ] && [ ! -L "$trivy_cache" ] || { echo "Trivy önbelleği bir dizin olmalıdır" >&2; exit 2; }
if find "$scanner_root" -type l -print -quit | grep -q .; then
  echo "tarayıcı anlık görüntüsü sembolik bağlantı içermemelidir" >&2
  exit 2
fi

sums_relative="${sums#"$scanner_root"/}"
awk '
  NF != 2 || length($1) != 64 || $1 !~ /^[0-9a-f]+$/ ||
    $2 ~ /^\// || $2 ~ /(^|\/)\.\.(\/|$)/ { exit 1 }
  END { if (NR == 0) exit 1 }
' "$sums" || { echo "tarayıcı SHA256SUMS dosyası güvensiz bir girdi içeriyor" >&2; exit 2; }
manifest_paths="$(awk '{ path=$2; sub(/^\.\//, "", path); print path }' "$sums" | LC_ALL=C sort)"
actual_paths="$({
  CDPATH= cd -- "$scanner_root"
  find . -type f ! -path "./$sums_relative" -print \
    | sed 's#^\./##' \
    | LC_ALL=C sort
})"
if [ "$actual_paths" != "$manifest_paths" ]; then
  echo "tarayıcı anlık görüntüsünde mühürlenmemiş veya eksik dosyalar var" >&2
  exit 1
fi

if ! printf '%s\n' "$INTERNAL_SCANNER_SHA256SUMS_SHA256" | grep -Eq '^[0-9a-f]{64}$'; then
  echo "tarayıcı kabul özeti 64 küçük harfli onaltılık karakterden oluşmalıdır" >&2
  exit 2
fi
actual_sums_sha256="$(sha256sum "$sums" | awk '{print $1}')"
if [ "$actual_sums_sha256" != "$INTERNAL_SCANNER_SHA256SUMS_SHA256" ]; then
  echo "tarayıcı sağlama toplamı manifesti bant dışı banka kabul özetiyle eşleşmiyor" >&2
  exit 1
fi
python3 - "$INTERNAL_SCANNER_ADMITTED_ON" "$max_age_days" <<'PY'
from datetime import date
import sys

try:
    admitted = date.fromisoformat(sys.argv[1])
    maximum = int(sys.argv[2])
except (ValueError, IndexError) as exc:
    raise SystemExit(f"tarayıcı kabul yaşı kanıtı geçersiz: {exc}")
age = (date.today() - admitted).days
if maximum < 0 or age < 0 or age > maximum:
    raise SystemExit(
        f"tarayıcı anlık görüntüsünün {age} günlük yaşı kabul edilen {maximum} günlük üst sınırın dışında"
    )
PY
(cd "$scanner_root" && sha256sum --check "$sums_relative")
python3 "$script_dir/check-dependency-admission.py" --root "$root" --ledger "$ledger"

echo "tarayıcı sürümleri: $(gitleaks version); $(semgrep --version); $(trivy --version | head -n 1)"
gitleaks dir --config "$root/.gitleaks.toml" --redact --exit-code 1 "$root"
SEMGREP_ENABLE_VERSION_CHECK=0 SEMGREP_SEND_METRICS=off \
  semgrep scan --config "$ruleset" --error "$root"
application_chart="$root/helm/dwhcodereview"
if [ -f "$application_chart/Chart.yaml" ]; then
  chart_scan_values="$(mktemp)"
  trap 'rm -f "$chart_scan_values"' 0 HUP INT TERM
  {
    printf '%s\n' \
      'backend:' \
      '  image:' \
      '    repository: registry.test.invalid/generated/backend' \
      '    digest: sha256:1111111111111111111111111111111111111111111111111111111111111111' \
      '  existingSecret: synthetic-runtime' \
      '  networkPolicy:' \
      '    ingress:' \
      '      - from:' \
      '          - podSelector: {matchLabels: {app.kubernetes.io/name: synthetic-gateway}}' \
      '        ports: [{protocol: TCP, port: 8000}]' \
      '    egress:' \
      '      - to:' \
      '          - podSelector: {matchLabels: {app.kubernetes.io/name: synthetic-dns}}' \
      '        ports: [{protocol: UDP, port: 53}, {protocol: TCP, port: 53}]' \
      '      - to:' \
      '          - podSelector: {matchLabels: {app.kubernetes.io/name: synthetic-database}}' \
      '        ports: [{protocol: TCP, port: 5432}]' \
      'frontend:' \
      '  image:' \
      '    repository: registry.test.invalid/generated/frontend' \
      '    digest: sha256:2222222222222222222222222222222222222222222222222222222222222222' \
      '  ingress:' \
      '    className: synthetic-gateway' \
      '    host: generated.test.invalid' \
      '    tlsSecretName: synthetic-tls' \
      '  networkPolicy:' \
      '    ingress:' \
      '      - from:' \
      '          - podSelector: {matchLabels: {app.kubernetes.io/name: synthetic-gateway}}' \
      '        ports: [{protocol: TCP, port: 8080}]' \
      '    egress: []'
  } > "$chart_scan_values"
  TRIVY_NO_PROGRESS=true TRIVY_SKIP_DB_UPDATE=true TRIVY_SKIP_JAVA_DB_UPDATE=true \
    trivy fs --offline-scan --include-dev-deps --scanners vuln,misconfig,secret \
      --skip-dirs "$application_chart" --exit-code 1 --severity HIGH,CRITICAL "$root"
  TRIVY_NO_PROGRESS=true \
    trivy config --skip-check-update --skip-version-check --helm-kube-version 1.33.0 \
      --helm-values "$chart_scan_values" \
      --exit-code 1 --severity HIGH,CRITICAL "$application_chart"
  rm -f "$chart_scan_values"
  trap - 0 HUP INT TERM
else
  TRIVY_NO_PROGRESS=true TRIVY_SKIP_DB_UPDATE=true TRIVY_SKIP_JAVA_DB_UPDATE=true \
    trivy fs --offline-scan --include-dev-deps --scanners vuln,misconfig,secret \
      --exit-code 1 --severity HIGH,CRITICAL "$root"
fi
