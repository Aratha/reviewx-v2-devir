# Görevler — kubernetes-delivery

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-10-01'de yerel
Compose yığınında geçti (arka uç 723/723, ön yüz 138/138 test; göç, OpenAPI, üretilmiş tip,
yönetişim sapması ve proje katmanıyla chart adımı dahil), `tests/helm/deploy-hooks.test.sh` 70 ve
`tests/infra/local-egress.test.sh` 22 denetimi geçti. Bu, chart, kanca, yerel Compose ve arka uç
için L1 (otomatik testlerden geçti) kanıtıdır. Canlı küme kanıtı (Acceptance 3) yoktur.

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
  Süper yönetici başlangıç parolası `DWHCODEREVIEW_ADMIN_PASSWORD` aynı testte sınanır: verilince
  `DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD` anahtarına dosyayla yazılır, yokken kümedeki değer
  korunur ve yeniden yazılmaz, `$(...)` saklanmaz, değer çıktıya ve argümana düşmez; değeri log
  satırına ekleyen ve değişken adını değiştiren iki bilinçli bozmada test kırmızıya döndü.
  Ayar şifreleme anahtarı (Decision 20) aynı testte sınanır: ilk koşuda 32 baytlık anahtar üretilir,
  sonraki koşularda ve kimlik bilgisi değişiminde korunur, `SETTINGS_ENCRYPTION_KEY` verilince o
  yazılır, `$(...)` kümedeki anahtarı korur, biçimsiz değer hiçbir şey yazmadan durdurur, değer
  çıktıya ve argümana düşmez.
