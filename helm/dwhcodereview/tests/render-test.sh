#!/usr/bin/env bash
# ============================================================================
# dwhcodereview Helm chart render testleri.
#
# Calistirma (repo kokunden):
#   bash helm/dwhcodereview/tests/render-test.sh
#
# HELM_BIN ile farkli bir helm ikilisi verilebilir:
#   HELM_BIN=/c/Users/me/bin/helm.exe bash helm/dwhcodereview/tests/render-test.sh
# ============================================================================
set -uo pipefail

HELM_BIN="${HELM_BIN:-helm}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHART_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

pass() { printf '  PASS  %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL  %s\n' "$1"; printf '        %s\n' "$2"; FAIL=$((FAIL + 1)); }

# Rancher UI / --set ile verilecek zorunlu degerler.
REQUIRED_SET=(
  --set-string "appConfig.mssqlConnectionString=DRIVER={ODBC Driver 18 for SQL Server};SERVER=test-sql;DATABASE=master;UID=u;PWD=p;TrustServerCertificate=yes"
  --set-string "appConfig.apiAccessToken=render-test-access-token"
  --set-string "appConfig.apiAdminToken=render-test-admin-token0"
)

render() {
  "$HELM_BIN" template dwhcodereview "$CHART_DIR" "$@" 2>&1
}

# --- 1) Rancher varsayilani: yalnizca values.yaml + zorunlu degerler --------
# Rancher Apps UI chart kokundeki values.yaml disindaki dosyalari yuklemez;
# bu yuzden values-test.yaml OLMADAN render edilebilmeli.
t="values.yaml + zorunlu degerler ile render edilir (Rancher UI yolu)"
out="$(render "${REQUIRED_SET[@]}")"
rc=$?
if [ $rc -eq 0 ]; then pass "$t"; else fail "$t" "$(printf '%s' "$out" | head -3)"; fi

# --- 2) nginxConfig frontend altinda tanimli olmali -------------------------
t="frontend.nginxConfig degerleri frontend.resources icine sizmaz"
out="$(render "${REQUIRED_SET[@]}")"
rc=$?
if [ $rc -ne 0 ]; then
  fail "$t" "render basarisiz, sizinti kontrol edilemedi: $(printf '%s' "$out" | head -1)"
elif printf '%s' "$out" | grep -qE '^[[:space:]]+override: '; then
  fail "$t" "render ciktisinda 'override:' alani var (nginxConfig yanlis yere dusmus)"
elif printf '%s' "$out" | grep -qE '^[[:space:]]+proxyReadTimeout: '; then
  fail "$t" "render ciktisinda 'proxyReadTimeout:' alani var"
else
  pass "$t"
fi

# --- 3) nginx ConfigMap gercekten uretilir ---------------------------------
t="nginxConfig.override=true iken frontend nginx ConfigMap render edilir"
out="$(render "${REQUIRED_SET[@]}")"
if printf '%s' "$out" | grep -q 'dwhcodereview-frontend-nginx'; then
  pass "$t"
else
  fail "$t" "frontend nginx ConfigMap render edilmedi"
fi

# --- 4) Zorunlu deger bos iken guard beklenen mesajla durdurur --------------
t="mssqlConnectionString bos iken install beklenen mesajla durur"
out="$(render)"
if printf '%s' "$out" | grep -q 'mssqlConnectionString'; then
  pass "$t"
else
  fail "$t" "beklenen guard mesaji gorulmedi: $(printf '%s' "$out" | head -2)"
fi

# --- 5) Kisa apiAccessToken reddedilir --------------------------------------
t="16 karakterden kisa apiAccessToken reddedilir"
out="$(render --set-string "appConfig.mssqlConnectionString=DRIVER={x};SERVER=s" --set-string "appConfig.apiAccessToken=kisa")"
if printf '%s' "$out" | grep -q 'apiAccessToken'; then
  pass "$t"
else
  fail "$t" "kisa token kabul edildi"
fi

# --- 6) secrets.create=false + existingSecret bos -> durur ------------------
t="secrets.create=false iken existingSecret bos birakilamaz"
out="$(render "${REQUIRED_SET[@]}" --set secrets.create=false --set-string secrets.existingSecret=)"
if printf '%s' "$out" | grep -q 'existingSecret'; then
  pass "$t"
