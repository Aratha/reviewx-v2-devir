# Görevler — sql-server-connection

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-10-01'de yerel
Compose yığınında geçti (arka uç 717/717, ön yüz 136/136 test; göç, OpenAPI, üretilmiş tip,
yönetişim sapması ve proje katmanıyla chart adımı dahil) ve `tests/helm/deploy-hooks.test.sh` 70
denetimi geçti. Bu, L1 (otomatik testlerden geçti) kanıtıdır. Gerçek bir SQL Server'a karşı yapılan
yerel gözlem Task 9'dadır; `nonprod` tarayıcı gözlemi (Acceptance 5) açıktır.

- [x] Task V1 — Requirement 1 / Acceptance 1: tipli ayar alanları ve aralık doğrulaması. Kanıt:
  `app/backend/tests/unit/test_config.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 1 — Requirement 1, Decision 5, 6, 10, 11 / Acceptance 1: başlangıç denetimi (`nonprod`'da
  şifreleme kapalıyken durma; sertifikaya güven açıkken ve veritabanı listesi ayarı olmadan başlama;
  her ortamda biçimsiz sunucu/kullanıcı) ve eksik bağlantıda "yapılandırılmamış" olarak başlama.
  Kanıt: `app/backend/tests/unit/test_integration_settings.py`
  (`test_nonprod_without_a_complete_sql_server_connection_starts_unconfigured`,
  `test_a_complete_nonprod_connection_needs_no_database_list`,
  `test_nonprod_may_start_without_certificate_verification_but_never_unencrypted`,
  `test_nonprod_without_sql_server_credentials_reports_not_configured`).
- [x] Task 2 — Requirement 2, 8 / Acceptance 1: bağlantı dizesi yardımcısı ve SQLSTATE hata
  sınıfları. Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_connection_string_*`, `test_unsafe_server_names_are_rejected`,
  `test_driver_errors_map_to_fixed_classes`,
  `test_a_login_timeout_is_unreachable_but_a_query_timeout_stays_a_timeout`).
- [x] Task 3 — Requirement 6, 7, 11, Decision 2, 5 / Acceptance 1, Acceptance 2: port ve pyodbc
  uyarlayıcısı; erişilebilen bütün çevrimiçi veritabanlarının sistem veritabanları olmadan
  listelenmesi, sistem veritabanı isteklerinin bağlantı açılmadan reddi, Nesne listesi süzmesi,
  tanım, Nesne meta verisi sınırları (ad başına en fazla 48 veritabanı, her ad istekte bir kez),
  olay döngüsünün 5 saniyelik bekleme sırasında 200 ms altında yanıt vermesi ve eşzamanlılık sınırı;
  üç parçalı başvurunun yalnız adını taşıdığı listedeki veritabanında çözülmesi; yürürlükteki
  bağlantının her işlemde yeniden okunması ve sertifikaya güven seçeneğinin bağlantı dizesine
  yansıması. Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_every_online_database_is_offered_except_the_system_databases`,
  `test_the_database_list_asks_only_for_online_databases_the_account_can_enter`,
  `test_system_databases_never_reach_sql_server`,
  `test_a_database_the_account_cannot_open_fails_with_a_fixed_class`,
  `test_cross_database_lookup_scans_accessible_databases_but_never_system_ones`,
  `test_cross_database_search_is_bounded_per_name_and_per_request`,
  `test_a_three_part_reference_resolves_its_id_in_the_named_database`,
  `test_a_changed_connection_is_used_on_the_next_call`). `HAS_DBACCESS` süzmesi gerçek bir SQL
  Server'da gözlenmedi; testler sorgu metnini ve sahte sürücünün yanıtını sabitler.
- [x] Task 4 — Requirement 3, 4, 5, Decision 3, 8 / Acceptance 1: `local`'de süreç içi ayar deposu,
  kısmi değişiklik, parola koruma/silme, kayıtlı parolanın başka hedefe gönderilmemesi, parolanın
  yanıt, log, `.env` ve süreç ortamında bulunmaması, sözleşmede veritabanı listesi alanının
  bulunmaması.
  Kanıt: `app/backend/tests/unit/test_sql_connection_service.py`.
- [x] Task 5 — API sözleşmesi, Requirement 5 / Acceptance 1, Acceptance 3: `/sql-connection` uçları,
  dağıtımla yönetilen `nonprod`'da yazma/test uçlarının herkes için 404 dönmesi, arayüzden yönetilen
  `nonprod`'da uçların yalnız süper yöneticiye açılması, rol denetimi, OpenAPI ve üretilmiş tipler.
  Kanıt: `app/backend/tests/unit/test_integration_settings.py`
  (`test_write_and_test_endpoints_exist_only_where_the_connection_is_editable`,
  `test_nonprod_write_requests_find_no_route`,
  `test_a_stored_nonprod_asks_for_a_session_before_it_saves_or_tests`),
  `app/backend/tests/integration/test_connection_settings_api.py`,
  `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [x] Task 6 — Decision 4, 6, Dağıtım etkisi / Acceptance 1: `pyodbc==5.3.0`, Alpine `unixodbc` ve
  bağımlılıkları, Microsoft `msodbcsql18` 18.6.2.1-1 (Microsoft EULA sahip kabulü 2026-09-26),
  kurum kök CA'sı; geliştirme ve yayın imajları. Kanıt: `python3 scripts/check-dependency-admission.py`,
  `dependency-admission.json` karar kaydı, `app/backend/tests/unit/test_corporate_ca.py`, geliştirme
  imajında ve amd64/arm64 yayın imajında sürücünün `pyodbc.drivers()` ile görülmesi.
