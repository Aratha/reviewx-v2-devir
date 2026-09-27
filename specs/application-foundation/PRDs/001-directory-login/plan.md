# Plan — directory-login

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.1.2). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uç ve `sqlalchemy-alembic` kalıcılığıdır.

## Kiracı kapsamı kararı

Uygulama tek kiracılıdır (Decision 6). İskeletin mevcut kiracı düzeni aynen kullanılır; yeni bir
kiracı mekanizması eklenmez:

- Göç `202609260001`, `code = 'platform'` kiracısını sabit `public_id`
  `00000000-0000-4000-8000-000000000010` ile tohumlar. Kayıt zaten varsa (örneğin daha önce
  `create_super_admin` açtıysa) dokunmaz.
- Dizin girişiyle açılan her kullanıcının `home_tenant_id` değeri bu kiracıdır; süper yönetici ve
  yerel test hesapları da aynı kiracıya bağlanır.
- JWT `tenant_id` iddiası bu kiracının `public_id` değerini taşır. Ön yüz her korumalı istekte
  iskeletin `x-tenant-id` başlığını giriş yanıtındaki `user.tenant_id` ile gönderir;
  `TenantContextMiddleware` başlığı JWT ile karşılaştırır.
- Çerezle çalışan `POST /auth/refresh` ve `POST /auth/logout` kiracı başlığı istemez; kiracıyı
  sunucudaki oturum kaydı belirler.
