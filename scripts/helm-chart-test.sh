#!/usr/bin/env bash
# ============================================================================
# helm/dwhcodereview chart ve deploy.sh sözleşme testleri. Küme gerekmez:
# render gerçek helm ile yapılır; deploy.sh'nin apply yolu kubectl/helm test
# dublörleriyle, gerçek openssl ve kubectl (yalnız client-side dry-run) ile sınanır.
#
# Çalıştırma (repo kökünden):
#   bash scripts/helm-chart-test.sh
# ============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="$ROOT/helm/dwhcodereview"
REAL_HELM="$(command -v "${HELM_BIN:-helm}")" || { echo 'helm bulunamadı' >&2; exit 2; }
REAL_KUBECTL="$(command -v "${KUBECTL_BIN:-kubectl}")" || { echo 'kubectl bulunamadı' >&2; exit 2; }
command -v openssl >/dev/null || { echo 'openssl bulunamadı' >&2; exit 2; }
HOST=dwhcodereview.ailab-test.kuveytturk.com.tr
SHA=0123456789abcdef0123456789abcdef01234567

PASS=0
FAIL=0
pass() { printf '  PASS  %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL  %s\n        %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
check() { # check <ad> <koşul komutu...>
  local name="$1"; shift
  if "$@"; then pass "$name"; else fail "$name" "koşul sağlanmadı: $*"; fi
}
has() { printf '%s' "$1" | grep -qF -- "$2"; }
lacks() { ! printf '%s' "$1" | grep -qF -- "$2"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/home" "$TMP/tmp"
export HOME="$TMP/home"

render() { "$REAL_HELM" template dwhcodereview "$CHART" --namespace dwhcodereview "$@" 2>&1; }
expect_rejected() { # expect_rejected <ad> <beklenen mesaj parçası> <helm argümanları...>
  local name="$1" message="$2" out rc; shift 2
  out="$(render "$@")"; rc=$?
  if [ "$rc" -ne 0 ] && has "$out" "$message"; then pass "$name"
  else fail "$name" "rc=$rc; beklenen mesaj: $message; çıktı: $(printf '%s' "$out" | head -3)"; fi
}

echo '--- chart düzeni ve render'
layout="$(cd "$CHART" && find . -type f ! -name .DS_Store | LC_ALL=C sort | tr '\n' ' ')"
expected_layout='./.helmignore ./Chart.yaml ./README.md ./certs/ailab-test.crt ./deploy.sh ./templates/_helpers.tpl ./templates/_validation.tpl ./templates/application-ingress.yaml ./templates/backend-configmap.yaml ./templates/backend-deployment.yaml ./templates/backend-networkpolicy.yaml ./templates/backend-pvc.yaml ./templates/backend-service.yaml ./templates/frontend-configmap.yaml ./templates/frontend-deployment.yaml ./templates/frontend-networkpolicy.yaml ./templates/frontend-service.yaml ./values.schema.json ./values.yaml '
check 'chart dosya düzeni standartla aynı (tek values.yaml, certs/, deploy.sh)' test "$layout" = "$expected_layout"

out="$("$REAL_HELM" lint "$CHART" 2>&1)"
check 'helm lint temiz' has "$out" '0 chart(s) failed'

out="$(render)"; rc=$?
check 'varsayılan values.yaml ile render edilir' test "$rc" -eq 0
kinds="$(printf '%s\n' "$out" | grep -E '^kind: ' | LC_ALL=C sort | uniq -c | tr -s ' ' | tr '\n' ';')"
check 'kaynaklar: 2 ConfigMap, 2 Deployment, 1 Ingress, 2 NetworkPolicy, 1 PVC, 2 Service' \
  test "$kinds" = ' 2 kind: ConfigMap; 2 kind: Deployment; 1 kind: Ingress; 2 kind: NetworkPolicy; 1 kind: PersistentVolumeClaim; 2 kind: Service;'
lacks_kind() { ! printf '%s\n' "$out" | grep -qE '^kind: (Secret|ServiceAccount)$'; }
check 'chart Secret üretmez (sırlar chart dışındaki runtime Secret'"'"'ta)' lacks_kind

ingress="$(render --show-only templates/application-ingress.yaml)"
check 'Ingress host wildcard sertifika kapsamındaki ailab-test hostu' has "$ingress" "- host: \"$HOST\""
check 'Ingress TLS ailab-tls ve nginx sınıfı' has "$ingress" 'secretName: "ailab-tls"'
check 'Ingress /api backend servisine gider' has "$(printf '%s' "$ingress" | grep -A5 'path: /api')" 'backend-'
check 'Ingress / frontend servisine gider' has "$(printf '%s' "$ingress" | grep -A5 'path: /$')" 'frontend-'
check 'SSE için proxy-buffering kapalı' has "$ingress" 'nginx.ingress.kubernetes.io/proxy-buffering: "off"'
check 'SSE için okuma zaman aşımı 3600 sn' has "$ingress" 'nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"'

count() { printf '%s\n' "$out" | grep -cF -- "$1"; }
check 'iki Pod da non-root' test "$(count 'runAsNonRoot: true')" -eq 2
check 'iki container da salt-okunur kök dosya sistemi' test "$(count 'readOnlyRootFilesystem: true')" -eq 2
check 'iki container da tüm yetenekleri bırakır' test "$(count 'capabilities: {drop: ["ALL"]}')" -eq 2
check 'ServiceAccount token bağlanmaz' test "$(count 'automountServiceAccountToken: false')" -eq 2
check 'frontend non-root 8080 dinler' has "$(render --show-only templates/frontend-configmap.yaml)" 'listen 8080;'
check 'frontend Nginx yapılandırması backend adına bağımlı değil (egress kapalı)' \
  lacks "$(render --show-only templates/frontend-configmap.yaml)" 'proxy_pass'
check 'frontend ana nginx.conf imajdan bağımsız (pid emptyDir'"'"'de)' \
  has "$(render --show-only templates/frontend-configmap.yaml)" 'pid /var/run/nginx.pid;'

backend="$(render --show-only templates/backend-deployment.yaml)"
check 'backend imajı iç registry yolundan' has "$backend" 'image: "cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/dwhcodereview-backend:latest"'
check 'latest etiketi her başlangıçta çekilir' has "$backend" 'imagePullPolicy: Always'
check 'backend sırları runtime Secret'"'"'tan alır' has "$backend" 'secretRef: {name: "dwhcodereview-runtime"}'
check 'RWO veri hacminde Recreate stratejisi' has "$backend" 'type: Recreate'
backend="$(render --show-only templates/backend-deployment.yaml --set-string "backend.image.tag=$SHA")"
check 'commit etiketi imaja aktarılır' has "$backend" "dwhcodereview-backend:$SHA\""
check '  (commit etiketi önbellekten çekilir)' has "$backend" 'imagePullPolicy: IfNotPresent'
digest="sha256:$(printf 'a%.0s' $(seq 64))"
backend="$(render --show-only templates/backend-deployment.yaml --set-string "backend.image.digest=$digest")"
check 'digest etiketin önüne geçer' has "$backend" "dwhcodereview-backend@$digest\""

pvc="$(render --show-only templates/backend-pvc.yaml)"
check 'PVC adı eski chart ile aynı (veri korunur)' has "$pvc" 'name: dwhcodereview-backend-data'
check 'PVC release kaldırılınca silinmez' has "$pvc" 'helm.sh/resource-policy: keep'
config="$(render --show-only templates/backend-configmap.yaml)"
check 'CORS_ORIGINS Ingress hostundan türetilir' has "$config" "CORS_ORIGINS: https://$HOST"
config="$(render --show-only templates/backend-configmap.yaml --set-string backend.config.CORS_ORIGINS=https://a.example)"
check 'açık CORS_ORIGINS korunur' has "$config" 'CORS_ORIGINS: https://a.example'

echo '--- kapalı-başarısız doğrulamalar'
expect_rejected 'bilinmeyen üst anahtar reddedilir (eski appConfig)' "additional properties 'appConfig' not allowed" --set appConfig.llmModel=x
expect_rejected 'backend altındaki yazım hatası reddedilir' "additional properties 'replicas' not allowed" --set backend.replicas=2
expect_rejected 'sır ConfigMap ayarına yazılamaz (şema)' "additional properties 'API_ACCESS_TOKEN' not allowed" --set-string backend.config.API_ACCESS_TOKEN=abc
expect_rejected 'sır ConfigMap ayarına yazılamaz (şablon)' 'backend.config sır içeremez (MSSQL_PASSWORD)' --skip-schema-validation --set-string backend.config.MSSQL_PASSWORD=abc
expect_rejected 'ayar değerleri metin olmalıdır' "/backend/config/LLM_REQUEST_RETRIES" --set backend.config.LLM_REQUEST_RETRIES=3
expect_rejected 'public registry reddedilir' 'iç registry yolunu kullanmalıdır' --set-string backend.image.repository=ghcr.io/kt-vibecoding/dwhcodereview-backend
expect_rejected 'geçersiz digest reddedilir' '/backend/image/digest' --set-string backend.image.digest=sha256:xyz
expect_rejected 'sertifika dışı ailabtest hostu reddedilir' 'ailab-tls wildcard sertifikasının' --set-string frontend.ingress.host=dwhcodereview.ailabtest.kuveytturk.com.tr
expect_rejected 'RWO veri hacminde birden çok backend replikası reddedilir' 'backend.replicaCount 1 olmalıdır' --set backend.replicaCount=2
printf 'backend:\n  networkPolicy:\n    egress: []\n' > "$TMP/no-egress.yaml"
expect_rejected 'backend egress boş bırakılamaz (şema)' '/backend/networkPolicy/egress' -f "$TMP/no-egress.yaml"
expect_rejected 'backend egress boş bırakılamaz (şablon)' 'DNS ile SQL Server ve LLM hedeflerini' --skip-schema-validation -f "$TMP/no-egress.yaml"
cat > "$TMP/open-egress.yaml" <<'EOF'
backend:
  networkPolicy:
    egress:
      - to: [{ipBlock: {cidr: 0.0.0.0/0}}]
        ports: [{protocol: TCP, port: 443}]
EOF
expect_rejected 'sınırsız egress CIDR reddedilir (şablon)' 'sınırsız ağ CIDR' --skip-schema-validation -f "$TMP/open-egress.yaml"
expect_rejected 'sınırsız egress CIDR reddedilir (şema)' "'not' failed" -f "$TMP/open-egress.yaml"

echo '--- sertifika zinciri'
cert="$CHART/certs/ailab-test.crt"
check 'sertifika dosyası private key içermez' test "$(grep -c 'PRIVATE KEY' "$cert")" -eq 0
check 'zincir leaf + ara CA + kök CA içerir' test "$(grep -c 'BEGIN CERTIFICATE' "$cert")" -eq 3
awk '/-----BEGIN CERTIFICATE-----/ { cert++ } cert > 1 { print }' "$cert" > "$TMP/ca.crt"
verifies() { openssl verify -purpose sslserver -verify_hostname "$1" -CAfile "$TMP/ca.crt" "$cert" >/dev/null 2>&1; }
check 'values.yaml hostu repodaki zincirle doğrulanır' verifies "$(sed -n 's/^    host: //p' "$CHART/values.yaml")"
rejects() { ! verifies "$1"; }
check 'eski ailabtest hostu zincirle doğrulanmaz' rejects dwhcodereview.ailabtest.kuveytturk.com.tr

echo '--- deploy.sh giriş noktası'
DEPLOY="$CHART/deploy.sh"
check 'bash sözdizimi geçerli' bash -n "$DEPLOY"
out="$(bash "$DEPLOY" --help 2>&1)"
check '--help kullanım yazar' has "$out" 'Usage: bash helm/dwhcodereview/deploy.sh'
bash "$DEPLOY" --bilinmeyen >/dev/null 2>&1; rc=$?
check 'bilinmeyen argüman 2 ile döner' test "$rc" -eq 2

# Test dublörleri: çağrıları kaydeder, küçük bir küme durumunu $FAKE_STATE'ten sunar.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
set -uo pipefail
state="$FAKE_STATE"
printf '%s\n' "$*" >> "$state/kubectl.log"
args=("$@")
flag() {
  local i
  for ((i = 0; i < ${#args[@]}; i++)); do
    case "${args[$i]}" in
      "$1") printf '%s' "${args[$((i + 1))]:-}"; return 0 ;;
      "$1="*) printf '%s' "${args[$i]#*=}"; return 0 ;;
    esac
  done
  return 1
}
ns="$(flag --namespace || echo default)"
output="$(flag --output || true)"
selector="$(flag --selector || true)"
store() { # store <manifest dosyası> — YAML (runtime) veya JSON (TLS) Secret
  local name namespace
  name="$(sed -n -e 's/^  name: //p' -e 's/^ *"name": "\(.*\)",*$/\1/p' "$1" | head -1)"
  namespace="$(sed -n -e 's/^  namespace: //p' -e 's/^ *"namespace": "\(.*\)",*$/\1/p' "$1" | head -1)"
  printf '%s/secret-%s-%s' "$state" "${namespace:-$ns}" "$name"
}
case "$1 ${2:-}" in
  "auth can-i")
    echo "${FAKE_CAN_I:-yes}"; [ "${FAKE_CAN_I:-yes}" = yes ] ;;
  "get namespace") [ -e "$state/ns-$3" ] ;;
  "create namespace") touch "$state/ns-$3"; echo "namespace/$3 created" ;;
  "get secret")
    file="$state/secret-$ns-$3"
    case "$output" in
      name) if [ -e "$file" ]; then echo "secret/$3"; fi ;;
      'go-template={{range'*) sed -n 's/^  \([^:]*\): ".*"$/\1/p' "$file" | LC_ALL=C sort ;;
      'go-template={{index .data'*)
        key="${output#*\"}"; key="${key%%\"*}"
        sed -n "s/^  $key: \"\(.*\)\"$/\1/p" "$file" | tr -d '\n' ;;
      'jsonpath={.type}'*) [ -e "$state/tls-source" ] && cat "$state/tls-source" ;;
      *) exit 1 ;;
    esac ;;
  "create secret") KUBECONFIG=/dev/null exec "$REAL_KUBECTL" "$@" ;;
  "create --filename")
    target="$(store "$3")"
    if [ -e "$target" ]; then echo 'AlreadyExists' >&2; exit 1; fi
    cp "$3" "$target" ;;
  "replace --filename")
    target="$(store "$3")"
    [ -e "$target" ] || exit 1
    cp "$3" "$target" ;;
  "get ingress")
    case "${3:-}" in
      --*)
        if [ -e "$state/installed" ]; then printf 'ailab-tls\t%s\n' "$FAKE_HOST"; fi ;;
      *) cat "$state/legacy-ingress-owner" 2>/dev/null || true ;;
    esac ;;
  "delete ingress") rm -f "$state/legacy-ingress-owner" ;;
  "get deployments")
    case "$output" in
      *generation*) [ -e "$state/installed" ] && cat "$state/backend-generation" ;;
      *metadata.name*)
        case "$selector" in
          *component=backend) echo "backend-deployment" ;;
          *) echo "backend-deployment frontend-deployment" ;;
        esac ;;
    esac ;;
  "rollout restart"|"rollout status") ;;
  *) echo "beklenmeyen kubectl çağrısı: $*" >&2; exit 97 ;;