- [x] Task 7 — Gözlemlenebilirlik: `dwhcodereview_sql_server_calls_total`,
  `dwhcodereview_sql_server_call_duration_seconds`, `dwhcodereview_sql_server_inflight` ölçümleri
  ve çağrı başına `sql_server <operation>` izi; veritabanı adı, sunucu, kullanıcı, parola ve sürücü
  metni yok. OpenTelemetry altyapısı [directory-login](../../../application-foundation/PRDs/001-directory-login/tasks.md)
  Task 13'tedir. Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_calls_emit_the_prd_metrics_and_spans_without_names_or_secrets`,
  `test_the_in_flight_gauge_counts_calls_waiting_for_the_pool`), `scripts/quality-gate.sh all`. Gerçek SQL Server
  olmadığından bu ölçümler yerel yığında canlı gözlenmedi.
- [x] Task 8 — Requirement 5, 9 / Acceptance 3: SQL bağlantısı sayfası ve Vitest testleri. Kanıt:
  `app/frontend/src/pages/ConnectionPages.test.tsx` (`editable: false` iken yalnız dağıtım notu,
  süreç içi uygulama metni, kaydetmeden test ve ilk 8 veritabanı, parola koruma/kaldırma, sabit
  hata iletisi, port aralığı, `local`'de düzenlenebilir iki şifreleme kutusu ve veritabanı listesinin
  yokluğu), `app/frontend/src/components/layout/AppShell.test.tsx` (`editable: false` iken menü
  öğesi yok). Yerel tarayıcıda `e2e/sql-review/03-settings-objects-users.mjs`
  sayfayı, kaydetmeden testin sabit hata iletisini ve inceleyiciye kapalı menüyü gözledi.