- Sahipli iş tabloları (`app_user_change`, `auth_refresh_session`, `rule_set_draft`,
  `rule_set_version`, `review_run`, `llm_call_summary`) `tenant_id` dış anahtarı taşır; alt tablolar
  kiracıyı üst kayıt üzerinden alır. Benzersizlik kuralları kiracıyla nitelenir (örneğin sürüm
  numarası kiracı içinde tekildir).

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Ayarlar | `app/backend/app/core/config.py`, `app/backend/.env.example`, `app/infra/docker-compose.local.yml` | Requirement 3, 6, 7, 9, 10, 11 |
| Şema yetkisi | `app/backend/app/domain/models/user.py`, `refresh_session.py`, `user_change.py`, `role.py`, `tenant.py` | Requirement 3, 4, 5, 7; Veri ve geçiş |
| Göç | `schema/alembic/versions/202609260001_directory_login_and_review_data_model.py` | Veri ve geçiş |
| Alan sözleşmesi | `app/backend/app/domain/directory.py` (UPN normalleştirme, dizin portu) | Requirement 1, 2, 3 |
| Dizin uyarlayıcısı | `app/backend/app/infrastructure/directory/ldap_login_client.py`, `app/backend/certs/nonprod-directory-ca.crt` | Requirement 2, 10; Decision 1–3 |
| Depolar | `app/backend/app/infrastructure/repositories/user_repository.py`, `refresh_session_repository.py` | Requirement 4, 5, 7, 8 |
| Hizmetler | `app/backend/app/services/auth_service.py`, `user_admin_service.py` | Requirement 1–9, 11, 12 |
| Çekirdek | `app/backend/app/core/errors.py`, `login_throttle.py`, `client_address.py`, `security.py`, `logging.py` | Requirement 6, 7, 9; Gözlemlenebilirlik |
| API | `app/backend/app/api/auth/`, `app/backend/app/api/admin/router.py`, `app/backend/app/schemas/auth/`, `app/backend/app/schemas/admin/users.py` | API sözleşmesi, Requirement 5, 6, 7, 8, 12 |
| Betik | `scripts/create-local-user.sh`, `app/backend/app/scripts/create_local_user.py` | Requirement 11, Decision 9 |
| Bağımlılık | `app/backend/requirements.in` (`ldap3==2.9.1`), kilitli `requirements*.txt`, `dependency-admission.json` | Requirement 2 |
| Telemetri | `app/backend/app/core/telemetry.py`, `app/backend/app/core/config.py` (`DWHCODEREVIEW_OTEL_*`), `app/backend/app/services/startup_checks.py`, `app/backend/app/middleware/request_logging.py`, `app/backend/app/core/logging.py`, `app/backend/app/main.py`, `app/infra/docker-compose.local.yml`, `app/infra/docker-compose.observability.yml`, OpenTelemetry sabitlemeleri `app/backend/requirements.in`, `dependency-admission.json` | Gözlemlenebilirlik; ortak kurallar [alan belgesinde](../../DOMAIN.md) |
| Sözleşme | `specs/openapi/dwhcodereview-api.yaml`, üretilmiş `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | `app/frontend/src/lib/authStorage.ts` (bellekte oturum), `app/frontend/src/lib/apiClient.ts` (çerezle yenileme ve yeniden deneme), `app/frontend/src/contexts/AuthContext.tsx`, `app/frontend/src/pages/LoginPage.tsx`, `app/frontend/src/components/layout/AppShell.tsx`, `app/frontend/src/components/auth/RoleRoute.tsx`, `app/frontend/src/pages/UserAdministrationPage.tsx` | Requirement 5, 6, 8, 13 |

## Uygulama kararları

- Oturum: erişim belirteci ES256, 15 dakika (`DWHCODEREVIEW_ACCESS_TOKEN_EXPIRE_MINUTES=15`).
  Yenileme belirteci 256 bit CSPRNG; veritabanında yalnız SHA-256 özeti tutulur. Her yenileme
  sunulan satırı `rotated` olarak kapatıp aynı `family_id` ile yenisini ekler; kapanmış satır
  yeniden gelirse aile `reuse_detected` ile kapanır ve kapanış 401 yanıtından önce kalıcı yazılır.
  Boşta kalma 60 dakika, mutlak sınır 8 saat; mutlak sınır yenilemeyle uzamaz.
- Çerez adı `dwhcodereview_refresh`; `Secure`, `HttpOnly`, `SameSite=Strict`,
  `Path=/api/dwhcodereview/v1/auth`. `refresh` ve `logout`, `Origin` başlığı
  `DWHCODEREVIEW_PUBLIC_ORIGIN` ile birebir eşleşmezse 403 `origin_not_allowed` döner.
- Süresi dolmuş veya kapanmış oturum kayıtları, bitişlerinden 7 gün sonra her başarılı girişte
  silinir (istek üzerine çalışan temizlik; ayrı arka plan işi yoktur).
- Yerel parolalı giriş: `nonprod`'da (ortam değeri `development` dışındaki her değer) yalnız
  `super_admin` rolündeki yerel hesaba açıktır. `DWHCODEREVIEW_LOCAL_LOGIN_SUPER_ADMIN_ONLY_ENFORCED`
  yalnız aynı sınırı `local` ortama da ekleyebilir; `nonprod` sınırını kaldıramaz.
- Roller iskeletin RBAC tablolarında tutulur: göç `inceleyici` ve `kural-yoneticisi` rollerini ve
  onlara iskeletin `platform:access` iznini tohumlar. Uç yetkileri rol üzerindendir; süper yönetici
  dışındaki kullanıcının tek uygulama rolü `app_user_role` içinde tek etkin atamadır.
- Rol ve durum uçları çağıranın süper yönetici olduğunu JWT'ye ek olarak veritabanından yeniden
  okur (Requirement 12). Doğrulama hatası PRD'deki gibi 400 `invalid_request` döner.
- Hız sınırı süreç içidir: ad+adres için 15 dakikada 5, adres için 15 dakikada 30 hatalı deneme.
  `X-Forwarded-For` yalnız isteğin doğrudan karşı ucu `DWHCODEREVIEW_TRUSTED_PROXY_CIDRS`
  içindeyse dikkate alınır.
- Başarısız girişte ad yerine anahtarlı özet (`name_digest`) yazılır; anahtar JWT imza anahtarından
  türetilir, yeni sır eklenmez. Bütün uygulama olayları `x-request-id` değerini taşır.
- Dizin uyarlayıcısı kullanıcı adıyla tek arama yapar (`userPrincipalName` eşitliği) ve
  `objectClass`, `servicePrincipalName` özniteliklerini de okur; bilgisayar ve servis hesabı bu
  sayede 401 ile reddedilir. Yönlendirme izlenmez; bağlantı süresi 5, okuma süresi 10 saniyedir.
- Hata gövdesi her yeni uçta `{"detail":{"code":"...","message":"..."}}` biçimindedir; iskeletin
  kimlik ve kiracı hataları da aynı zarfa taşındı.

## Göç ve dağıtım bağımlılığı

- Göç `202609260001` yalnız genişleticidir: `app_user.username` 320 karaktere genişler,
  `password_hash` boş olabilir ve hesap türüyle eşleşme kısıtı eklenir; yeni tablolar eklenir.
  Geri alma, dizin hesabı varken yerel hesap kısıtı nedeniyle durur.
- CA bundle'ının imaja girmesi, dizin ayarlarının değer katmanına (`values-project.yaml`)
  yazılması ve LDAPS çıkış kuralı [kubernetes-delivery](../002-kubernetes-delivery/PRD.md)
  PRD'sinindir.

## Doğrulama komutları

- `python3 scripts/check-config-sync.py`
- `python3 scripts/check-dependency-admission.py`
- `scripts/db.sh apply`, `scripts/db.sh validate`, `scripts/db.sh status`
- `scripts/quality-gate.sh backend` ve devir için `scripts/quality-gate.sh all`
- `python3 scripts/check-governance-drift.py`, `PYTHON=.venv/bin/python scripts/render-charts.sh --self-test`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 1, 2, 10 | Acceptance 1, Acceptance 3 | Task 3, Task 4, Task 12 |
| Requirement 3, 4 | Acceptance 1, Acceptance 3 | Task 2, Task 4 |
| Requirement 5 | Acceptance 1, Acceptance 2 | Task 2, Task 6, Task 10, Task 11 |
| Requirement 6, 7, 8 | Acceptance 1, Acceptance 2 | Task 2, Task 5, Task 10, Task 11 |
| Requirement 9 | Acceptance 1, Acceptance 3 | Task 4, Task 12 |
| Requirement 11 | Acceptance 1, Acceptance 2 | Task 1, Task 7, Task 11 |
| Requirement 12 | Acceptance 1 | Task 4, Task 6 |
| Requirement 13 | Acceptance 2 | Task 10, Task 11 |
| Dağıtım etkisi (ayarlar, bağımlılık) | Acceptance 1 | Task 1, Task 8, Task 9 |
| Gözlemlenebilirlik (ölçüm, iz, ortak telemetri) | — | Task 13 |