esac
EOF
cat > "$TMP/bin/helm" <<'EOF'
#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "$*" >> "$FAKE_STATE/helm.log"
case "$1" in
  lint|template) exec "$REAL_HELM" "$@" ;;
  upgrade)
    if [ "${2:-}" = --help ]; then exec "$REAL_HELM" "$@"; fi
    if [ "${FAKE_HELM_UPGRADE_RC:-0}" != 0 ]; then exit "$FAKE_HELM_UPGRADE_RC"; fi
    if [ ! -e "$FAKE_STATE/installed" ]; then echo 1 > "$FAKE_STATE/backend-generation"
    elif [ "${FAKE_HELM_ROLLS_BACKEND:-1}" = 1 ]; then
      echo $(( $(cat "$FAKE_STATE/backend-generation") + 1 )) > "$FAKE_STATE/backend-generation"
    fi
    touch "$FAKE_STATE/installed" ;;
  list) cat "$FAKE_STATE/helm-list" 2>/dev/null || echo '[]' ;;
  uninstall|rollback|status) ;;
  *) echo "beklenmeyen helm çağrısı: $*" >&2; exit 97 ;;
esac
EOF
chmod +x "$TMP/bin/kubectl" "$TMP/bin/helm"

# Test chart kopyası: gerçek şablonlar, test CA'sıyla imzalanmış aynı host sertifikası.
pki="$TMP/pki"
mkdir -p "$pki"
printf 'basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n' > "$pki/ca.ext"
printf 'subjectAltName=DNS:*.ailab-test.kuveytturk.com.tr\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature,keyEncipherment\n' > "$pki/leaf.ext"
{
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$pki/root.key" -out "$pki/root.crt" \
    -subj /CN=test-root -days 2 -addext 'basicConstraints=critical,CA:TRUE' \
    -addext 'keyUsage=critical,keyCertSign,cRLSign'
  openssl req -new -newkey rsa:2048 -nodes -keyout "$pki/int.key" -out "$pki/int.csr" -subj /CN=test-int
  openssl x509 -req -in "$pki/int.csr" -CA "$pki/root.crt" -CAkey "$pki/root.key" -CAcreateserial \
    -out "$pki/int.crt" -days 2 -extfile "$pki/ca.ext"
  openssl req -new -newkey rsa:2048 -nodes -keyout "$pki/leaf.key" -out "$pki/leaf.csr" -subj /CN=ailab
  openssl x509 -req -in "$pki/leaf.csr" -CA "$pki/int.crt" -CAkey "$pki/int.key" -CAcreateserial \
    -out "$pki/leaf.crt" -days 2 -extfile "$pki/leaf.ext"
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$pki/other.key" -out "$pki/other.crt" -subj /CN=other -days 2
  sed 's/\*\.ailab-test\.kuveytturk\.com\.tr/*.other.test/' "$pki/leaf.ext" > "$pki/other-host.ext"
  openssl x509 -req -in "$pki/leaf.csr" -CA "$pki/int.crt" -CAkey "$pki/int.key" -CAcreateserial \
    -out "$pki/other-host.crt" -days 2 -extfile "$pki/other-host.ext"
} >/dev/null 2>&1 || { echo 'test PKI üretilemedi' >&2; exit 2; }
cp -R "$CHART" "$TMP/chart"
cat "$pki/leaf.crt" "$pki/int.crt" "$pki/root.crt" > "$TMP/chart/certs/ailab-test.crt"
cp -R "$CHART" "$TMP/chart-other-host"
cat "$pki/other-host.crt" "$pki/int.crt" "$pki/root.crt" > "$TMP/chart-other-host/certs/ailab-test.crt"

