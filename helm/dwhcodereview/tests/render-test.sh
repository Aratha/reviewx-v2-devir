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


# --- 13) CI'da sir aktarilmadi: bos --set-string dosyadaki degeri EZMEMELI ---
# helm'de --set-string, -f dosyalarindan daha yuksek onceliklidir. Azure DevOps
# secret degiskenleri script'e otomatik gecmedigi icin pipeline bos deger
# gonderir ve values-test.yaml'daki gecerli deger silinir. appConfigFallback
# bu durumda devreye girer.
t="bos --set-string values-test.yaml degerini ezmez (CI sir aktarilmadi senaryosu)"
out="$(render -f "$CHART_DIR/values-test.yaml" \
  --set-string "appConfig.mssqlConnectionString=" \
  --set-string "appConfig.apiAccessToken=" \
  --set-string "appConfig.apiAdminToken=")"
rc=$?
if [ $rc -ne 0 ]; then
  fail "$t" "render durdu: $(printf '%s' "$out" | head -2)"
elif printf '%s' "$out" | grep -qE '^  MSSQL_CONNECTION_STRING: ""$'; then
  fail "$t" "MSSQL_CONNECTION_STRING bos render edildi (fallback devreye girmedi)"
elif printf '%s' "$out" | grep -qE '^  API_ACCESS_TOKEN: ""$'; then
  fail "$t" "API_ACCESS_TOKEN bos render edildi (fallback devreye girmedi)"
else
  pass "$t"
fi

# --- 14) Fallback Rancher UI guard'ini DELMEZ -------------------------------
# Rancher yalnizca values.yaml yukler; orada fallback bostur, guard calismali.
t="fallback Rancher UI guard'ini delmez (values.yaml tek basina bos deger reddedilir)"
out="$(render --set-string "appConfig.mssqlConnectionString=")"
if printf '%s' "$out" | grep -q 'mssqlConnectionString'; then
  pass "$t"
else
  fail "$t" "Rancher yolunda bos baglanti dizesi sessizce kabul edildi"
fi

# --- 15) PROD fallback tasimaz -------------------------------------------
# Prod sirlari harici Secret'tan (secrets.create=false + existingSecret) gelir;
# chart orada Secret uretmez. Prod'a appConfigFallback eklemek, git'e
# commit'lenmis placeholder sirlari canliya tasima riski dogurur.
t="values-prod.yaml fallback tasimaz (prod sirlari harici Secret'tan gelir)"
if grep -q 'appConfigFallback' "$CHART_DIR/values-prod.yaml"; then
  fail "$t" "prod'a appConfigFallback eklenmis; prod sirlari harici Secret'tan gelmeli"
elif ! grep -qE '^[[:space:]]+create: false' "$CHART_DIR/values-prod.yaml"; then
  fail "$t" "prod secrets.create=false degil; fallback semantigi degismis olabilir"
else
  pass "$t"
fi

# --- 16) Dolu deger fallback'i ezer (oncelik sirasi) ------------------------
t="dolu --set-string fallback'i ezer"
out="$(render -f "$CHART_DIR/values-test.yaml" \
  --set-string "appConfig.mssqlConnectionString=DRIVER={x};SERVER=gercek-host")"
if printf '%s' "$out" | grep -q 'SERVER=gercek-host'; then
  pass "$t"
else
  fail "$t" "verilen deger yerine fallback kullanildi"
fi

printf '\n%s\n' "-----------------------------------------"
printf 'PASS: %d  FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