else
  fail "$t" "Secret uretilmeden deploy'a izin verildi (backend envFrom bos Secret'a bakar)"
fi

# --- 7) secrets.create=true + existingSecret dolu -> durur ------------------
t="secrets.create=true ile existingSecret birlikte kullanilamaz"
out="$(render "${REQUIRED_SET[@]}" --set secrets.create=true --set-string secrets.existingSecret=harici-secret)"
if printf '%s' "$out" | grep -qi 'existingSecret'; then
  pass "$t"
else
  fail "$t" "iki Secret kaynagi ayni anda kabul edildi"
fi

# --- 8) Secret adi ile backend envFrom adi ayni yardimciyi kullanir ---------
t="harici Secret kipinde backend envFrom harici Secret adini gosterir"
out="$(render "${REQUIRED_SET[@]}" --set secrets.create=false --set-string secrets.existingSecret=harici-secret)"
if printf '%s' "$out" | grep -q 'name: harici-secret'; then
  pass "$t"
else
  fail "$t" "backend envFrom harici Secret adini kullanmiyor"
fi

# --- 9) Ortam override dosyalari kendi baslarina render edilebilir ---------
for env_file in values-test.yaml values-prod.yaml; do
  t="$env_file ile render edilir"
  out="$(render -f "$CHART_DIR/$env_file")"
  rc=$?
  if [ $rc -eq 0 ]; then pass "$t"; else fail "$t" "$(printf '%s' "$out" | head -2)"; fi
done

# --- 10) Rancher UI form tanimi zorunlu alanlari sorar ----------------------
# Rancher Apps UI chart kokundeki questions.yaml'i okuyup form uretir; zorunlu
# degerler burada sorulmazsa kullanici bos values.yaml ile install dener.
t="questions.yaml zorunlu appConfig alanlarini sorar"
q="$CHART_DIR/questions.yaml"
if [ ! -f "$q" ]; then
  fail "$t" "questions.yaml yok; Rancher UI zorunlu degerleri soramaz"
elif ! grep -q 'appConfig.mssqlConnectionString' "$q"; then
  fail "$t" "questions.yaml appConfig.mssqlConnectionString sormuyor"
elif ! grep -q 'appConfig.apiAccessToken' "$q"; then
  fail "$t" "questions.yaml appConfig.apiAccessToken sormuyor"
else
  pass "$t"
fi

# --- 11) questions.yaml gecerli YAML ve chart paketine dahil ---------------
t="questions.yaml gecerli YAML ve helm lint temiz"
out="$("$HELM_BIN" lint "$CHART_DIR" --set-string "appConfig.mssqlConnectionString=DRIVER={x};SERVER=s" --set-string "appConfig.apiAccessToken=render-test-access-token" 2>&1)"
rc=$?
if [ $rc -eq 0 ]; then pass "$t"; else fail "$t" "$(printf '%s' "$out" | head -3)"; fi

# --- 12) Paketlenen chart Rancher formunu tasir, testleri tasimaz ----------
t="helm package ciktisi questions.yaml icerir, tests/ icermez"
pkg_dir="$(mktemp -d)"
out="$("$HELM_BIN" package "$CHART_DIR" -d "$pkg_dir" 2>&1)"
rc=$?
if [ $rc -ne 0 ]; then
  fail "$t" "$(printf '%s' "$out" | head -2)"
else
  tgz="$(ls "$pkg_dir"/*.tgz 2>/dev/null | head -1)"
  listing="$(tar -tzf "$tgz" 2>/dev/null)"
  if ! printf '%s' "$listing" | grep -q 'questions.yaml'; then
    fail "$t" "questions.yaml paketten dislanmis"
  elif printf '%s' "$listing" | grep -q 'tests/'; then
    fail "$t" "tests/ pakete dahil edilmis"
  else
    pass "$t"
  fi
fi
rm -rf "$pkg_dir"

printf '\n%s\n' "-----------------------------------------"
printf 'PASS: %d  FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
