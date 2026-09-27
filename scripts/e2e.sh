#!/usr/bin/env sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
e2e_root="$root/e2e"
suite="${1:-auth}"
mode="${KT_SCAFFOLD_E2E_MODE:-offline}"

fail() {
  echo "çevrimdışı E2E hatası: $*" >&2
  exit 2
}

case "$suite" in
  ""|[!a-z]*|*[!a-z0-9-]*)
    fail "paket küçük harfli bir kısa ad olmalıdır"
    ;;
esac
[ -f "$e2e_root/$suite/run-all.mjs" ] || fail "bilinmeyen tarayıcı paketi: $suite"

verify_browser() {
  browser_root="$1"
  [ -d "$browser_root" ] || fail "Playwright tarayıcı dizini eksik: $browser_root"
  browser_root="$(CDPATH= cd -- "$browser_root" && pwd -P)"
  chromium_path="$(PLAYWRIGHT_BROWSERS_PATH="$browser_root" node -e '
    const fs = require("node:fs");
    const {chromium} = require("@playwright/test");
    const executable = chromium.executablePath();
    fs.accessSync(executable, fs.constants.X_OK);
    process.stdout.write(executable);
  ')" || fail "onaylı Playwright ağacında bu platform için çalıştırılabilir Chromium yok"
  [ -x "$chromium_path" ] || fail "Chromium çalıştırılabilir değil: $chromium_path"
  chromium_path="$(CDPATH= cd -- "$(dirname -- "$chromium_path")" && pwd -P)/$(basename -- "$chromium_path")"
  case "$chromium_path" in
    "$browser_root"/*) ;;
    *) fail "Playwright, Chromium'u onaylı tarayıcı ağacının dışında çözümledi" ;;
  esac
  export PLAYWRIGHT_BROWSERS_PATH="$browser_root"
}

wait_for_readiness() {
  base_url="${APP_E2E_BASE:-http://localhost:8080}"
  base_url="${base_url%/}"
  [ -n "$base_url" ] || fail "APP_E2E_BASE boş olmamalıdır"
  api_prefix="$(sed -n 's/^api_prefix: //p' "$root/.kt-scaffold/answers.yml")"
  [ -n "$api_prefix" ] || fail "üretilen yanıtlarda api_prefix yok"
  readiness_url="$base_url$api_prefix/readiness"
  attempt=1
  while [ "$attempt" -le 60 ]; do
    if curl -fsS "$readiness_url" >/dev/null 2>&1; then
      return 0
    fi
    if [ "$attempt" -lt 60 ]; then
      sleep 1
    fi
    attempt=$((attempt + 1))
  done
  fail "arka uç tarayıcı doğrulaması için hazır duruma gelmedi: $readiness_url"
}

case "$mode" in
  offline)
    bundle_input="${KT_SCAFFOLD_OFFLINE_BUNDLE:-}"
    trusted_manifest_digest="${KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256:-}"
    [ -n "$bundle_input" ] || fail \
      "KT_SCAFFOLD_OFFLINE_BUNDLE kabul edilmiş, platformla eşleşen bir bundle paketini göstermelidir"
    printf '%s\n' "$trusted_manifest_digest" | grep -Eq '^[0-9a-f]{64}$' || fail \
      "KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256, SHA256SUMS dosyasının banka kabul özeti olmalıdır"
    [ -d "$bundle_input" ] || fail "çevrimdışı bundle dizini eksik: $bundle_input"
    bundle="$(CDPATH= cd -- "$bundle_input" && pwd -P)"
    manifest="$bundle/SHA256SUMS"
    matrix="$bundle/BUILD-MATRIX"
    npm_cache="$bundle/npm-cache"
    browser_root="$bundle/playwright"

    [ -f "$manifest" ] || fail "çevrimdışı bundle içinde SHA256SUMS bildirimi yok"
    [ -f "$matrix" ] || fail "çevrimdışı bundle içinde BUILD-MATRIX kaydı yok"
    [ -d "$npm_cache" ] || fail "çevrimdışı bundle içinde npm-cache dizini yok"
    [ -d "$browser_root" ] || fail "çevrimdışı bundle içinde Playwright tarayıcı dizini yok"

    if command -v sha256sum >/dev/null 2>&1; then
      actual_manifest_digest="$(sha256sum "$manifest" | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
      actual_manifest_digest="$(shasum -a 256 "$manifest" | awk '{print $1}')"
    else
      fail "kabul edilmiş bundle paketini doğrulamak için sha256sum veya shasum gereklidir"
    fi
    [ "$actual_manifest_digest" = "$trusted_manifest_digest" ] || fail \
      "çevrimdışı bundle bildirimi banka kabul özetiyle eşleşmiyor"

    awk '
      NF != 2 || length($1) != 64 || $1 !~ /^[0-9a-f]+$/ ||
        $2 !~ /^\.\// || $2 ~ /(^|\/)\.\.(\/|$)/ { exit 1 }
      END { if (NR == 0) exit 1 }
    ' "$manifest" || fail "çevrimdışı bundle SHA256SUMS dosyası güvensiz bir girdi içeriyor"
    if find "$bundle" -type l -print -quit | grep -q .; then
      fail "çevrimdışı bundle sembolik bağ içermemelidir"
    fi
    manifest_paths="$(awk '{print $2}' "$manifest" | LC_ALL=C sort)"
    actual_paths="$({
      CDPATH= cd -- "$bundle"
      find . -type f ! -name SHA256SUMS -print | LC_ALL=C sort
    })"
    [ "$actual_paths" = "$manifest_paths" ] ||
      fail "çevrimdışı bundle mühürlenmemiş veya eksik dosyalar içeriyor"
    grep -Eq '  \./BUILD-MATRIX$' "$manifest" || fail "BUILD-MATRIX bütünlük mührüyle korunmuyor"
    grep -Eq '  \./npm-cache/' "$manifest" || fail "npm önbelleği bütünlük mührüyle korunmuyor"
    grep -Eq '  \./playwright/' "$manifest" || fail "Playwright ağacı bütünlük mührüyle korunmuyor"

    if command -v sha256sum >/dev/null 2>&1; then
      (CDPATH= cd -- "$bundle" && sha256sum --check SHA256SUMS >/dev/null) ||
        fail "çevrimdışı bundle sağlama toplamı doğrulaması başarısız"
    elif command -v shasum >/dev/null 2>&1; then
      (CDPATH= cd -- "$bundle" && shasum -a 256 -c SHA256SUMS >/dev/null) ||
        fail "çevrimdışı bundle sağlama toplamı doğrulaması başarısız"
    fi

    target_platform="$(sed -n 's/^oci-platform=//p' "$matrix")"
    [ -n "$target_platform" ] || fail "BUILD-MATRIX içinde oci-platform yok"
    host_os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$(uname -m)" in
      x86_64|amd64) host_arch="amd64" ;;
      arm64|aarch64) host_arch="arm64" ;;
      *) fail "desteklenmeyen ana makine mimarisi: $(uname -m)" ;;
    esac
    [ "$target_platform" = "$host_os/$host_arch" ] || fail \
      "bundle platformu $target_platform, ana makine $host_os/$host_arch ile eşleşmiyor"

    (
      cd "$e2e_root"
      wait_for_readiness
      npm ci --offline --ignore-scripts --no-audit --no-fund --cache "$npm_cache"
      verify_browser "$browser_root"
      npm run "$suite"
    )
    ;;
  private-index)
    registry="${KT_SCAFFOLD_NPM_REGISTRY:-}"
    browser_root="${PLAYWRIGHT_BROWSERS_PATH:-}"
    [ -n "$registry" ] || fail \
      "private-index kipi KT_SCAFFOLD_NPM_REGISTRY gerektirir"
    registry_lower="$(printf '%s' "$registry" | tr '[:upper:]' '[:lower:]')"
    case "$registry_lower" in
      *registry.npmjs.org*|*npmjs.com*|*yarnpkg.com*)
        fail "genel npm kayıt depoları yasaktır"
        ;;
    esac
    [ -n "$browser_root" ] || fail \
      "private-index kipi onaylı PLAYWRIGHT_BROWSERS_PATH gerektirir"
    (
      cd "$e2e_root"
      wait_for_readiness
      npm_config_registry="$registry" \
      npm_config_replace_registry_host=always \
        npm ci --ignore-scripts --no-audit --no-fund --registry "$registry"
      verify_browser "$browser_root"
      npm run "$suite"
    )
    ;;
  *)
    fail "KT_SCAFFOLD_E2E_MODE, offline veya private-index olmalıdır"
    ;;
esac