- [ ] Task 9 — Requirement 3, 4, 7, 9 / Acceptance 4 ve Requirement 5, 7, 10, 11 / Acceptance 5:
  geliştirici SQL Server'ı ve `nonprod` ayarlarıyla L2 doğrulaması. İkisi de bu sürümle açıktır:
  veritabanı listesinin gerçek SQL Server'da hesabın eriştiği bütün veritabanlarını (sistem
  veritabanları olmadan) getirdiği, sertifikaya güven seçeneği kapalıyken kendinden imzalı
  sertifikalı sunucuda `sql_tls_failed`, açıkken bağlantı kurulduğu ve `nonprod`'da süper yöneticinin
  tarayıcıdan kaydı gözlenmedi. Bu revizyonla değişmeyen davranışın önceki yerel gözlemleri:
  2026-09-27'de yerel Compose'da SQL Server 2022 Developer sürümüne okuyucu hesapla tarayıcıdan
  bağlanıldı; sertifikaya güven kapalıyken test `sql_tls_failed`, açıkken başarılıydı; kayıt
  `app/infra/.env` dosyasını değiştirmedi; görünüm, yordam ve tablo değerli fonksiyon tanımları ile
  çapraz veritabanı meta verisi port üzerinden okunup incelemeye verildi; sistem veritabanı 403
  aldı; yanlış parola `sql_login_failed`, kapalı port ve çözülemeyen ad `sql_server_unreachable`
  döndü. 2026-10-01'de (tarayıcı değil, gerçek HTTP üzerinden API; SQL Server'a çıkışı olmayan yerel
  ağda) geliştirme imajı `staging` ayarlarıyla açıldı: kayıt yeniden başlatmadan denendi
  (`sql_server_unreachable`), aynı anahtarla yeniden başlatmada geri geldi, başka anahtarla
  "yapılandırılmamış" oldu ve `sql_connection.stored_unusable` yazıldı, anahtarsız ve tam dağıtım
  bağlantılı açılışlarda yazma ve test 404 aldı, PostgreSQL satırında parola şifreliydi.
- [x] Task 10 — Requirement 1, 10, Decision 13 / Acceptance 1: `SecretCipher` (AES-256-GCM) ve
  `DWHCODEREVIEW_SETTINGS_ENCRYPTION_KEY` ayarı. Kanıt:
  `app/backend/tests/unit/test_secret_cipher.py` (yanlış anahtar, başka bağlam, değiştirilmiş ve
  biçimsiz değer açılmaz; aynı değer her seferinde farklı şifrelenir; anahtar tam 32 bayt olmalı),
  `app/backend/tests/unit/test_config.py`
  (`test_the_settings_encryption_key_is_optional_and_must_be_32_bytes`,
  `test_a_deployment_supplies_the_sql_connection_only_when_it_is_complete`),
  `python3 scripts/check-config-sync.py`. Yeni bağımlılık eklenmedi; `cryptography` kilitli
  `pyjwt[crypto]` bağımlılığıdır (`python3 scripts/check-dependency-admission.py` değişmeden geçer).
- [x] Task 11 — Requirement 5, 10, 11, Decision 5, 6, 12, 14 / Acceptance 1: `sql_connection_setting`
  tablosu ve iki göçü, depo, `StoredSqlConnection`, durum seçimi, süper yöneticiye açılan uçlar ve her
  istekte yeniden okuma. Kanıt: `scripts/db.sh validate`;
  `app/backend/tests/unit/test_sql_connection_service.py` (durum seçimi, süper yönetici görünümü,
  diğer rollerin 403 alması, kayıt güvenceleri, sertifikaya güven seçeneğinin açılıp kapatılması,
  veritabanı listesi olmadan kayıt ve test);
  `app/backend/tests/unit/test_sql_connection_wiring.py` (süreç içi bağlantıların ayarlardan
  kurulması); `app/backend/tests/integration/test_sql_connection_storage.py` (parola tabloda
  şifreli, kaydeden kullanıcı ve zaman sütunları, ikinci kopyanın yeniden başlatmadan yeni bağlantıyı
  kullanması ve erişilebilen bütün veritabanlarını listelemesi, sertifika seçeneğinin kayıtla
  birlikte diğer kopyaya ulaşması (`TrustServerCertificate=yes/no`), başka anahtarla şifrelenmiş
  parolada "yapılandırılmamış" durum ve tek olay, süper yönetici olmayan ya da bilinmeyen hesabın
  reddi, reddedilen değişikliğin hiçbir şey yazmaması, okuma hatasında son bağlantının korunması,
  iki göçün geri alınıp yeniden uygulanması ve `202610010002`'nin kayıt varken geri alınmayı
  reddetmesi); `app/backend/tests/integration/test_connection_settings_api.py`
  (`test_nonprod_super_admin_saves_tests_and_reads_the_connection`,
  `test_nonprod_stored_password_is_ciphertext_in_postgresql`,
  `test_nonprod_other_roles_cannot_see_or_change_the_stored_connection`,
  `test_nonprod_save_refuses_values_that_break_the_guarantees`,
  `test_nonprod_shows_only_the_state_and_has_no_write_endpoints`);
  `app/backend/tests/integration/test_data_model.py` (zorunlu blok, açıklamalar,
  `test_a_saved_sql_connection_is_one_row_per_tenant`);
  `app/backend/tests/integration/test_review_catalog_api.py` (bütün veritabanlarının listelenmesi,
  sistem veritabanının 403 alması, başka her veritabanının porta iletilmesi).
