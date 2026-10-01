# Plan — sql-server-connection

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.4.0). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uç ve `sqlalchemy-alembic` kalıcılığıdır. Bu PRD PostgreSQL'e
`sql_connection_setting` tablosunu ekler.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Ayarlar | `app/backend/app/core/config.py` (`DWHCODEREVIEW_MSSQL_*`), `app/backend/.env.example`, `app/infra/docker-compose.local.yml` | Requirement 1 |
| Başlangıç denetimi | `app/backend/app/services/startup_checks.py`, `app/backend/app/main.py` (uygulama yaşam döngüsü) | Requirement 1, Decision 5, 6, 10, 11 |
| Port | `app/backend/app/domain/sql_server.py` (`SqlCatalogPort`, `SqlConnectionProbe`, hata sınıfları, sabit Türkçe iletiler) | Decision 2, Requirement 8 |
| Bağlantı dizesi | `app/backend/app/infrastructure/sql_server/connection_string.py` | Requirement 2, Decision 1 |
| Sorgular | `app/backend/app/infrastructure/sql_server/queries.py`, `dependency_metadata.py` (kaynaktaki `db/queries.py` ve `services/dependency_metadata.py`) | Requirement 7 |
| Uyarlayıcı | `app/backend/app/infrastructure/sql_server/catalog_adapter.py` | Requirement 6, 7, 8 |
| Hizmet | `app/backend/app/services/sql_connection_service.py` (durum seçimi, süreç içi depo, `StoredSqlConnection`) | Requirement 3, 4, 5, 10, 11, Decision 3, 8, 12, 14 |
| Şifreleme | `app/backend/app/core/secret_cipher.py` | Requirement 10, Decision 13 |
| Şema ve göç | `app/backend/app/domain/models/sql_connection.py`, `schema/alembic/versions/202610010001_sql_connection_setting.py`, `schema/alembic/versions/202610010002_sql_connection_all_databases_and_certificate_option.py` | Requirement 10, Veri ve geçiş |
| Depo | `app/backend/app/infrastructure/repositories/sql_connection_setting_repository.py` | Requirement 10, 11 |
| API | `app/backend/app/api/sql_connection/router.py`, `app/backend/app/api/route_classes.py`, `app/backend/app/api/router.py` (`local_environment_router`, `stored_sql_connection_router`), `app/backend/app/api/integrations.py`, `app/backend/app/main.py`, `app/backend/app/schemas/sql_connection/contracts.py` | API sözleşmesi, Requirement 5, 11 |
| Dağıtım kancası | `helm/dwhcodereview/deploy-hooks.sh`, `tests/helm/deploy-hooks.test.sh` | Decision 13 |
| İmaj | `app/infra/locks/backend-alpine-packages.lock`, `app/infra/locks/msodbcsql18-alpine-packages.lock`, `app/infra/install-backend-system-packages.sh`, `app/backend/Dockerfile.dev`, `app/infra/Dockerfile.backend.release` | Dağıtım etkisi, Decision 4, 6 |
| Bağımlılık | `app/backend/requirements.in` (`pyodbc==5.3.0`), kilitli `requirements*.txt`, `dependency-admission.json` | Decision 4 |
| Gözlemlenebilirlik | `app/backend/app/infrastructure/sql_server/catalog_adapter.py` (`sql_server_call`), `app/backend/app/core/telemetry.py` | Gözlemlenebilirlik |
| Ön yüz | `app/frontend/src/pages/SqlConnectionPage.tsx`, `app/frontend/src/hooks/useConnectionMenu.ts`, `app/frontend/src/services/connections.ts`, `app/frontend/src/lib/connectionText.ts`, `app/frontend/src/lib/errorMessages.ts` | Requirement 5, 9 |

## Uygulama kararları

- Bağlantı dizesi yalnız `build_connection_string` ile `ODBC Driver 18 for SQL Server` için
  üretilir: `Database`, `UID`, `PWD` süslü parantez içinde, kapanış parantezi ikilenerek yazılır.
  Sunucu yalnız ana makine adı, IPv4, köşeli parantezli IPv6 veya `ad\örnek` biçimini kabul eder;
  denetim karakteri, `;`, `=`, `{`, `}` veya boşluk içeren sunucu ve denetim karakteri içeren
  kullanıcı 422 `sql_connection_invalid` alır ve başlangıçta süreci durdurur.