# deploy <durum dizini> [ENV=değer...] — temiz ortamda deploy.sh'yi çalıştırır.
deploy() {
  local state="$1"; shift
  env -i PATH="$TMP/bin:$PATH" HOME="$HOME" TMPDIR="$TMP/tmp" FAKE_STATE="$state" FAKE_HOST="$HOST" \
    REAL_HELM="$REAL_HELM" REAL_KUBECTL="$REAL_KUBECTL" CHART_DIR="$TMP/chart" \
    "$@" bash "$DEPLOY" 2>&1
}
new_state() { # new_state <ad> [kaynak anahtar dosyası]
  local state="$TMP/state-$1"
  mkdir -p "$state"
  printf 'kubernetes.io/tls\n%s\n%s\n' "$(openssl base64 -A < "$pki/leaf.crt")" \
    "$(openssl base64 -A < "${2:-$pki/leaf.key}")" > "$state/tls-source"
  printf '%s' "$state"
}
b64() { printf '%s' "$1" | openssl base64 -A; }
logs() { cat "$1/kubectl.log" "$1/helm.log" 2>/dev/null; }

out="$(bash "$DEPLOY" --render 2>/dev/null)"
check '--render kümesiz manifest üretir' has "$out" 'kind: Ingress'
out="$(env -i PATH="$PATH" HOME="$HOME" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" bash "$DEPLOY" --render 2>/dev/null)"
check 'Azure latest isteği build commit etiketine çözülür' has "$out" "dwhcodereview-frontend:$SHA\""
check '--render çıktısı yalnız manifesttir' test "$(printf '%s' "$out" | head -1)" = '---'

