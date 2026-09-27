# Plan — kubernetes-delivery

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.3.1). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uç ve `sqlalchemy-alembic` kalıcılığıdır.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Chart (fabrikanın yönettiği) | `helm/dwhcodereview/Chart.yaml`, `values.yaml`, `templates/**` | Requirement 1, 2, 3, 4, 6, 8 |
| Dağıtım betiği (fabrikanın yönettiği) | `helm/dwhcodereview/deploy.sh` | Requirement 6, 10, Decision 4 |
| Proje değer katmanı | `helm/dwhcodereview/values-project.yaml` | Requirement 2, 5, 8, 10, Decision 9, 11, 17 |
| Proje kancası | `helm/dwhcodereview/deploy-hooks.sh` | Requirement 5, Decision 14, 17 |
| Kanca testi | `tests/helm/deploy-hooks.test.sh` | Requirement 5 |
| Chart denetimi (fabrikanın yönettiği) | `scripts/render_charts.py`, `scripts/render-charts.sh` | Requirement 1, 8 |
| Yayın imajı | `app/infra/Dockerfile.backend.release` (dizin CA dosyası), `.github/workflows/image-build.yml` | Requirement 9 |
| Başlangıç denetimi | `app/backend/app/services/startup_checks.py` ([sql-server-connection](../../../sql-review/PRDs/002-sql-server-connection/PRD.md) Decision 11) | Requirement 5, Decision 17 |
| Göç | `schema/alembic/versions/*` (içe aktarım göçü `202609260002`) | Requirement 4, 12 |

## Uygulama kararları

- Fabrikanın proje dağıtım katmanı fabrika `main` `ce34a65` sürümünden alındı: aynı yanıtlarla
  (`.kt-scaffold/answers.yml`) o sürümün ağacından ve projenin önceki fabrika sürümünden (`28811ac`)
  taze iskelet üretildi; ikisi arasında değişen yönetilen dosyalar kopyalandı,
  ekibin düzenlediği `README.md`, `app/backend/.env.example` ve `app/backend/app/core/config.py`'ye
  aynı fark elle uygulandı ve `.kt-scaffold/manifest.json` özetleri yeni sürüme çekildi.
- Kanca Secret'ı `kubectl create secret generic --dry-run=client | kubectl apply` ile yazar; yalnız
  yönettiği beş anahtarı gönderir, böylece eski öneksiz anahtarlar (Decision 13) silinmez. Kümedeki
  değer yalnız bu beş anahtar için okunur. Süper yönetici başlangıç parolası
  (`DWHCODEREVIEW_ADMIN_PASSWORD` → `DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD`) diğer isteğe
  bağlı değişkenlerle aynı kuralla işlenir; kanca parola politikasını denetlemez, politikanın sahibi
  backend'dir ([directory-login](../001-directory-login/PRD.md) Requirement 14).
- Kanca, Secret değiştiğinde yalnız kümede aynı imaj etiketiyle çalışan backend'i yeniden başlatır;
  yeni etiket geliyorsa pod şablonu zaten değişir ve yeniden başlatmayı Helm yapar.
- Güvenilen ingress ağı, ingress denetleyicisi podlarının 2026-09-27'de salt okunur gözlenen pod
  ağıdır (`10.42.x.x`, RKE2 varsayılanı `10.42.0.0/16`); backend'e girişi NetworkPolicy yalnız
  `kube-system`'e açtığı için bu ağdan başka istemci `X-Forwarded-For` gönderemez.
- Uygulama rolü chart'ın göç Job'undaki `runtime-role` hazırlık kapsayıcısıyla oluşur; yerel
  Compose tek `app` rolüyle çalışır.

## Göç ve dağıtım bağımlılığı

Göçler yalnız genişleticidir (Requirement 4). İlk kurulumda göç Job'u veritabanıyla aynı adımda
oluşur; sonraki güncellemelerde `pre-upgrade` kancasıdır. Dağıtım GitHub'ın imajları yayımlamasına
ve PR #14'ün `main`'e birleşmesine bağlıdır; Azure işini kullanıcı tetikler.

## Doğrulama komutları

- `tests/helm/deploy-hooks.test.sh`
- `scripts/render-charts.sh` (kurulu `kt-iskelet` gerekir) ve
  `IMAGE_TAG=<etiket> helm/dwhcodereview/deploy.sh --render`
- `python3 scripts/check-config-sync.py`, `python3 scripts/check-governance-drift.py`
- `scripts/quality-gate.sh all`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 1, 2, 3, 6, 8, 10 | Acceptance 1, Acceptance 3 | Task 1, Task 3 |
| Requirement 1 (chart sürümü) | Acceptance 1 | Task 8 |
| Requirement 4 | Acceptance 1, Acceptance 3 | Task 1, Task 7 |
| Requirement 5 | Acceptance 1, Acceptance 3 | Task 2, Task 3, Task 5 |
| Requirement 7, 13 | Acceptance 3, Acceptance 4 | Task 11, Task 12 |
| Requirement 9 | Acceptance 3 | Task 4 |
| Requirement 11, 12 | Acceptance 2 | Task 6, Task 9 |
| Decision 7 | — | Task 1 |
| Decision 11 | Acceptance 3 | Task 13 |
