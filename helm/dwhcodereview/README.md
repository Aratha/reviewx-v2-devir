# DWH Code Review — Helm Chart

`backend` (FastAPI + pyodbc/ODBC Driver 18) ve `frontend` (Vite build → Nginx)
imajlarını Rancher/Kubernetes ortamına deploy eder.

## Yapı

```
helm/dwhcodereview/
├── Chart.yaml
├── values.yaml            # ortak varsayılanlar (fail-fast guard'lar burada)
├── values-test.yaml       # TEST override
├── values-prod.yaml       # PROD override (harici Secret)
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

## Kurulum (TEST)

```powershell
helm upgrade --install dwhcodereview ./helm/dwhcodereview `
  -n dwhcodereview --create-namespace `
  -f helm/dwhcodereview/values.yaml `
  -f helm/dwhcodereview/values-test.yaml `
  --set appConfig.mssqlConnectionString='DRIVER={ODBC Driver 18 for SQL Server};SERVER=<host>;DATABASE=master;UID=<user>;PWD=<pass>;TrustServerCertificate=yes' `
  --set appConfig.apiAccessToken='<en-az-16-karakter>' `
  --set appConfig.apiAdminToken='<en-az-16-karakter>'
```

Sonraki upgrade'lerde `--reuse-values` ile değerleri devralın.

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

```powershell
helm lint ./helm/dwhcodereview -f helm/dwhcodereview/values.yaml -f helm/dwhcodereview/values-test.yaml
helm template dwhcodereview ./helm/dwhcodereview -f helm/dwhcodereview/values.yaml -f helm/dwhcodereview/values-test.yaml
```

## Notlar

- **Fail-fast:** `appConfig.mssqlConnectionString` ve `appConfig.apiAccessToken`
  boşsa `helm install/template` hata verir. `apiAccessToken`/`apiAdminToken`
  en az 16 karakter olmalıdır.
- **SSE:** Canlı review akışı için Ingress annotation'larında
  `proxy-buffering: "off"` ve 3600 sn timeout tanımlıdır; Nginx ConfigMap'inde de
  `proxy_buffering off` korunur.
- **Kalıcılık:** `review_rules.json` ve LLM logları için backend `/app/data`
  PVC'ye bağlanır (`persistence.enabled`).
- **Frontend securityContext:** `nginx:alpine` master process root gerektirdiği
  için `frontend.podSecurityContext.runAsNonRoot=false` olarak override edilir.