state="$(new_state no-source)"
out="$(deploy "$state" TF_BUILD=true)"; rc=$?
check 'Azure latest + eksik BUILD_SOURCEVERSION hiçbir araç çağrılmadan 2 döner' \
  test "$rc" -eq 2 -a ! -e "$state/kubectl.log" -a ! -e "$state/helm.log"
out="$(deploy "$state" TF_BUILD=true BUILD_SOURCEVERSION='bad;value')"; rc=$?
check 'geçersiz kaynak commit girdisi 2 ile reddedilir' test "$rc" -eq 2
check '  (girdi loga yansımaz)' lacks "$out" 'bad;value'

echo '--- deploy.sh apply (test dublörleri)'
connection='DRIVER={ODBC Driver 18 for SQL Server};SERVER=sql01,1433;DATABASE=master;UID=svc;PWD=Gizli,Parola!'
state="$(new_state fresh)"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" \
  MSSQL_CONNECTION_STRING="$connection" API_ACCESS_TOKEN='erisim-tokeni-0123456789')"; rc=$?
check 'ilk kurulum başarılı' test "$rc" -eq 0
check 'namespace oluşturulur' test -e "$state/ns-dwhcodereview"
check 'runtime Secret pipeline değerleriyle oluşturulur' has "$out" '[RUNTIME] CREATED namespace=dwhcodereview secret=dwhcodereview-runtime keys=MSSQL_CONNECTION_STRING API_ACCESS_TOKEN'
secret="$(cat "$state/secret-dwhcodereview-dwhcodereview-runtime" 2>/dev/null)"
check 'virgül/süslü parantezli bağlantı dizesi bayt-bayt saklanır' has "$secret" "MSSQL_CONNECTION_STRING: \"$(b64 "$connection")\""
check 'sır değerleri log ve argümanlarda görünmez' lacks "$out$(logs "$state")" 'Gizli,Parola!'
check '  (token da görünmez)' lacks "$out$(logs "$state")" 'erisim-tokeni-0123456789'
upgrade="$(grep '^upgrade --install' "$state/helm.log")"
check 'helm upgrade atomik, bekleyen ve değerleri sıfırlayan kipte' has "$upgrade" '--atomic --wait --timeout 30m'
check '  (--reset-values)' has "$upgrade" '--reset-values'
check '  (iki imaja da commit etiketi)' has "$upgrade" "frontend.image.tag=$SHA"
check 'TLS Secret repodaki zincirle doğrulanıp oluşturulur' has "$out" '[TLS] CREATED namespace=dwhcodereview secret=ailab-tls'
check '  (anahtar kaynağı kt-verim/ailab-tls)' has "$out" '[TLS] VALIDATED namespace=dwhcodereview secret=ailab-tls key-source=kt-verim/ailab-tls'
check 'RBAC raporu yazılır' has "$out" '[RBAC] END authorization only'
check 'commit etiketinde rollout restart yapılmaz' lacks "$(logs "$state")" 'rollout restart'

