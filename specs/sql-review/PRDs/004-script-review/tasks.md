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
- [ ] Task 3 — Requirement 2, 11 / Acceptance 3: "SQL betiği incelemesi" sayfası, sayaç, sınır
  iletisi, sabit not ve Vitest testleri. Ön yüz sonraki teslimdedir; açık. `OpenAPI` ve üretilmiş
  tipler bu teslimde güncel (`scripts/generate-types.sh --check`).
- [ ] Task 4 — Acceptance 4, Acceptance 5: onaylı LLM ucuyla tarayıcıda L2 (gerçek ortamda
  doğrulama). Task 3 ve kurum ağı gerekli; açık.
- [x] Task 5 — Gözlemlenebilirlik: metin incelemesinin `kind=script` koşum ve kural ölçümleri;
  etiket ve metin hiçbir ize veya ölçüme girmez. Kanıt:
  `app/backend/tests/integration/test_telemetry_signals.py`
  (`test_a_script_review_counts_as_script_and_keeps_its_label_and_text_out`),
  `scripts/quality-gate.sh all`.