- [x] Task 3 — Requirement 2, 5, 8, 10, Decision 9, 11 / Acceptance 1:
  `helm/dwhcodereview/values-project.yaml` (ingress, runtime Secret adı, 10Gi `nfs-sc`, çıkış eşleri,
  sır olmayan `staging` ayarları, süper yönetici hesap adı `admin`). Kanıt: `scripts/render-charts.sh`.
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
- [x] Task 7 — Requirement 4 / Acceptance 1: backend hazır olma yoklaması şemaya duyarlıdır
  (`app/backend/app/db/readiness.py`; fabrika `main` `73aa97f` ile aynı davranış). Kanıt:
  `tests/unit/test_readiness.py` ve `tests/integration/test_readiness_postgres.py` (PRD Test
  stratejisi) `scripts/quality-gate.sh all` içinde geçti. 2026-09-27 yerel ilk kurulum provası
  (yerel yığının PostgreSQL'i; küme değil): boş veritabanı ve henüz oluşmamış uygulama rolüyle açılan
  backend yoklamaya 503 verdi (tek `readiness.not_ready` olayı, `InvalidPasswordError`), rol oluşup
  şema yokken yine 503 (`schema_behind`), `alembic upgrade head` sonrası 200; logda hata izi, 500
  yanıtı ve parola yoktu. Aynı prova önceki kodla rol yokken 500 ve hata izi, şema yokken 200
  verdi. Kümedeki davranış bir sonraki Azure koşumunda gözlenir.
- [x] Task 8 — Requirement 1, Decision 19 / Acceptance 1: chart sürümü fabrikanın yönettiği
  `Chart.yaml`'daki `0.1.0`'dır. Kanıt: Task 10'daki `acc1150` koşumu nonprod'daki `0.2.0`
  release'ini bu chart'la aynı release'te sorunsuz güncelledi; PRD bu gözleme hizalandı, yönetilen
  dosya değişmedi.
- [ ] Task 9 — Requirement 12 / Acceptance 3: güncellemeden sonra PostgreSQL'deki kural sayısı ve
  içerik özetinin depodaki kopyayla karşılaştırılması.
- [x] Task 10 — Acceptance 3: Azure koşumu her `main` birleştirmesinde kendiliğinden, argümansız
  çalıştı (2026-09-27: `acc1150` eski sürümü güncelledi; `4c9e903` ve `9722faf` sıradan güncelleme).
  Kümede gözlendi: veritabanı StatefulSet'i 10Gi `nfs-sc` diskle hazır; ilk kurulumda `migration-init`,
  sonraki koşumlarda `pre-upgrade` geçiş işi tamamlandı; backend hazır olma yoklaması 200, ön yüz
  200, dizin girişi yanlış bilgide 401 `invalid_credentials`. İlk kurulumda geçiş bitene kadar
  (yaklaşık bir dakika) backend istekleri veritabanı rolü henüz yokken hata aldı; Task 7'deki
  şemaya duyarlı hazır olma bunu önler.
- [x] Task 12 — Requirement 7, Decision 13: eski PVC `dwhcodereview-backend-data`, yeni sürüm
  sağlıklı açıldıktan sonra Azure koşumunda (`9722faf`, 2026-09-27) tek seferlik kanca adımıyla
  silindi; kümede PVC'nin kalmadığı gözlendi ve adım kancadan ve testinden kaldırıldı.
- [ ] Task 13 — Decision 11: SQL Server adresi belli olunca `values-project.yaml`'daki çıkış kuralı
  `/32`'ye daraltılır. Sunucu, hesap ve izinli veritabanı listesi değer katmanına yazılmaz; süper
  yönetici uygulamadan girer
  ([sql-server-connection](../../../sql-review/PRDs/002-sql-server-connection/PRD.md) Decision 12).
- [ ] Task 14 — Decision 13: eski Secret anahtarları ve eski Azure değişkenleri sahip tarafından
  elle silinir.
- [x] Task 15 — Requirement 11, Decision 15 / Acceptance 2: yerelde SQL Server ve LLM erişimi ayrıca
  seçilen `local-egress` Compose profilidir; Git'in yok saydığı `app/infra/.env` içindeki
  `COMPOSE_PROFILES=local-egress` satırı açar, varsayılan kapalıdır ([plan](plan.md),
  [yerel kurulum](../../../../docs/tr/yerel-kurulum.md)). Kanıt (L1): `tests/infra/local-egress.test.sh`
  22 denetimi geçti (profil kapalıyken geçit ve dışa çıkan ağ yok, backend yalnız iç ağlarda;
  açıkken dışa çıkan köprüde yalnız geçit, `host-gate`'te yalnız backend ve geçit, geçit port
  yayımlamaz, salt okunur, kök olmayan kullanıcıyla ve yeteneksiz çalışır, yalnız 1433, 11434 ve
  1234'ü aynı portla `host.docker.internal`'a aktarır, yapılandırması sabit imajda geçerlidir); beş
  bilinçli bozmada (backend'i dışa çıkan ağa ekleme, profili silme, `host-gate`'i iç ağ olmaktan
  çıkarma, başka hedefe aktarma, başlat görevinden temizliği silme) test kırmızıya döndü.
  `app/backend/tests/unit/test_llm_connection_service.py`: geçidin adı iç ağ adresine çözülünce LLM
  adresi kaydedilir; profil kapalıyken (ad çözülmez) ve ad genel adrese çözülürse
  `network_policy_denied`, `nonprod`'da 404; ada istisna tanıyan bilinçli bozmada iki test kırmızıya
  döndü. LLM ağ politikası değişmedi: kapalı durumdaki `network_policy_denied`, adın iç ağda
  çözülememesinden geliyordu. 2026-09-27 yerel gözlem (L2 yerel, küme değil; ayrı Compose
  projesiyle, tarayıcı değil API üzerinden): KT Verim'in yerel SQL Server kapsayıcısı
  (`kt-console-mssql`, ana makine portu 1433, salt okunur hesap) ve ana makinedeki Ollama
  `qwen3.6:35b` çalışırken, profil kapalıyken backend `host.docker.internal` adını çözemedi;
  `POST /sql-connection/test` `sql_server_unreachable`, `GET /databases` 503
  `sql_server_unreachable`, `PUT /llm-connection` 422 `network_policy_denied` döndü; bir metin
  incelemesinde 11 kural `UNKNOWN` ve 11 LLM çağrı özeti `connect_error` oldu. Profil VS Code başlat
  göreviyle açılınca bağlantı testi 11 veritabanıyla başarılı oldu, `PUT /llm-connection` 200 döndü;
  `EDWUTIL` içindeki küçük bir saklı yordamın Nesne incelemesi tanımı ve meta veriyi SQL Server'dan
  aldı, 11 kural `qwen3.6:35b` ile değerlendirildi (11 `ok` özet, canlı ilerleme olayları, 107 sn).
  Açıkken backend yalnız bu üç porta ulaştı; ana makinenin başka portu, internet adı ve genel IP
  kapalı kaldı; ön yüz, nginx ve PostgreSQL `host.docker.internal` adını çözemedi. Ayar kaldırılıp
  başlat görevi yeniden çalıştırılınca geçit kaldırıldı ve kapalı durumun sonuçları aynen döndü.
  Kurum ağındaki bir SQL Server'a veya RunAI ucuna yerelden erişim bu profilin kapsamında değildir.