out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" \
  MSSQL_CONNECTION_STRING="$connection" API_ACCESS_TOKEN='erisim-tokeni-0123456789')"; rc=$?
check 'aynı değerlerle tekrar: Secret değişmez' has "$out" '[RUNTIME] UNCHANGED'
check '  (mevcut TLS Secret korunur)' has "$out" '[TLS] EXISTS namespace=dwhcodereview secret=ailab-tls'
: > "$state/kubectl.log"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA")"; rc=$?
check 'pipeline değeri yoksa mevcut Secret okunmadan korunur' has "$out" '[RUNTIME] EXISTS'
check '  (Secret içeriği okunmaz)' lacks "$(cat "$state/kubectl.log")" 'go-template'

printf '  LLM_API_KEY: "%s"\n' "$(b64 korunacak-anahtar)" >> "$state/secret-dwhcodereview-dwhcodereview-runtime"
: > "$state/kubectl.log"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" FAKE_HELM_ROLLS_BACKEND=0 \
  API_ACCESS_TOKEN='yeni-erisim-tokeni-987654')"; rc=$?
secret="$(cat "$state/secret-dwhcodereview-dwhcodereview-runtime")"
check 'dönen sır yalnız verilen anahtarı günceller' has "$out" '[RUNTIME] UPDATED namespace=dwhcodereview secret=dwhcodereview-runtime keys=API_ACCESS_TOKEN'
check '  (verilmeyen anahtarlar korunur)' has "$secret" "LLM_API_KEY: \"$(b64 korunacak-anahtar)\""
check '  (bağlantı dizesi korunur)' has "$secret" "MSSQL_CONNECTION_STRING: \"$(b64 "$connection")\""
check 'Pod şablonu değişmediyse yalnız backend yeniden başlatılır' has "$(cat "$state/kubectl.log")" 'rollout restart deployment/backend-deployment'
check '  (frontend yeniden başlatılmaz)' lacks "$(cat "$state/kubectl.log")" 'deployment/frontend-deployment'
: > "$state/kubectl.log"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" FAKE_HELM_ROLLS_BACKEND=1 \
  API_ACCESS_TOKEN='ucuncu-erisim-tokeni-4567')"; rc=$?
