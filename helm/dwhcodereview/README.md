# DWH Code Review — Helm Chart

`backend` (FastAPI + pyodbc/ODBC Driver 18) ve `frontend` (Vite build → Nginx)
imajlarını Rancher/Kubernetes ortamına deploy eder.

## Yapı

```
helm/dwhcodereview/
├── Chart.yaml
├── questions.yaml         # Rancher Apps UI form tanımı (zorunlu alanlar)
├── values.yaml            # ortak varsayılanlar (fail-fast guard'lar burada)
├── values-test.yaml       # TEST override (yalnızca CLI'da `-f` ile geçerli)
├── values-prod.yaml       # PROD override (harici Secret)
├── tests/
│   └── render-test.sh     # chart render/guard testleri
└── templates/
    ├── _helpers.tpl
    ├── secret.yaml               # backend .env → Secret (env anahtarları)
    ├── backend-deployment.yaml
    ├── backend-service.yaml
    ├── frontend-configmap.yaml   # nginx default.conf (proxy_pass → backend svc)
    ├── frontend-deployment.yaml
    ├── frontend-service.yaml
    ├── ingress.yaml              # tek giriş: frontend (Nginx /api'yi proxy'ler)
    ├── pvc.yaml                  # backend /app/data
    └── NOTES.txt
```

## Kurulum (Rancher UI)

> **Rancher yalnızca chart kökündeki `values.yaml`'ı yükler.**
> `values-test.yaml` ve `values-prod.yaml` Rancher tarafından **otomatik
> uygulanmaz**. Zorunlu değerler girilmediğinde install şu hatayla durur:
>
> ```
> Error: execution error at (dwhcodereview/templates/secret.yaml:...):
> appConfig.mssqlConnectionString bos olamaz ...
> ```

1. Rancher → **Apps → Charts** altında `DWH Code Review` chart'ını açın.
2. Açılan formda **Zorunlu Ayarlar** grubunu doldurun:
   - **SQL Server bağlantı dizesi** (`appConfig.mssqlConnectionString`)
   - **API erişim tokeni** (`appConfig.apiAccessToken`, en az 16 karakter)
   - **API yönetim tokeni** (`appConfig.apiAdminToken`, önerilir)
3. **Ağ / Ingress** grubunda `ingress.host` ve `appConfig.corsOrigins`
   değerlerini ortamla uyumlu hale getirin.
4. Install.

Form alanları `questions.yaml` içinde tanımlıdır. Formu kullanmadan
**Edit YAML** sekmesinden de aynı değerleri girebilirsiniz:

```yaml
appConfig:
  mssqlConnectionString: "DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>;DATABASE=master;UID=<user>;PWD=<pass>;TrustServerCertificate=yes"
  apiAccessToken: "<en-az-16-karakter>"
  apiAdminToken: "<en-az-16-karakter>"
```

## Kurulum (CLI / TEST)

```powershell
helm upgrade --install dwhcodereview ./helm/dwhcodereview `
  -n dwhcodereview --create-namespace `
  -f helm/dwhcodereview/values-test.yaml `
  --set-string appConfig.mssqlConnectionString='DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>;DATABASE=master;UID=<user>;PWD=<pass>;TrustServerCertificate=yes' `
  --set-string appConfig.apiAccessToken='<en-az-16-karakter>' `
  --set-string appConfig.apiAdminToken='<en-az-16-karakter>'
```

`--reuse-values` sırların korunacağının garantisi değildir; kalıcı sırlar için
harici Secret kullanın (aşağıdaki PROD bölümü) veya her upgrade'de aynı
değerleri tekrar verin.

## Kurulum (PROD)

`values-prod.yaml` içinde `secrets.create=false` ve
`secrets.existingSecret=dwhcodereview-secrets` tanımlıdır. Önce harici Secret'ı
oluşturun (anahtarlar `templates/secret.yaml` ile birebir aynı olmalı):

```powershell
kubectl -n dwhcodereview create secret generic dwhcodereview-secrets `
  --from-literal=MSSQL_CONNECTION_STRING='...' `
  --from-literal=API_ACCESS_TOKEN='...' `
  --from-literal=API_ADMIN_TOKEN='...' `
  --from-literal=LLM_BASE_URL='http://llm-gateway.ailab.svc.cluster.local/v1' `
  --from-literal=LLM_CHAT_API='api_v1_chat' `
  --from-literal=LLM_MODEL='openai/gpt-oss-120b' `
  --from-literal=CORS_ORIGINS='https://dwhcodereview.ailab.kuveytturk.com.tr'
```

## Doğrulama

Chart'ta değişiklik yaptıktan sonra render testlerini çalıştırın (repo kökünden):

```bash
bash helm/dwhcodereview/tests/render-test.sh
```

Test, Rancher'ın kullandığı yolu (yalnızca `values.yaml` + form değerleri),
guard'ların negatif davranışını ve paketleme çıktısını doğrular.

Tek seferlik render kontrolü:

```powershell
helm template dwhcodereview ./helm/dwhcodereview -f helm/dwhcodereview/values-test.yaml
```

## Notlar

- **Fail-fast:** `appConfig.mssqlConnectionString` ve `appConfig.apiAccessToken`
  boşsa `helm install/template` hata verir. `apiAccessToken`/`apiAdminToken`
  en az 16 karakter olmalıdır.
- **Tek Secret kaynağı:** `secrets.create=true` ile `secrets.existingSecret`
  birlikte kullanılamaz; `secrets.create=false` iken `existingSecret` zorunludur.
  Her iki hata da install anında durdurulur.
- **`appConfigFallback` (yalnızca CLI/pipeline):** helm'de `--set-string`,
  `-f` ile verilen dosyalardan daha yüksek önceliklidir. Bu yüzden **boş** bir
  `--set-string appConfig.apiAccessToken=`, `values-test.yaml`'daki geçerli
  değeri siler ve fail-fast guard'ını yanlış yere tetikler — CI sırrı script'e
  aktarılmadığında tam olarak bu olur (Azure DevOps secret değişkenleri, task'ın
  `env:` bloğunda tanımlı değilse boş gelir). `values-test.yaml` zorunlu sırları
  bu nedenle `appConfigFallback` altında tutar; ilgili `appConfig` alanı boş
  geldiğinde devreye girer, dolu bir `--set-string` yine önceliği alır.
  Rancher UI yalnızca kökteki `values.yaml`'ı yükler ve orada bu blok boştur,
  dolayısıyla UI'dan boş değer girildiğinde guard'lar aynen çalışır. Prod'a
  **eklemeyin**: prod sırları harici Secret'tan gelir.
- **SSE:** Canlı review akışı için Ingress annotation'larında
  `proxy-buffering: "off"` ve 3600 sn timeout tanımlıdır; Nginx ConfigMap'inde de
  `proxy_buffering off` korunur.
- **Kalıcılık:** `review_rules.json` ve LLM logları için backend `/app/data`
  PVC'ye bağlanır (`persistence.enabled`).
- **Frontend securityContext:** `nginx:alpine` master process root gerektirdiği
  için `frontend.podSecurityContext.runAsNonRoot=false` olarak override edilir.
