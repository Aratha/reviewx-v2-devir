# Görevler — sql-server-connection

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-10-01'de yerel
Compose yığınında geçti (arka uç 723/723, ön yüz 138/138 test; göç, OpenAPI, üretilmiş tip,
yönetişim sapması ve proje katmanıyla chart adımı dahil) ve `tests/helm/deploy-hooks.test.sh` 70
denetimi geçti. Bu, L1 (otomatik testlerden geçti) kanıtıdır. Gerçek bir SQL Server'a karşı yapılan
yerel gözlem Task 9'dadır; `nonprod` tarayıcı gözlemi (Acceptance 5) açıktır.

- [x] Task V1 — Requirement 1 / Acceptance 1: tipli ayar alanları ve aralık doğrulaması. Kanıt:
  `app/backend/tests/unit/test_config.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 1 — Requirement 1, Decision 5, 6, 10, 11 / Acceptance 1: başlangıç denetimi (`nonprod`'da
  tam bağlantıda boş izin listesi, sistem veritabanı, şifreleme kapalı, sertifikaya güven açık; her
  ortamda biçimsiz sunucu/kullanıcı) ve eksik bağlantıda "yapılandırılmamış" olarak başlama. Kanıt:
  `app/backend/tests/unit/test_integration_settings.py`
  (`test_nonprod_without_a_complete_sql_server_connection_starts_unconfigured`,
  `test_a_complete_nonprod_connection_still_requires_the_allow_list`,
  `test_nonprod_without_sql_server_credentials_reports_not_configured`). 2026-09-27'de yayın backend
  imajı `staging` ayarlarıyla ve SQL Server hesabı olmadan yerelde açıldı: hazır olma yoklaması 200,
  `GET /sql-connection` `configured: false`, `GET /databases` 503 `sql_connection_not_configured`
  (kubernetes-delivery Task 5).
- [x] Task 2 — Requirement 2, 8 / Acceptance 1: bağlantı dizesi yardımcısı ve SQLSTATE hata
  sınıfları. Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_connection_string_*`, `test_unsafe_server_names_are_rejected`,
  `test_driver_errors_map_to_fixed_classes`,
  `test_a_login_timeout_is_unreachable_but_a_query_timeout_stays_a_timeout`).
- [x] Task 3 — Requirement 6, 7, Decision 2 / Acceptance 1, Acceptance 2: port ve pyodbc
  uyarlayıcısı; izin listesi, Nesne listesi süzmesi, tanım, Nesne meta verisi sınırları, olay
  döngüsünün 5 saniyelik bekleme sırasında 200 ms altında yanıt vermesi ve eşzamanlılık sınırı;
  üç parçalı başvurunun yalnız adını taşıdığı izinli veritabanında çözülmesi; Requirement 11:
  yürürlükteki bağlantı ile izin listesinin her işlemde birlikte okunması. Kanıt:
  `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_a_three_part_reference_resolves_its_id_in_the_named_database`,
  `test_a_changed_connection_and_allow_list_are_used_on_the_next_call`,
  `test_a_connection_test_uses_the_candidate_allow_list_not_the_saved_one`).
- [x] Task 4 — Requirement 3, 4, 5, Decision 3, 8 / Acceptance 1: `local`'de süreç içi ayar deposu,
  kısmi değişiklik, parola koruma/silme, kayıtlı parolanın başka hedefe gönderilmemesi, parolanın
  yanıt, log, `.env` ve süreç ortamında bulunmaması, izin listesinin arayüzden değiştirilememesi.
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
  hata iletisi, port aralığı, `local`'de salt okunur izin listesi ve düzenlenebilir şifreleme
  kutuları), `app/frontend/src/components/layout/AppShell.test.tsx` (`editable: false` iken menü
  öğesi yok). Yerel tarayıcıda `e2e/sql-review/03-settings-objects-users.mjs`
  sayfayı, kaydetmeden testin sabit hata iletisini ve inceleyiciye kapalı menüyü gözledi.
