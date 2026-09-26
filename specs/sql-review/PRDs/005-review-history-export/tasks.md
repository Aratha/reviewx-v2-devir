# Görevler — review-history-export

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti. Bu, arka uç kapsamı için L1 (otomatik testlerden geçti) kanıtıdır.

- [x] Task V1 — Requirement 4, 5, 6 / Acceptance 1: yanlış pozitif sütunları, fiziksel silme
  basamaklaması, `finished_at` dizini ve saklama süresi ayarı. Kanıt:
  `app/backend/tests/integration/test_data_model.py`, `app/backend/tests/unit/test_config.py`.
- [x] Task 1 — Requirement 1–6, 10 / Acceptance 1: gerçek PostgreSQL ile liste, başlık ve sayılar,
  sayfalama ve `422`, kapsam ve rol başına `401`/`403`/`404`, kiracı yalıtımı, ayrıntıda SQL metni
  olmaması, işaret tekrarı, kural sonucu işaret kuralı, silme kapsamı ve LLM özetinin bağının
  boşalması, süren koşumda `409`, "tümünü sil" kapsamı, saklama işinin yalnız süresi dolanı silmesi
  ve kilitte tek kopya, saklanmış metni olmayan koşumda `409`; `OpenAPI` kayıtlı yapıtla aynı.
  Kanıt: `app/backend/tests/integration/test_review_history_api.py`,
  `scripts/export-openapi.sh --check`.
- [x] Task 2 — Requirement 7–9 / Acceptance 2: CSV'nin kaynaktaki `buildReviewResultsCsv` çıktısıyla
  bayt bayt aynı olması (kaynak işlev Node ile aynı girdide çalıştırılıp beklenen baytlar
  sabitlendi), formül koruması, hata satırı; SQL yorum bloğundaki her satır numarasının dosyadaki
  gerçek satırı göstermesi (nesne ve metin koşumu, CRLF ve baştaki boş satırlar), yanlış pozitifin
  yorumdan çıkması. Kanıt: `app/backend/tests/unit/test_review_export.py`,
  `app/backend/tests/integration/test_review_history_api.py`.
- [ ] Task 3 — Requirement 3, 4, 5, 10, 11 / Acceptance 3: geçmiş sayfası, onaylar, indirme
  düğmeleri, pasif SQL düğmesi ve Vitest testleri. Ön yüz sonraki teslimdedir; açık.
- [x] Task 4 — Gözlemlenebilirlik: `dwhcodereview_review_exports_total{format}`,
  `dwhcodereview_review_history_retention_deleted_runs_total` ve
  `dwhcodereview_review_history_retention_last_success_timestamp_seconds` ölçümleri ile günlük
  olayları. Kanıt: `app/backend/tests/integration/test_telemetry_signals.py`
  (`test_exports_and_retention_record_their_metrics`), `scripts/quality-gate.sh all`; saklama işinin iki ölçümü
  yerel gözlemlenebilirlik yığınında Prometheus'ta gözlendi.
- [ ] Task 5 — Acceptance 4, Acceptance 5: iki tarayıcı ve iki kullanıcıyla L2 (gerçek ortamda
  doğrulama). Task 3 gerekli; açık.
