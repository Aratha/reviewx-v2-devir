# Görevler — sql-server-connection

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti. Bu, arka uç kapsamı için L1 (otomatik testlerden geçti) kanıtıdır. Gerçek
bir SQL Server'a karşı tümleşik test çalıştırılmadı: yerelde erişilebilir SQL Server yoktu.

- [x] Task V1 — Requirement 1 / Acceptance 1: tipli ayar alanları ve aralık doğrulaması. Kanıt:
  `app/backend/tests/unit/test_config.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 1 — Requirement 1, Decision 5, 6, 10 / Acceptance 1: başlangıç denetimi (`nonprod`'da
  eksik değer, sistem veritabanı, şifreleme kapalı, sertifikaya güven açık; her ortamda biçimsiz
  sunucu/kullanıcı). Kanıt: `app/backend/tests/unit/test_integration_settings.py`.
- [x] Task 2 — Requirement 2, 8 / Acceptance 1: bağlantı dizesi yardımcısı ve SQLSTATE hata
  sınıfları. Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`
  (`test_connection_string_*`, `test_unsafe_server_names_are_rejected`,
  `test_driver_errors_map_to_fixed_classes`).
- [x] Task 3 — Requirement 6, 7, Decision 2 / Acceptance 1, Acceptance 2: port ve pyodbc
  uyarlayıcısı; izin listesi, Nesne listesi süzmesi, tanım, Nesne meta verisi sınırları, olay
  döngüsünün 5 saniyelik bekleme sırasında 200 ms altında yanıt vermesi ve eşzamanlılık sınırı.
  Kanıt: `app/backend/tests/unit/test_sql_server_adapter.py`.
- [x] Task 4 — Requirement 3, 4, 5, Decision 3, 8 / Acceptance 1: süreç içi ayar deposu, kısmi
  değişiklik, parola koruma/silme, kayıtlı parolanın başka hedefe gönderilmemesi, parolanın yanıt,
  log, `.env` ve süreç ortamında bulunmaması. Kanıt:
  `app/backend/tests/unit/test_sql_connection_service.py`.
- [x] Task 5 — API sözleşmesi, Requirement 5 / Acceptance 1, Acceptance 3: `/sql-connection` uçları,
  `nonprod`'da yazma/test uçlarının 404 dönmesi, rol denetimi, OpenAPI ve üretilmiş tipler. Kanıt:
  `app/backend/tests/unit/test_integration_settings.py`,
  `app/backend/tests/integration/test_connection_settings_api.py`,
  `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [x] Task 6 — Decision 4, 6, Dağıtım etkisi / Acceptance 1: `pyodbc==5.3.0`, Alpine `unixodbc` ve
  bağımlılıkları, Microsoft `msodbcsql18` 18.6.2.1-1 (Microsoft EULA sahip kabulü 2026-09-26),
  kurum kök CA'sı; geliştirme ve yayın imajları. Kanıt: `python3 scripts/check-dependency-admission.py`,
  `dependency-admission.json` karar kaydı, `app/backend/tests/unit/test_corporate_ca.py`, geliştirme
  imajında ve amd64/arm64 yayın imajında sürücünün `pyodbc.drivers()` ile görülmesi.
- [ ] Task 7 — Gözlemlenebilirlik: `dwhcodereview_sql_server_calls_total`,
  `dwhcodereview_sql_server_call_duration_seconds` ve `dwhcodereview_sql_server_inflight`
  ölçümleri. Arka uçta ölçüm kitaplığı veya dışa aktarıcı yok; yeni bağımlılık (OpenTelemetry SDK
  veya Prometheus istemcisi) için sahip kararı ve kabul kaydı gerekiyor. Açık, engelli.
- [x] Task 8 — Requirement 5, 9 / Acceptance 3: SQL bağlantısı sayfası ve Vitest testleri. Kanıt:
  `app/frontend/src/pages/ConnectionPages.test.tsx` (`editable: false` iken yalnız dağıtım notu,
  süreç içi uygulama metni, kaydetmeden test ve ilk 8 veritabanı, parola koruma/kaldırma, sabit
  hata iletisi, port aralığı), `app/frontend/src/components/layout/AppShell.test.tsx` (`editable:
  false` iken menü öğesi yok). Yerel tarayıcıda `e2e/sql-review/03-settings-objects-users.mjs`
  sayfayı, kaydetmeden testin sabit hata iletisini ve inceleyiciye kapalı menüyü gözledi.
- [ ] Task 9 — Requirement 3, 4, 7, 9 / Acceptance 4 ve Requirement 5, 7 / Acceptance 5: geliştirici
  SQL Server'ı ve `nonprod` ayarlarıyla L2 doğrulaması; gerçek SQL Server'a karşı tümleşik testler
  (yanlış parola `sql_login_failed`, erişilemeyen port `sql_server_unreachable`). Yerel Compose ağı
  dışarı çıkamadığı için erişilebilir SQL Server yok; açık.
