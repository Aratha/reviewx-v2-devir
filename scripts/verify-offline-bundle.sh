#!/usr/bin/env sh
set -eu

fail() {
  echo "çevrimdışı bundle hatası: $*" >&2
  exit 2
}

bundle_input="${KT_SCAFFOLD_OFFLINE_BUNDLE:-}"
trusted_digest="${KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256:-}"
[ -n "$bundle_input" ] || fail "KT_SCAFFOLD_OFFLINE_BUNDLE gereklidir"
case "$bundle_input" in
  /*) ;;
  *) fail "KT_SCAFFOLD_OFFLINE_BUNDLE mutlak bir yol olmalıdır" ;;
esac
printf '%s\n' "$trusted_digest" | grep -Eq '^[0-9a-f]{64}$' ||
  fail "KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256 banka kabul özeti olmalıdır"
[ -d "$bundle_input" ] || fail "çevrimdışı bundle dizini eksik: $bundle_input"
bundle="$(CDPATH= cd -- "$bundle_input" && pwd -P)"
[ "$bundle" = "$bundle_input" ] || fail "çevrimdışı bundle yolu önceden kanonik olmalıdır"

manifest="$bundle/SHA256SUMS"
matrix="$bundle/BUILD-MATRIX"
[ -f "$manifest" ] || fail "SHA256SUMS eksik"
[ -f "$matrix" ] || fail "BUILD-MATRIX eksik"
for required in \
  "$bundle/npm-cache" \
  "$bundle/wheelhouse/generator" \
  "$bundle/wheelhouse/python-fastapi"
do
  [ -d "$required" ] || fail "gerekli çevrimdışı bağımlılık bağlamı eksik: $required"
done
[ -f "$bundle/runtime-images.tar" ] || fail "runtime-images.tar eksik"

if command -v sha256sum >/dev/null 2>&1; then
  actual_digest="$(sha256sum "$manifest" | awk '{print $1}')"
  checksum_command="sha256sum --check SHA256SUMS"
elif command -v shasum >/dev/null 2>&1; then
  actual_digest="$(shasum -a 256 "$manifest" | awk '{print $1}')"
  checksum_command="shasum -a 256 -c SHA256SUMS"
else
  fail "sha256sum veya shasum gereklidir"
fi
[ "$actual_digest" = "$trusted_digest" ] ||
  fail "bundle bildirimi banka kabul özetiyle eşleşmiyor"

awk '
  NF != 2 || length($1) != 64 || $1 !~ /^[0-9a-f]+$/ ||
    $2 !~ /^\.\// || $2 ~ /(^|\/)\.\.(\/|$)/ { exit 1 }
  END { if (NR == 0) exit 1 }
' "$manifest" || fail "SHA256SUMS güvensiz bir girdi içeriyor"
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
for sealed in BUILD-MATRIX runtime-images.tar npm-cache/ wheelhouse/generator/ wheelhouse/python-fastapi/
do
  grep -Fq "  ./$sealed" "$manifest" || fail "$sealed bütünlük mührüyle korunmuyor"
done
(CDPATH= cd -- "$bundle" && sh -c "$checksum_command" >/dev/null) ||
  fail "çevrimdışı bundle sağlama toplamı doğrulaması başarısız"

target_platform="$(sed -n 's/^oci-platform=//p' "$matrix")"
[ -n "$target_platform" ] || fail "BUILD-MATRIX içinde oci-platform yok"
host_os="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$(uname -m)" in
  x86_64|amd64) host_arch="amd64" ;;
  arm64|aarch64) host_arch="arm64" ;;
  *) fail "desteklenmeyen ana makine mimarisi: $(uname -m)" ;;
esac
[ "$target_platform" = "$host_os/$host_arch" ] ||
  fail "bundle platformu $target_platform, ana makine $host_os/$host_arch ile eşleşmiyor"

echo "çevrimdışı bundle doğrulandı: $bundle"