check 'Helm backend Pod'"'"'larını zaten yenilediyse ek restart yapılmaz' lacks "$(cat "$state/kubectl.log")" 'rollout restart'

state="$(new_state macro)"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" API_ACCESS_TOKEN='$(API_ACCESS_TOKEN)')"; rc=$?
check 'çözülmemiş Azure değişkeni reddedilir' has "$out" '[RUNTIME] ERROR API_ACCESS_TOKEN is an unresolved Azure variable'
check '  (Secret yazılmaz, Helm çalışmaz)' test "$rc" -ne 0 -a ! -e "$state/secret-dwhcodereview-dwhcodereview-runtime"
check '  (upgrade yok)' lacks "$(logs "$state")" 'upgrade --install'

state="$(new_state pending)"
echo '[{"name":"dwhcodereview","status":"pending-upgrade"}]' > "$state/helm-list"
echo dwhcodereview > "$state/legacy-ingress-owner"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA")"; rc=$?
order="$(grep -E '^(rollback|upgrade --install)' "$state/helm.log" | awk '{print $1}' | tr '\n' ' ')"
check 'askıdaki upgrade önce son sürüme döndürülür' test "$order" = 'rollback upgrade '
check 'eski chart'"'"'ın Ingress'"'"'i upgrade öncesi silinir' has "$(cat "$state/kubectl.log")" 'delete ingress dwhcodereview'
check 'boş runtime Secret ile ilk kurulum' has "$out" '[RUNTIME] CREATED namespace=dwhcodereview secret=dwhcodereview-runtime keys=none'
state="$(new_state foreign-ingress)"
echo baska-release > "$state/legacy-ingress-owner"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA")"
check 'başka release'"'"'e ait aynı adlı Ingress silinmez' lacks "$(cat "$state/kubectl.log")" 'delete ingress'

