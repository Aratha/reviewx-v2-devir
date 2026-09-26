# Plan — sql-server-connection

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.0.0). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uçtur. Bu PRD PostgreSQL'e tablo eklemez.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Ayarlar | `app/backend/app/core/config.py` (`DWHCODEREVIEW_MSSQL_*`), `app/backend/.env.example`, `app/infra/docker-compose.local.yml` | Requirement 1 |
| Başlangıç denetimi | `app/backend/app/services/startup_checks.py`, `app/backend/app/main.py` (uygulama yaşam döngüsü) | Requirement 1, Decision 5, 6, 10 |
| Port | `app/backend/app/domain/sql_server.py` (`SqlCatalogPort`, `SqlConnectionProbe`, hata sınıfları, sabit Türkçe iletiler) | Decision 2, Requirement 8 |
| Bağlantı dizesi | `app/backend/app/infrastructure/sql_server/connection_string.py` | Requirement 2, Decision 1 |
| Sorgular | `app/backend/app/infrastructure/sql_server/queries.py`, `dependency_metadata.py` (kaynaktaki `db/queries.py` ve `services/dependency_metadata.py`) | Requirement 7 |
| Uyarlayıcı | `app/backend/app/infrastructure/sql_server/catalog_adapter.py` | Requirement 6, 7, 8 |
| Hizmet | `app/backend/app/services/sql_connection_service.py` | Requirement 3, 4, 5, Decision 3, 8 |
| API | `app/backend/app/api/sql_connection/router.py`, `app/backend/app/api/route_classes.py`, `app/backend/app/api/router.py` (`local_environment_router`), `app/backend/app/api/integrations.py`, `app/backend/app/schemas/sql_connection/contracts.py` | API sözleşmesi, Requirement 5 |
| İmaj | `app/infra/locks/backend-alpine-packages.lock`, `app/infra/locks/msodbcsql18-alpine-packages.lock`, `app/infra/install-backend-system-packages.sh`, `app/backend/Dockerfile.dev`, `app/infra/Dockerfile.backend.release` | Dağıtım etkisi, Decision 4, 6 |
| Bağımlılık | `app/backend/requirements.in` (`pyodbc==5.3.0`), kilitli `requirements*.txt`, `dependency-admission.json` | Decision 4 |
| Ön yüz | SQL bağlantısı sayfası | Requirement 5, 9 |

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
- İzin listesi büyük/küçük harf duyarsızdır ve her işlemden önce, bağlantı açılmadan uygulanır
  (`DatabaseNotAllowed`; 403 eşlemesi uçların sahibi olan nesne incelemesi PRD'sindedir). Boş liste
  yalnız `local`'de olabilir ve bütün çevrimiçi veritabanları demektir.
- Nesne meta verisi kaynaktaki genişlik öncelikli taramayı korur (derinlik 4, en çok 48 veritabanı
  taraması, 95.000 karakter kesme, iç hataların atlanması); çapraz veritabanı çözümü yalnız izinli
  ve çevrimiçi veritabanlarında arar. 48 nesne sınırı kaynakta yalnız kuyruk adımları arasında
  denetleniyordu; burada kesin sınırdır. Kök veritabanı bağlantısı açılamazsa sınıflı hata döner,
  sonraki hatalar yalnız tipleriyle `debug` düzeyinde loglanıp atlanır.
- `local`'de ayar değişikliği süreç içi `SqlConnectionStore`'dadır; dosyaya ve süreç ortamına
  yazılmaz. Test, sunucu/port/kullanıcı kayıtlı değerden farklıysa ve formda parola yoksa kayıtlı
  parolayı göndermez (`password_required`).
- `nonprod`'da yazma ve test uçları yönlendiriciye eklenmez; `MethodScopedRoute` aynı yoldaki GET
  ucunun 405 yerine 404 üretmesini sağlar. Başlangıç denetimi `nonprod`'da eksik sunucu, kullanıcı,
  parola, izin listesi, izin listesinde sistem veritabanı, `ENCRYPT=false` veya
  `TRUST_SERVER_CERTIFICATE=true` görürse süreci ayar adlarıyla (değer olmadan) durdurur.
- Log olayları: her işlem için bir `sql_server.call` (`operation`, `database`, `outcome`,
  `sqlstate`, `duration_ms`, `rows`; `request_id` biçimleyiciden gelir) ve `sql_connection.updated`
  (değişen alan adları, kullanıcı `public_id`).
- İmaj: Alpine v3.23 `unixodbc` ve sürücünün çalışma zamanı paketleri ile Microsoft `msodbcsql18`
  18.6.2.1-1 kilit dosyalarından SHA-256 denetimiyle ve ağsız `apk` ile kurulur; Microsoft paketinin
  imzası kabul sırasında Microsoft yayın anahtarıyla doğrulandı. Kurum kök CA'sı sistem güven
  deposuna eklenir. Çevrimdışı kipte aynı dosyalar `system_packages` yapı bağlamından alınır.

## Dağıtım bağımlılığı

Runtime Secret anahtarları, sır olmayan değerlerin chart'a taşınması ve tek adresli ağ çıkış
kuralı [Kubernetes teslim PRD'sinindir](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md);
bu teslimde `helm/` değişmedi.

## Doğrulama komutları

- `python3 scripts/check-config-sync.py`, `python3 scripts/check-dependency-admission.py`
- `scripts/quality-gate.sh backend` ve devir için `scripts/quality-gate.sh all`
- `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 1 | Acceptance 1, Acceptance 5 | Task V1, Task 1 |
| Requirement 2, 8 | Acceptance 1 | Task 2 |
| Requirement 3, 4, 5 | Acceptance 1, Acceptance 3 | Task 4, Task 5 |
| Requirement 6 | Acceptance 2 | Task 3 |
| Requirement 7 | Acceptance 1 | Task 3 |
| Requirement 9 | Acceptance 3, Acceptance 4 | Task 8 |
| Gözlemlenebilirlik (ölçümler) | — | Task 7 |
| Dağıtım etkisi (imaj, bağımlılık) | Acceptance 1 | Task 6 |