- [ ] Task 9 — Requirement 3, 4, 7, 9 / Acceptance 4 ve Requirement 5, 7 / Acceptance 5: geliştirici
  SQL Server'ı ve `nonprod` ayarlarıyla L2 doğrulaması. Acceptance 4 bölümü 2026-09-27'de yerel
  Compose'da, veri ambarının yalnız şema kopyasını taşıyan SQL Server 2022 Developer sürümüne
  `CONNECT ANY DATABASE` ve `VIEW ANY DEFINITION` dışında yetkisi olmayan okuyucu hesapla gözlendi:
  tarayıcıda sertifikaya güven kapalıyken test `sql_tls_failed`, açıkken 11 izinli veritabanıyla
  başarılı; kayıt `app/infra/.env` dosyasını değiştirmedi; İnceleme sayfasında veritabanı ve Nesne
  listelendi; üç veritabanında görünüm, yordam ve tablo değerli fonksiyon tanımları ile çapraz
  veritabanı meta verisi port üzerinden okunup incelemeye verildi; izin dışı ve sistem veritabanı
  403 aldı; API ile yanlış parola `sql_login_failed`, kapalı port ve çözülemeyen ad
  `sql_server_unreachable` döndü. Acceptance 5 açık: `nonprod` ayarlarıyla tarayıcıdan kayıt, test
  ve gerçek SQL Server'dan liste gözlenmedi. 2026-10-01 yerel gözlem (L2 değil; tarayıcı değil,
  gerçek HTTP üzerinden API; SQL Server'a çıkışı olmayan yerel ağda): geliştirme imajı `staging`
  ayarlarıyla ve ayar şifreleme anahtarıyla açıldı; süper yönetici `GET /sql-connection` ile
  `editable: true`, `managed_by: super_admin` gördü, `GET /databases` 503
  `sql_connection_not_configured` döndü; sistem veritabanlı liste 422
  `sql_allowed_databases_invalid`, sertifikaya güven 422 `sql_setting_fixed` aldı; kayıt 200 döndü
  ve hemen ardından `GET /databases` 503 `sql_server_unreachable` (kaydedilen bağlantı denendi),
  test `sql_server_unreachable` döndü; oturumsuz yazma 401 aldı. Süreç aynı anahtarla yeniden
  başlatılınca kayıt `password_set: true` ile geri geldi; başka anahtarla `password_set: false`,
  `configured: false` oldu ve `sql_connection.stored_unusable` olayı yazıldı; anahtarsız ve tam
  dağıtım bağlantılı açılışlarda `managed_by: deployment` görüldü, yazma ve test 404 aldı.
  PostgreSQL satırında parola `v1.` ile başlayan şifreli değerdi; yanıtlarda ve logda parola ve
  anahtar yoktu.
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
  tablosu ve göçü, depo, `StoredSqlConnection`, durum seçimi, süper yöneticiye açılan uçlar ve her
  istekte yeniden okuma. Kanıt: `scripts/db.sh validate`;
  `app/backend/tests/unit/test_sql_connection_service.py` (durum seçimi, süper yönetici görünümü,
  diğer rollerin 403 alması, kayıt güvenceleri, izin listesi seçilmeden test);
  `app/backend/tests/unit/test_sql_connection_wiring.py` (süreç içi bağlantıların ayarlardan
  kurulması); `app/backend/tests/integration/test_sql_connection_storage.py` (parola tabloda
  şifreli, kaydeden kullanıcı ve zaman sütunları, ikinci kopyanın yeniden başlatmadan yeni bağlantıyı
  kullanması, başka anahtarla şifrelenmiş parolada ve güvencesini yitirmiş izin listesinde
  "yapılandırılmamış" durum ve tek olay, süper yönetici olmayan ya da bilinmeyen hesabın reddi,
  reddedilen değişikliğin hiçbir şey yazmaması, okuma hatasında son bağlantının korunması, göçün
  geri alınıp yeniden uygulanması); `app/backend/tests/integration/test_connection_settings_api.py`
  (`test_nonprod_super_admin_saves_tests_and_reads_the_connection`,
  `test_nonprod_stored_password_is_ciphertext_in_postgresql`,
  `test_nonprod_other_roles_cannot_see_or_change_the_stored_connection`,
  `test_nonprod_save_refuses_values_that_break_the_guarantees`,
  `test_nonprod_shows_only_the_state_and_has_no_write_endpoints`);
  `app/backend/tests/integration/test_data_model.py` (zorunlu blok, açıklamalar,
  `test_a_saved_sql_connection_is_one_row_per_tenant_with_a_usable_allow_list`). Bilinçli bozmada
  (istekten önceki yeniden okuma kaldırıldı) ikinci kopya testi kırmızıya döndü.
- [x] Task 12 — Requirement 5, 9 / Acceptance 3: `nonprod` SQL bağlantısı formu ve menü görünürlüğü.
  Kanıt: `app/frontend/src/pages/ConnectionPages.test.tsx` (`managed_by: super_admin` ve
  `editable: false` iken yalnız uygulama yöneticisi iletisi; süper yönetici formunda izin listesi
  alanı, şifreleme kutularının yokluğu ve gönderilen alanlar; boş ya da sistem veritabanlı listede
  kapalı "Kaydet"; sunucunun ret iletisi), `app/frontend/src/components/layout/AppShell.test.tsx`
  (`nonprod`'da menü öğesi süper yöneticide var, `kural-yoneticisi`nde yok). Tarayıcı senaryosu
  yerel yığın `local` Ortamda çalıştığı için `nonprod` formunu kapsamaz; Acceptance 5 ile açıktır.
- [x] Task 13 — Decision 13, Dağıtım etkisi / Acceptance 1: `deploy-hooks.sh` ayar şifreleme
  anahtarını bir kez üretir ve korur. Kanıt: `tests/helm/deploy-hooks.test.sh` (ilk koşuda 32 baytlık
  anahtar, sonraki koşuda ve kimlik bilgisi değişiminde aynı anahtar, pipeline değeri, çözülmemiş
  makroda kümedeki anahtar, üç biçimsiz değerde durma, değerin çıktıya ve argümana düşmemesi),
  `scripts/render-charts.sh` ("deploy-hooks.sh parses").
- [x] Task 14 — Belgeler: `docs/tr/yonetici-kilavuzu.md` (test ortamında bağlantının süper
  yöneticice girilmesi, `SETTINGS_ENCRYPTION_KEY`, günlük olayları) ve `docs/tr/kullanim-kilavuzu.md`
  (rol tablosu, "yapılandırılmamış" iletisi). Kanıt: belgelerin kendisi; otomatik denetimi yoktur.
