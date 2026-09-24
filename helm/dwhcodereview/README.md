# dwhcodereview chart

DWH Code Review yayını KT Verim'in tag tabanlı deployment düzenini kullanır: GitHub
imajları GHCR'a yayımlar, Azure mevcut Secure File kubeconfig'iyle `deploy.sh`'yi
çalıştırır. Chart, kt-vibecoding-boilerplate'in backend/frontend ürün şablonunu izler.
Tek değer kaynağı `values.yaml`; Helm değer sözleşmesi `values.schema.json` dosyasıdır.

## Dosya düzeni

- `Chart.yaml`: chart 0.2.0; uygulama appVersion 1.0.0.
- `values.yaml`: `backend` ve `frontend` değerleri; ortam dosyası (values-test/prod) yoktur.
- `values.schema.json`: alan bazında sözleşme; bilinmeyen anahtar render'ı durdurur.
- `templates/_helpers.tpl`: ortak ad, etiket, imaj, backend ayarı ve Nginx yardımcıları.
- `templates/_validation.tpl`: iç registry, ağ kuralı, sır, sertifika hostu ve kalıcılık kontrolleri.
- `templates/backend-*.yaml`: Deployment, Service, ConfigMap, NetworkPolicy, PVC.
- `templates/frontend-*.yaml`: Deployment, Service, ConfigMap (Nginx), NetworkPolicy.
- `templates/application-ingress.yaml`: tek giriş noktası; `/api` backend'e, `/` frontend'e.
- `deploy.sh`: Azure'ın çağırdığı Helm deployment giriş noktası.
- `certs/ailab-test.crt`: doğrulanmış wildcard public sertifika ve CA zinciri.

## Yayın ve deployment

GitHub'da `.github/workflows/image-build.yml` main push/merge ile `dwhcodereview-backend`
ve `dwhcodereview-frontend` imajlarını GHCR'a `latest`, tarih, kısa ve tam commit SHA
etiketleriyle yayımlar. PR üzerinde imaj yayımlanmaz. Azure şunu çalıştırır:

```sh
export KUBECONFIG=<Azure Secure File yolu>
bash helm/dwhcodereview/deploy.sh
```

`IMAGE_TAG` varsayılanı `latest`tir. Azure'da (`TF_BUILD=true` veya `BUILD_SOURCEVERSION`
tanımlı) script bu isteği `BUILD_SOURCEVERSION` içindeki tam 40 haneli commit SHA'sına
çevirir; eksik/geçersiz SHA hiçbir Helm veya Kubernetes komutu çalışmadan hata üretir.
Açıkça verilen tarih, sürüm veya SHA etiketi korunur. Her iki imaj aynı etiketi alır.
Commit etiketi henüz yayımlanmamışsa geçici `ImagePullBackOff` görülebilir; Helm `--wait`
ve `HELM_TIMEOUT` (30 dakika) doğru imajla hazır olmayı bekler, olmazsa geri alır.

Script sırasıyla: Helm lint, `[RBAC]` yetki raporu, namespace, çalışma zamanı Secret'ı,
askıdaki release kurtarma (`pending-install` kaldırılır, `pending-upgrade/rollback` son
sürüme döner), eski chart'ın Ingress'ini kaldırma, `helm upgrade --install --reset-values
--wait` (Helm 3'te `--atomic`, Helm 4'te `--rollback-on-failure`), eksik TLS Secret'ı ve
gerekirse rollout restart adımlarını çalıştırır. Başarısız komutun çıkış kodu pipeline'a
aynen yansır.

Küme olmadan manifest üretmek için: `bash helm/dwhcodereview/deploy.sh --render`.

## İmaj yolu

İmajlar kümenin çekebildiği iç registry (GHCR proxy-cache) yolundan gelir:
`cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/dwhcodereview-{backend,frontend}`.
Doğrudan `ghcr.io/...` referansı node üzerinde çözülemez; public registry yolları render
aşamasında reddedilir. `digest` verilirse etiketin önüne geçer; `deploy.sh` etiket
seçimini ezmemesi için digest değerlerini boşaltır. `latest` etiketi her Pod
başlangıcında yeniden çekilir (`Always`), commit etiketi ve digest önbellekten çekilir.

## Giriş noktası ve TLS

```yaml
frontend:
  ingress:
    className: nginx
    host: dwhcodereview.ailab-test.kuveytturk.com.tr
    tlsSecretName: ailab-tls
```

Yayınlanan adres: `https://dwhcodereview.ailab-test.kuveytturk.com.tr`. Ingress `/api`
yolunu doğrudan backend'e, `/` yolunu frontend'e yönlendirir. Canlı inceleme akışı
(SSE) için `proxy-buffering: "off"` ve 3600 sn okuma/yazma zaman aşımı tanımlıdır.
Önceki chart'taki `dwhcodereview.ailabtest...` (tiresiz) host sertifika kapsamında
değildir; `ailab-tls` ile bu tür host render aşamasında reddedilir.

