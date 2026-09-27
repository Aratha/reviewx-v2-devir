# Görevler — rule-management

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti (göç, arka uç, ön yüz, OpenAPI, üretilmiş tip, yönetişim sapması ve chart
adımları dahil). Bu, L1 (otomatik testlerden geçti) kanıtıdır; Acceptance 4'ün yerel tarayıcı kanıtı
Task 7'dedir, Acceptance 5 açıktır.

- [x] Task V1 — Requirement 2, 3, 4, 5, 8 / Acceptance 1: taslak, taslak kuralı, sürüm ve sürüm
  kuralı tabloları; göç `202609260001`. Kanıt: `app/backend/tests/integration/test_data_model.py`.
- [x] Task 1 — Requirement 2, 3, 5, 6 / Acceptance 1: kırpma, boş kural atma, kimlik biçimi,
  yineleme, 8.000 karakter ve 200 kural sınırı, kullanılmış kimliğin reddi, ilk serbest numara ve
  içerik parmak izi. Kanıt: `app/backend/tests/unit/test_rule_set_rules.py`.
- [x] Task 2 — Requirement 1, 8 / Acceptance 1: `require_any_role` rol bağımlılığı ve 422 zarfıyla
  dönen istek doğrulaması. Kanıt: `app/backend/tests/integration/test_rule_set_api.py`
  (`test_roles_are_enforced_on_every_endpoint`, `test_invalid_codes_and_limits_are_rejected_without_writing`).
- [x] Task 3 — Requirement 1–8 / Acceptance 1: depo, hizmet ve `/rule-set` uçları; kilitli
  kaydetme ve yayımlama, 409, 422, aynı içerikte 200, eşzamanlı iki yayımlamada tek sürüm, sürüm
  değişmezliği, kiracı yalıtımı ve `latest_published_rule_set` okuma işlevi. Kanıt:
  `app/backend/tests/integration/test_rule_set_api.py`.
- [x] Task 4 — Requirement 9 / Acceptance 2: kaynak dosyanın kopyası ve veri göçü
  `202609260002`; boş, dolu ve bozuk kopya durumları. Kanıt:
  `app/backend/tests/integration/test_rule_import_migration.py`,
  `test_rule_set_api.py::test_imported_file_is_version_one_for_both_roles`, `scripts/db.sh validate`.
- [x] Task 5 — API sözleşmesi / Acceptance 1: `specs/openapi/dwhcodereview-api.yaml` ve üretilmiş ön
  yüz tipleri. Kanıt: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [x] Task 6 — Requirement 4 (409 iletisi), 10, 11 / Acceptance 3: Kurallar ve "Yayımlanmış
  kurallar" sayfaları ile Vitest testleri. Kanıt: `app/frontend/src/pages/RulesPage.test.tsx`
  (arama, taşıma, silme, ekleme kimliği, "Kaydedilmedi", yayımlamadan önce kaydetme, 409 iletisi ve
  yenileme, 8.000 karakter), `app/frontend/src/pages/PublishedRulesPage.test.tsx` (iki rolde salt
  okunur, eski sürüm, sürüm yokken ileti), `app/frontend/src/components/layout/AppShell.test.tsx`
  (Kurallar menüsü ve sayfası inceleyiciye kapalı).
- [x] Task 7 — Requirement 1, 4, 5, 8, 9, 10, 11 / Acceptance 4: yerel PostgreSQL ve tarayıcıyla
  L2 doğrulaması. `e2e/sql-review/01-rules-and-roles.mjs` 2026-09-26'da Chromium'da geçti: kural
  yöneticisi içe aktarılmış sürüm 1'i görür (ilk koşumda 1 → 2), kural ekler, kaydeder, yayımlar ve
  yeni sürümü görür; inceleyici Kurallar sayfasını göremez, taslak ucundan 403 alır, yeni sürümü
  "Yayımlanmış kurallar"da salt okunur görür. Senaryo eklediği kuralı kaldırıp yeniden yayımlar.
- [ ] Task 8 — Requirement 7 / Acceptance 5: koşumun sürümü başta sabitlediğinin gerçek koşumla
  gözlenmesi. [Nesne incelemesi](../003-object-review/PRD.md) uygulanınca yapılır; açık.