- Her sürücü çağrısı `DWHCODEREVIEW_MSSQL_MAX_CONCURRENCY` iş parçacıklı havuzda koşar; bağlantı
  `autocommit` açık, giriş süresi ayardan (bağlantı testinde sabit 15 sn) ve sorgu süresi
  `connection.timeout` ile ayardandır.
- SQLSTATE eşlemesi sürücü iletisindeki ek `[XXXXX]` kayıtlarını da değerlendirir: `08001`/`08S01`
  ile SSL/sertifika belirtisi `sql_tls_failed`, `28000` `sql_login_failed`, `08001`/`08S01`
  `sql_server_unreachable`, `HYT00`/`HYT01` `sql_timeout`, diğerleri `sql_query_failed`. Sürücü
  metni yalnız sınıflandırmada kullanılır; kullanıcıya, loga ve istisna zincirine geçmez.
- Veritabanı listesi `LIST_DATABASES_SQL` ile gelir (`state = 0` ve `HAS_DBACCESS(name) = 1`);
  uyarlayıcı sonuçtan sistem veritabanlarını çıkarır. Sistem veritabanı denetimi (`is_system_database`,
  büyük/küçük harf duyarsız) her işlemden önce, bağlantı açılmadan uygulanır (`DatabaseNotAllowed`;
  403 eşlemesi uçların sahibi olan nesne incelemesi PRD'sindedir). Uyarlayıcı her çağrıda önce
  bağlantıyı denetler; yapılandırılmamış bağlantıda çağrı 503 `sql_connection_not_configured` alır
  (Decision 11). Listeyi daraltan bir ayar, kayıt veya süzgeç yoktur (Decision 5).
- Nesne meta verisi kaynaktaki genişlik öncelikli taramayı korur (derinlik 4, en çok 48 veritabanı
  taraması, 95.000 karakter kesme, iç hataların atlanması); çapraz veritabanı çözümü yalnız
  veritabanı listesindeki veritabanlarında arar ve yerelde bulunamayan her adı bir istekte yalnız bir
  kez tarar (toplayıcı sonucu istek boyunca saklar). 48 nesne sınırı kaynakta yalnız kuyruk adımları arasında
  denetleniyordu; burada kesin sınırdır. Kök veritabanı bağlantısı açılamazsa sınıflı hata döner,
  sonraki hatalar yalnız tipleriyle `debug` düzeyinde loglanıp atlanır.
- Yürürlükteki bağlantı (`SqlServerConnectionConfig`; sertifikaya güven seçeneği dahil) süreç içi
  `SqlConnectionStore`'da durur; uyarlayıcı her işlemde bu değeri bir kez okur (Requirement 11).
- Durum, `sql_connection_mode` ile ayarlardan seçilir: `local`; `nonprod`'da dağıtım tam bağlantı
  veriyorsa ya da anahtar yoksa `deployment`; aksi hâlde `stored` (Requirement 5).
- `local`'de ayar değişikliği yalnız süreç içi depodadır; dosyaya ve süreç ortamına yazılmaz. Test,
  sunucu/port/kullanıcı kayıtlı değerden farklıysa ve formda parola yoksa kayıtlı parolayı göndermez
  (`password_required`).
- `stored` durumunda `StoredSqlConnection` kaydı kendi kısa işlemiyle yazar: kaydeden hesabı ve
  süper yönetici rolünü veritabanından yeniden okur, kiracının satırını kilitler (`SELECT … FOR
  UPDATE`), değişikliği doğrular, parolayı şifreler, yazar ve ancak işlem tamamlandıktan sonra süreç
  içi depoyu günceller. Reddedilen değişiklik hiçbir şey yazmaz. Kayıt tek platform kiracısının
  satırıdır ([directory-login](../../../application-foundation/PRDs/001-directory-login/PRD.md)
  Decision 6).
- Kopyalar arası güncellik: FastAPI bağımlılığı `get_sql_catalog` ve bağlantı sayfasının okuma ucu,
  `stored` durumunda her istekte `StoredSqlConnection.refresh()` ile satırı yeniden okuyup depoya
  koyar (Decision 14). Okuma hatası son değeri korur ve `sql_connection.refresh_failed` olayını
  yazar.
- Şifreleme `SecretCipher`'dadır: AES-256-GCM, değer başına `os.urandom` ile 96 bit nonce, ek
  doğrulanan veri olarak `sql-connection-password:<kiracı public_id>`; saklanan biçim
  `v1.<nonce>.<şifreli değer ve doğrulama etiketi>` (URL güvenli base64). Yanlış anahtar, başka
  bağlam ve değiştirilmiş değer aynı içeriksiz hatayı verir. Anahtar ayarı tipli ayarlarda
  doğrulanır; hata iletisi değeri yankılamaz.
- Yazma ve test uçları iki ayrı yönlendiricide aynı işlevlerdir: `local_router` (`kural-yoneticisi`)
  yalnız `local`'de, `stored_router` (süper yönetici) yalnız `stored` durumunda uygulamaya eklenir;
  `deployment` durumunda hiçbiri eklenmez ve `MethodScopedRoute` aynı yoldaki GET ucunun 405 yerine
  404 üretmesini sağlar. Hizmet aynı denetimleri yineler. Başlangıç denetimi `nonprod`'da
  `ENCRYPT=false` görürse süreci ayar adıyla (değer olmadan) durdurur; `TRUST_SERVER_CERTIFICATE=true`
  Decision 6 istisnası gereği süreci durdurmaz.
- Sertifikaya güven seçeneği `stored` durumunda satırın `trust_server_certificate` sütununda durur
  ve süper yönetici tarafından değiştirilir; `encrypt` o durumda her zaman `true`'dur ve `false`
  isteği 422 `sql_setting_fixed` alır.
- OpenAPI dışa aktarımı uygulamayı `local` olarak kurar; yazma ve test uçları sözleşmede bir kez,
  iki ortamın rol ve hata açıklamalarıyla yer alır.
- Log olayları: her işlem için bir `sql_server.call` (`operation`, `database`, `outcome`,
  `sqlstate`, `duration_ms`, `rows`; `request_id` biçimleyiciden gelir), `sql_connection.updated`
  (değişen alan adları, `managed_by`, `trust_server_certificate`, kullanıcı `public_id`), `sql_connection.stored_unusable`
  (neden), `sql_connection.refresh_failed` (hata türü) ve `startup.sql_connection_mode` (durum).
- İmaj: Alpine v3.23 `unixodbc` ve sürücünün çalışma zamanı paketleri ile Microsoft `msodbcsql18`
  18.6.2.1-1 kilit dosyalarından SHA-256 denetimiyle ve ağsız `apk` ile kurulur; Microsoft paketinin
  imzası kabul sırasında Microsoft yayın anahtarıyla doğrulandı. Kurum kök CA'sı sistem güven
  deposuna eklenir. Çevrimdışı kipte aynı dosyalar `system_packages` yapı bağlamından alınır.

## Dağıtım bağımlılığı

Runtime Secret anahtarları (`helm/dwhcodereview/deploy-hooks.sh`; ayar şifreleme anahtarı dahil),
sır olmayan değerlerin `helm/dwhcodereview/values-project.yaml` ile chart'a taşınması ve SQL Server
ağ çıkış kuralı
[Kubernetes teslim PRD'sinindir](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md).
Değer katmanında SQL Server adresi yoktur; bağlantıyı süper yönetici girer
(Decision 11, 12). Yeni tablo mevcut göç Job'uyla kurulur; ayrı dağıtım adımı gerekmez.

## Doğrulama komutları

- `python3 scripts/check-config-sync.py`, `python3 scripts/check-dependency-admission.py`
- `scripts/quality-gate.sh backend` ve devir için `scripts/quality-gate.sh all`
- `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`
- `scripts/db.sh validate` (şema ile göç geçmişinin uyumu), `tests/helm/deploy-hooks.test.sh`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 1 | Acceptance 1, Acceptance 5 | Task V1, Task 1 |
| Requirement 2, 8 | Acceptance 1 | Task 2 |
| Requirement 3, 4, 5 | Acceptance 1, Acceptance 3 | Task 4, Task 5, Task 11 |
| Requirement 10 | Acceptance 1, Acceptance 5 | Task 10, Task 11, Task 13 |
| Requirement 11 | Acceptance 1, Acceptance 5 | Task 3, Task 11 |
| Requirement 6 | Acceptance 2 | Task 3 |
| Requirement 7 | Acceptance 1 | Task 3 |
| Requirement 5, 9 | Acceptance 3, Acceptance 4, Acceptance 5 | Task 8, Task 9, Task 12 |
| Gözlemlenebilirlik (ölçümler) | — | Task 7 |
| Dağıtım etkisi (imaj, bağımlılık) | Acceptance 1 | Task 6 |
| Dağıtım etkisi (Secret anahtarı, Decision 13) | Acceptance 1 | Task 13 |