TLS Secret'ları namespace-scoped'tır: `ailab-tls` release'in namespace'inde yoksa
ingress-nginx sahte varsayılan sertifikayı sunar. `deploy.sh`, Helm tamamlandıktan sonra
kurulan Ingress'ten etkin host ve Secret adını okur. Hedef Secret yoksa oluşturma ve
`kt-verim/ailab-tls` kaynağını okuma yetkileri kontrol edilir; ikisi de `ALLOW` ise
kaynak Secret'ın `tls.key` alanı repodaki public zincirle birleştirilir. OpenSSL zincir,
tarih, sunucu amacı ve hostname kontrolü yapar; kubectl client dry-run sertifika/anahtar
eşleşmesini doğrular; ardından yalnız `create` denenir. Hedef zaten varsa `[TLS] EXISTS`
yazılır ve içeriği değiştirilmez. `[TLS] CREATED` yalnız Secret'ın oluşturulduğunu
kanıtlar; sunulan HTTPS sertifikası ayrıca kontrol edilmelidir.

`certs/ailab-test.crt` sunucu sertifikasını, `Kuveyt Turk Wireless Network` ara CA'sını
ve `Kuveyt Turk Trust Network` kök CA'sını içerir; kt-vibecoding-boilerplate'teki dosyayla
bayt-bayt aynıdır. SAN `*.ailab-test.kuveytturk.com.tr` ve `*.ailab.kuveytturk.com.tr`
adreslerini kapsar; sunucu sertifikası 14 Ağustos 2026–13 Ağustos 2028 arasında
geçerlidir. **Ara CA 21 Ocak 2027'de sona erer**; bu tarihten sonra eksik TLS Secret'ı
oluşturma adımı zincir doğrulamasında durur. Sunucu SHA-256 parmak izi:
`6e334fc52dcb4b230f5ca51a897421142d4847db4b4e0fec2c344221924af0fc`. Dosyada private key
yoktur; HTTPS için bu sertifikaya uyan anahtar kümedeki kaynak Secret'tan gelir.

## Çalışma zamanı yapılandırması

Sır olmayan ayarlar `backend.config` altında `backend/config.py` alanlarının env adlarıyla
tutulur ve ConfigMap olarak aktarılır; değerler metin olmalıdır (`"true"`, `"6"`).
`CORS_ORIGINS` boşsa `https://<frontend.ingress.host>` türetilir. Şema bilinen anahtarlar
dışındakileri, şablon ise sır anahtarlarını reddeder.

Sırlar chart dışında yönetilen `dwhcodereview-runtime` Secret'ındadır ve backend'e
`envFrom` ile bağlanır. Chart Secret üretmez; `helm uninstall` bu Secret'ı silmez.

