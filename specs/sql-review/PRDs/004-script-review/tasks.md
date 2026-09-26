# Görevler — script-review

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti. Bu, arka uç kapsamı için L1 (otomatik testlerden geçti) kanıtıdır.

- [x] Task V1 — Requirement 3, 9 / Acceptance 2: metin koşumu kısıtları (tür, etiket, tek nesne,
  saklanan metin) göç `202609260001` içinde. Kanıt: `app/backend/tests/integration/test_data_model.py`.
- [x] Task 1 — Requirement 3–7, 12 / Acceptance 1: SQL Server portuna sıfır çağrı (her çağrısı hata
  veren katalogla), işaretli kurala metin notu ve işaretsize blok olmaması, etiket arındırma ve
  varsayılanı, sonuç kimliği, olay alanları ve LLM çağrı etiketi, eşik üstünde iki parçalı analiz.
  Kanıt: `app/backend/tests/integration/test_script_review_api.py`.
- [x] Task 2 — Requirement 1–3, 8–10 / Acceptance 2: boş metin, 120.000 ve 120.001 karakter, 201
  karakter etiket, eksik alan; akış öncesi `401`/`409`/`429` ve nesne incelemesiyle ortak sayaç
  (`app/backend/tests/integration/test_object_review_api.py`); iptal edilen koşumda metnin
  saklanmaması; metnin ve etiketin günlükte olmaması ve yalnız koşum nesnesinde saklanması.
  Kanıt: `app/backend/tests/integration/test_script_review_api.py`.
- [x] Task 3 — Requirement 2, 11 / Acceptance 3: "SQL betiği incelemesi" sayfası, sayaç, sınır
  iletisi, sabit not ve Vitest testleri. Kanıt: `app/frontend/src/pages/ScriptReviewPage.test.tsx`
  (düğme durumları, sayaç, 120.000/120.001 sınırı ve iletisi, sabit not, 200 karakter etiket, koşum
  sürerken kilit, tarayıcı deposuna yazılmaması), `app/frontend/src/contexts/ReviewSessionContext.test.tsx`
  (durdurma, "Yapıştırılan SQL" varsayılanı); `scripts/generate-types.sh --check`.
- [x] Task 4 — Requirement 2, 8 / Acceptance 5: 120.001 karakterlik metin tarayıcıda gönderilemez ve
  API'de `422 sql_text_too_long` alır; "Analizi durdur" sonrası koşum "iptal edildi" olur ve 5 saniyeden
  sonra başlamış LLM çağrı özeti yoktur. `e2e/sql-review/02-script-review-history.mjs` 2026-09-26'da
  Chromium'da, arka uç kabının içinde yalnız bu doğrulama için çalıştırılan yerel, OpenAI uyumlu yedek
  LLM ucuyla (`http://127.0.0.1:8765/v1`) geçti; bu uç onaylı kurum LLM'i değildir.
- [ ] Task 5 — Acceptance 4: onaylı LLM ucuyla tarayıcıda L2. Aynı akış (etiketli metin, canlı
  ilerleme, satır referanslı bulgu, sabit not, koşum kaydında sürüm ve etiket) Task 4'teki yedek uçla
  gözlendi; onaylı kurum LLM'i yerelden erişilebilir olmadığı için açık.
