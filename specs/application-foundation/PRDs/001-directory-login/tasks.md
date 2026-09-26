# Görevler — directory-login

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti (arka uç 236/236, ön yüz 35/35 test; göç, OpenAPI, üretilmiş tip,
yönetişim sapması ve chart adımları dahil). Bu, arka uç kapsamı için L1 (otomatik testlerden
geçti) kanıtıdır; Acceptance 1'in ön yüz bölümü Task 10 tamamlanmadan karşılanmaz.

- [x] Task 1 — Requirement 3, 6, 7, 9, 10, 11 / Acceptance 1: tipli ayarlar (ortam eşlemesi,
  dizin, oturum süreleri, güvenilen giriş denetleyicisi, uygulama adresi), `.env.example` ve yerel
  Compose ortamı. Kanıt: `tests/unit/test_config.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 2 — Requirement 3, 4, 5, 7 ve "Veri ve geçiş" / Acceptance 1: `app_user` genişletmesi,
  `auth_refresh_session`, `app_user_change`, `platform` kiracısı ve iki rolün tohumlanması; göç
  `202609260001`. Kanıt: `tests/integration/test_data_model.py`, `scripts/db.sh validate`.
- [x] Task 3 — Requirement 1, 2, 10 / Acceptance 1: UPN normalleştirme, LDAPS yalnız-giriş
  uyarlayıcısı (CA ve sunucu adı doğrulaması, yönlendirme yok, 5/10 saniye), sürümlenmiş CA bundle'ı.
  Kanıt: `tests/unit/test_directory_identity.py`, `tests/unit/test_ldap_login_client.py`,
  `tests/unit/test_directory_ca_bundle.py`.
- [x] Task 4 — Requirement 1–4, 9, 11, 12 / Acceptance 1: giriş hizmeti ve `POST /auth/login`
  (yerel/dizin ayrımı, `nonprod` yerel giriş sınırı, ilk girişte kayıt, 401/403/409/429/503, hız
  sınırı, denetim olayları, statik anahtar başlıklarının anlamsızlığı). Kanıt:
  `tests/integration/test_directory_login.py`, `tests/unit/test_login_throttle.py`,
  `tests/unit/test_api_baseline.py`.
- [x] Task 5 — Requirement 6, 7, 8 / Acceptance 1: 15 dakikalık ES256 belirteç, dönen yenileme
  oturumu, tekrar kullanım tespiti, `Origin` denetimi, `POST /auth/refresh`, `POST /auth/logout`,
  7 günlük temizlik. Kanıt: `tests/integration/test_directory_login.py`,
  `tests/unit/test_security.py`.
- [x] Task 6 — Requirement 5, 12 / Acceptance 1: `GET /admin/users`, rol ve durum uçları,
  değişiklik kaydı tablosu, oturum kapatma, çağıranın veritabanından yeniden okunması. Kanıt:
  `tests/integration/test_user_administration.py`, `tests/unit/test_rbac.py`.
- [x] Task 7 — Requirement 11, Decision 9 / Acceptance 1: `scripts/create-local-user.sh --role <rol>`
  yalnız dizin kapalıyken ve `local` ortamda çalışır. Kanıt:
  `tests/integration/test_user_administration.py` (dizin açık ve `nonprod` redleri, tekrar
  çalıştırmada aynı sonuç).
- [x] Task 8 — Requirement 2 / Acceptance 1: `ldap3==2.9.1` bağımlılık kabulü ve özetle kilitli
  gereksinim dosyaları. Kanıt: `python3 scripts/check-dependency-admission.py`,
  `dependency-admission.json` karar kaydı.
- [x] Task 9 — API sözleşmesi / Acceptance 1: `specs/openapi/dwhcodereview-api.yaml` ve üretilmiş ön
  yüz tipleri. Kanıt: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [x] Task 13 — Gözlemlenebilirlik: OpenTelemetry altyapısı (tipli `DWHCODEREVIEW_OTEL_*`
  ayarları, boş adreste dışa aktarım yok, `OTEL_*` süreç değişkeninde başlangıç reddi, `nonprod`'da
  yalnız `https`, gözlemlenebilirlik Compose katmanında yerel toplayıcı), istek başına sunucu izi,
  PostgreSQL komut izleri (yalnız komut türü), istek logunda `trace_id`, giriş sonuçları ölçümü
  `dwhcodereview_auth_login_attempts_total{outcome}`; OpenTelemetry paketlerinin bağımlılık kabulü.
  Kanıt: `tests/unit/test_telemetry.py`, `tests/unit/test_config.py`,
  `tests/unit/test_integration_settings.py`, `tests/integration/test_telemetry_signals.py`
  (`test_login_outcomes_are_counted_without_names_or_passwords`),
  `python3 scripts/check-dependency-admission.py`, `python3 scripts/check-config-sync.py`,
  `scripts/quality-gate.sh all`. Yerel gözlemlenebilirlik yığınında giriş ölçümü Prometheus'ta, aynı isteğin izi
  Tempo'da ve iz kimliği istek logunda gözlendi; bu, yerel ortam gözlemidir, `nonprod` kanıtı değildir.
- [ ] Task 10 — Requirement 6 (belleğe alınan belirteç), 13 / Acceptance 1, Acceptance 2: giriş
  ekranı, sessiz yenileme, çıkış, oturum bitince girişe dönüş, süper yönetici kullanıcı yönetimi
  ekranı, Vitest testleri ve tarayıcı senaryosu.
- [ ] Task 11 — Requirement 3, 5–8, 11, 13 / Acceptance 2: yerel Compose'da tarayıcıyla L2
  doğrulaması (gerçek istemci ve ortamda gözlem).
- [ ] Task 12 — Requirement 1–4, 9, 10 / Acceptance 3: `nonprod` kümede gerçek Active Directory ile
  L2 doğrulaması; CA bundle'ının imaja, dizin ayarlarının runtime Secret'a girmesi ve LDAPS çıkış
  kuralı [kubernetes-delivery](../002-kubernetes-delivery/PRD.md) görevleriyle birlikte.