| Anahtar | Kullanım |
| --- | --- |
| `MSSQL_CONNECTION_STRING` | ODBC Driver 18 bağlantı dizesi |
| `MSSQL_PASSWORD` | Ayrık SQL alanları (`MSSQL_SERVER`, `MSSQL_USER` config'te) kullanılıyorsa |
| `LLM_API_KEY` | LLM gateway anahtar istiyorsa |
| `API_ACCESS_TOKEN`, `API_ADMIN_TOKEN` | `/api` ve yönetim uçlarının korunması |

`deploy.sh` Secret'ı Helm'den önce hazırlar: yoksa oluşturur (değer verilmemişse boş),
pipeline'da **dolu** verilen anahtarları yazar, verilmeyen veya boş olanlarda kümedeki
değeri korur. Değerler argüman olarak geçmez ve loglanmaz; yalnız anahtar adları
yazılır (`[RUNTIME] CREATED/UPDATED/UNCHANGED/EXISTS`). Azure'da eşlenmemiş bir secret
değişkeni `$(AD)` metni olarak gelirse Secret'a yazılmaz, deployment durur. Bir sır
güncellendiğinde Pod şablonu değişmediyse backend yeniden başlatılır. Secret'ı elle
değiştirirseniz backend'i `kubectl rollout restart` ile yeniden başlatın.

Secret elle de hazırlanabilir:

```sh
printf '%s' 'DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>,1433;...' > baglanti.txt
kubectl -n dwhcodereview create secret generic dwhcodereview-runtime \
  --from-file=MSSQL_CONNECTION_STRING=./baglanti.txt
```

Bağlantı dizesinde virgül ve süslü parantez bulunduğundan Helm `--set` yerine dosya
kullanın; dosya satır sonuyla bitmemelidir (`echo` yerine `printf '%s'`).

Kümede arayüzden SQL/LLM ayarı kaydetme (`PUT /api/sql-config`, `/api/llm-config`)
desteklenmez: uygulama bu ayarları `/app/.env` dosyasına yazar, container kök dosya
sistemi ise salt okunurdur. Ayarlar `backend.config` ve runtime Secret'tan gelir.
Frontend istekleri `X-API-Key` başlığı göndermez; `API_ACCESS_TOKEN` tanımlanırsa arayüz
`/api` çağrılarında 401 alır.

## Kalıcı veri

`review_rules.json` ve LLM logları backend `/app/data` altındaki PVC'de tutulur. PVC adı
eski chart ile aynıdır (`dwhcodereview-backend-data`); yükseltmede veri yerinde kalır.
PVC `helm.sh/resource-policy: keep` taşır. `ReadWriteOnce` hacim iki Pod'a aynı anda
bağlanamadığı için backend tek replika ve `Recreate` stratejisiyle çalışır; birden çok
replika render aşamasında reddedilir. `persistence.enabled: false` iken veri Pod ömürlü
`emptyDir`'dadır.

## Ağ politikası

Her iki bileşen yalnız `kube-system` (RKE2 ingress-nginx) namespace'inden gelen trafiği
kabul eder. Frontend yalnız statik dosya sunar ve dışarı bağlantı açmaz. Backend egress'i
küme DNS'i ile kurum içi (private) ağdaki SQL Server (1433) ve LLM uç noktasıyla (80/443)
sınırlıdır; `LLM_ENFORCE_PRIVATE_NETWORK` ile aynı sınırdır. Gerçek SQL Server ve LLM
hostları netleştiğinde CIDR'leri daraltın; LLM başka bir portta dinliyorsa portu ekleyin.
`0.0.0.0/0`, boş seçici ve boş kural render aşamasında reddedilir.

## Deployment girdileri

Azure runner Bash, Helm, kubectl ve OpenSSL kullanır. KUBECONFIG mevcut pipeline Secure
File adımından sağlanır.

| Değişken | Varsayılan / kullanım |
| --- | --- |
| `RELEASE`, `NAMESPACE` | `dwhcodereview` |
| `IMAGE_TAG` | `latest`; Azure'da build commit'ine çözülür. Açık etiket korunur. |
| `BUILD_SOURCEVERSION`, `TF_BUILD` | Azure'ın otomatik sağladığı kaynak commit ve build işareti |
| `HELM_TIMEOUT` | `30m` |
| `CHART_DIR`, `VALUES_FILE` | Script'in bulunduğu chart ve onun `values.yaml` dosyası |
| `INGRESS_HOST` | Boşsa values.yaml'daki host; doluysa ezilir |
| `TLS_SECRET` | Ingress TLS Secret adı; boşsa `ailab-tls` |
| `TLS_SOURCE_NAMESPACE`, `TLS_SOURCE_SECRET` | `kt-verim` / `ailab-tls`; private key kaynağı |
| `RUNTIME_SECRET` | `dwhcodereview-runtime` |
| `MSSQL_CONNECTION_STRING`, `MSSQL_PASSWORD`, `LLM_API_KEY`, `API_ACCESS_TOKEN`, `API_ADMIN_TOKEN` | İsteğe bağlı; doluysa runtime Secret'a yazılır |

`[RBAC]` bloğu `kubectl auth can-i` ile aynı kimliğin runtime ve TLS Secret'ları,
Secret listeleme/oluşturma, `kt-verim/ailab-tls` okuma, Ingress listeleme ve Deployment
get/patch/watch yetkilerini raporlar. `ALLOW` izin, `DENY` ret, `UNKNOWN` karar
alınamadığı anlamına gelir; rapor dağıtımı atlatmaz veya hatayı başarıya çevirmez.

## Eski chart'tan geçiş

Önceki chart'taki `values-test.yaml`, `values-prod.yaml`, Rancher Apps formu
(`questions.yaml`), `appConfig`/`appConfigFallback` ve chart'ın ürettiği
`<release>-config` Secret'ı kaldırılmıştır; dağıtım Rancher UI yerine `deploy.sh`
üzerinden yapılır. Aynı release'i yükseltirken:

- eski `<release>-config` Secret'ı Helm tarafından silinir; sırları pipeline
  değişkenleriyle veya `dwhcodereview-runtime` Secret'ını önceden oluşturarak verin,
- `/app/data` PVC'si adını koruduğu için veri kaybolmaz,
- eski chart'ın bu release'e ait Ingress'i, aynı host/path çakışmasını önlemek için
  `deploy.sh` tarafından upgrade'den önce silinir,
- `--reset-values` eski release değerlerini taşımaz; yeni şema bunları zaten reddeder.

## Doğrulama

Chart veya `deploy.sh` değiştiğinde repo kökünden çalıştırın (küme gerekmez):

```sh
bash scripts/helm-chart-test.sh
```

Test gerçek `helm template/lint` ile chart sözleşmesini, repodaki sertifika zincirini ve
`deploy.sh`'nin apply yolunu kubectl/helm test dublörleriyle (Secret birleştirme, TLS
doğrulama, askıdaki release, eski Ingress, restart kararları) sınar. Gerçek kümede
rollout, imaj çekme ve HTTPS doğrulaması ayrıca yapılmalıdır.