state="$(new_state wrong-key "$pki/other.key")"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA")"; rc=$?
check 'eşleşmeyen kaynak anahtarla TLS Secret oluşturulmaz' has "$out" '[TLS] ERROR Source private key does not form a valid pair'
check '  (hata kodu ve Secret yok)' test "$rc" -ne 0 -a ! -e "$state/secret-dwhcodereview-ailab-tls"
state="$(new_state other-host)"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" CHART_DIR="$TMP/chart-other-host")"; rc=$?
check 'host'"'"'u kapsamayan repo zinciriyle TLS Secret oluşturulmaz' \
  has "$out" '[TLS] ERROR Repository certificate chain, validity or hostname validation failed.'
check '  (kaynak anahtar okunmaz)' lacks "$(cat "$state/kubectl.log")" 'jsonpath={.type}'
state="$(new_state denied)"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" FAKE_CAN_I=no)"; rc=$?
check 'Secret oluşturma izni yoksa TLS denenmez' has "$out" '[TLS] ERROR Secret create permission is DENY'
state="$(new_state helm-fails)"
out="$(deploy "$state" TF_BUILD=True BUILD_SOURCEVERSION="$SHA" FAKE_HELM_UPGRADE_RC=7)"; rc=$?
check 'Helm hatası çıkış koduyla yansır' test "$rc" -eq 7
check '  (TLS adımına geçilmez)' lacks "$out" '[TLS]'

state="$(new_state local-latest)"
out="$(deploy "$state")"; rc=$?
check 'yerel latest dağıtımı iki Deployment'"'"'ı yeniden başlatır' \
  has "$(cat "$state/kubectl.log")" 'rollout restart deployment/frontend-deployment'
check '  (Helm 3 atomik geri alma)' has "$(grep '^upgrade' "$state/helm.log")" '--atomic'

printf '\n%s\n' '-----------------------------------------'
printf 'PASS: %d  FAIL: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