- [x] Task 12 — Requirement 5, 9 / Acceptance 3: `nonprod` SQL bağlantısı formu ve menü görünürlüğü.
  Kanıt: `app/frontend/src/pages/ConnectionPages.test.tsx` (`managed_by: super_admin` ve
  `editable: false` iken yalnız uygulama yöneticisi iletisi; süper yönetici formunda veritabanı
  listesi alanının ve şifreleme kutusunun yokluğu, gönderilen alanlar; sertifikaya güven kutusu,
  uyarısı ve test ile kayıtta gönderilmesi; sunucunun ret iletisi),
  `app/frontend/src/pages/ObjectReviewPage.test.tsx` (seçicinin sunucunun döndürdüğü bütün
  veritabanlarını sunması, erişilebilen veritabanı yokken ileti, sistem veritabanı iletisi), `app/frontend/src/components/layout/AppShell.test.tsx`
  (`nonprod`'da menü öğesi süper yöneticide var, `kural-yoneticisi`nde yok). Tarayıcı senaryosu
  yerel yığın `local` Ortamda çalıştığı için `nonprod` formunu kapsamaz; Acceptance 5 ile açıktır.
- [x] Task 13 — Decision 13, Dağıtım etkisi / Acceptance 1: `deploy-hooks.sh` ayar şifreleme
  anahtarını bir kez üretir ve korur. Kanıt: `tests/helm/deploy-hooks.test.sh` (ilk koşuda 32 baytlık
  anahtar, sonraki koşuda ve kimlik bilgisi değişiminde aynı anahtar, pipeline değeri, çözülmemiş
  makroda kümedeki anahtar, üç biçimsiz değerde durma, değerin çıktıya ve argümana düşmemesi),
  `scripts/render-charts.sh` ("deploy-hooks.sh parses").
- [x] Task 14 — Belgeler: `docs/tr/yonetici-kilavuzu.md` (test ortamında bağlantının süper
  yöneticice girilmesi, sertifikaya güven seçeneğinin ne zaman ve ne kadar süreyle kullanılacağı,
  `SETTINGS_ENCRYPTION_KEY`, günlük olayları) ve `docs/tr/kullanim-kilavuzu.md`
  (rol tablosu, veritabanı seçimi, "yapılandırılmamış" ve sistem veritabanı iletileri),
  `docs/tr/yerel-kurulum.md` (veritabanı listesi ayarının yokluğu). Kanıt: belgelerin kendisi; otomatik denetimi yoktur.
- [ ] Task 15 — Decision 6 istisnası: bitiş tarihi 2026-12-31. Veritabanı ekibi PASIFIK'e kurum CA
  imzalı sertifika kurunca süper yönetici sertifikaya güven seçeneğini kapatır; o tarihte istisna bu
  PRD'nin revizyonuyla kaldırılır ya da yenilenir.
