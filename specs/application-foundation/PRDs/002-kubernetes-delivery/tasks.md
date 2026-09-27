# Görevler — kubernetes-delivery

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-27'de yerel
Compose yığınında geçti (arka uç 620/620, ön yüz 130/130 test; göç, OpenAPI, üretilmiş tip,
yönetişim sapması ve proje katmanıyla chart adımı dahil) ve `tests/helm/deploy-hooks.test.sh` 39
denetimi geçti. Bu, chart, kanca ve arka uç için L1 (otomatik testlerden geçti) kanıtıdır. Canlı
küme kanıtı (Acceptance 3) yoktur.

- [x] Task 1 — Requirement 1, 2, 3, 4, 6, 8, 10 / Acceptance 1: fabrikanın proje dağıtım katmanı
  (`deploy.sh`, `values.yaml`, `templates/**`, `render_charts.py`, rules/22 ve rules/45) fabrika `main`
  `ce34a65` sürümünden alındı (Decision 7). Kanıt: `scripts/render-charts.sh`
  ("values-project.yaml: 12 resources; deploy-hooks.sh parses"),
  `helm/dwhcodereview/deploy.sh --render` (iş yükü adları kümedeki eski release'in adlarıyla aynı),
  `python3 scripts/check-governance-drift.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 2 — Requirement 5, Decision 14, 17 / Acceptance 1: `helm/dwhcodereview/deploy-hooks.sh`
  runtime Secret'ı hazırlar. Kanıt: `tests/helm/deploy-hooks.test.sh` (anahtar bir kez üretilir ve
  korunur, isteğe bağlı değişkenler varken yazılır yokken korunur, `$(...)` verilmemiş sayılır,
  okunamayan Secret ve geçersiz anahtarda durur, değer argümana ve loga düşmez, gereksiz yeniden
  başlatma yok); iki bilinçli bozmada (değeri yazdırma, her koşuda yazma) test kırmızıya döndü.
- [x] Task 3 — Requirement 2, 5, 8, 10, Decision 9, 11 / Acceptance 1:
  `helm/dwhcodereview/values-project.yaml` (ingress, runtime Secret adı, 10Gi `nfs-sc`, çıkış eşleri,
  sır olmayan `staging` ayarları). Kanıt: `scripts/render-charts.sh`.
- [x] Task 4 — Requirement 9 / Acceptance 1: dizin CA dosyası yayın imajına
  `/workspace/app/backend/certs/nonprod-directory-ca.crt` yolunda girer; `image-build.yml`'ın
  yayımladığı `ghcr.io/kt-vibecoding/dwhcodereview-{backend,frontend}` adları (sahip adı küçük harfe
  çevrilir; depo adı `DWHCodeReview` imaj adında yoktur) değer dosyasındaki
  `cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/` yollarıyla ve kümede çalışan eski imajların
  yoluyla aynıdır. Kanıt: yerel `docker build -f app/infra/Dockerfile.backend.release` ve Task 5.
- [x] Task 5 — Requirement 5, Decision 17 / Acceptance 1: `nonprod`'da SQL Server hesabı olmadan
  başlama ([sql-server-connection](../../../sql-review/PRDs/002-sql-server-connection/PRD.md) Task 1).
  2026-09-27 yerel gözlem (L2 değil; küme değil): yayın backend imajı `values-project.yaml`'daki
  `staging` ayarlarıyla, salt okunur kök dosya sistemiyle, kök olmayan kullanıcıyla ve yalnız DML
  yetkili uygulama rolüyle ayrı bir iç ağda açıldı; chart'ın `runtime-role` betiği ve
  `alembic upgrade head` uygulandı; hazır olma yoklaması 200, uygulama rolü tablo oluşturamadı,
  süper yönetici uygulama rolüyle oluşturulup giriş yaptı, `GET /sql-connection`
  `configured: false`, `GET /databases` 503 `sql_connection_not_configured`,
  `POST /sql-connection/test` 404; logda parola ve anahtar yoktu.
- [ ] Task 6 — Requirement 11, 12 / Acceptance 2: yerel Compose'da tarayıcıyla giriş ve kural
  ekranı, içe aktarılan kuralların depodaki kopyayla eşleşmesi bu revizyonda yeniden gözlenmedi.
- [ ] Task 7 — Requirement 4: backend hazır olma yoklaması bugün yalnız veritabanı bağlantısına
  bakar; şema imajın beklediği sürüme gelene kadar 503 dönmez. İlk kurulumda göç bitene kadar yeni
  backend kısa süre şemasız istek alabilir.
- [ ] Task 8 — Requirement 1: chart sürümü fabrikanın yönettiği `Chart.yaml`'da `0.1.0`'dır, eski
  chart'ın `0.2.0` sürümünden büyük değildir. Helm güncellemesi buna bağlı değildir; karar sahibe
  ve fabrikaya aittir.
- [ ] Task 9 — Requirement 12 / Acceptance 3: güncellemeden sonra PostgreSQL'deki kural sayısı ve
  içerik özetinin depodaki kopyayla karşılaştırılması.
- [ ] Task 10 — Acceptance 3: PR #14 birleşip GitHub imajları yayımladıktan sonra kullanıcının
  tetiklediği argümansız Azure koşumu ve kümede doğrulama.
- [ ] Task 11 — Acceptance 4, Requirement 13: sahibin izniyle `helm rollback` provası.
- [ ] Task 12 — Requirement 7, Decision 13: yeni sürüm sağlıklı açıldıktan sonra eski PVC
  `dwhcodereview-backend-data`, eski Secret anahtarları ve eski Azure değişkenleri sahip tarafından
  elle silinir.
- [ ] Task 13 — Decision 11: işletim ekibi SQL Server adresini verince `values-project.yaml`'a
  sunucu ve izinli veritabanı listesi yazılır ve çıkış `/32`'ye daraltılır.
