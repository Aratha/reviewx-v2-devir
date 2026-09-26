# Görevler — object-review

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti. Bu, arka uç kapsamı için L1 (otomatik testlerden geçti) kanıtıdır;
gerçek SQL Server ve kurum içi LLM ile koşum yapılmadı.

- [x] Task V1 — Requirement 3, 4, 8, 13, 16 / Acceptance 2: koşum, koşum nesnesi, kural sonucu ve
  bulgu tabloları (göç `202609260001`); önemin yalnız `FAIL` sonucunda dolu olması ve 500
  karakterlik satır referansı (göç `202609260003`). Kanıt:
  `app/backend/tests/integration/test_data_model.py`.
- [x] Task V2 — Requirement 8, 9, 18: tipli ayar alanları. Kanıt:
  `app/backend/tests/unit/test_config.py`.
- [x] Task 1 — Requirement 8–13 / Acceptance 1: kaynaktaki `test_parse_review_response.py`
  testlerinin 11'i aynı girdi ve beklenen çıktıyla taşındı; eklenen altın testler `L012`,
  `L012–L015`, `line_numbers`, `line_number` ve kod parçasından satır çıkarımı, "ihlal değil"
  süzgeci, tek ve çok kurallı istekte boş `rule_code`, bilinmeyen kural kodu uyarısı, kural
  sonucu biçiminde geçersiz durum ve önem, iki parçada tek ve iki parça hatası, tekrar ayıklama,
  durum birleşimi ve uyarı birleştirmeyi kapsar. Kanıt:
  `app/backend/tests/unit/test_review_response_parser.py`.
- [x] Task 2 — Requirement 6, 7, 9, 12, 17 / Acceptance 2: kural başına çağrı ve sıra, meta verinin
  yalnız işaretli kurala gitmesi ve üç not, iki parça çağrı sayısı ve parça kimliği, ikinci
  parçanın özgün satır numarası, LLM hatasında sabit ileti ve tek satır uyarı, akış sayaçları;
  gerçek `httpx` uyarlayıcısı ve gerçek TCP sahte uçla koşum sınırının nesneler arasında ve süreç
  sınırının koşumlar arasında korunması. Kanıt: `app/backend/tests/unit/test_review_engine.py`.
- [x] Task 3 — Requirement 4, 5, 6, 16, 17 / Acceptance 2: sürüm sabitleme, koşum ve seçim
  satırları, tamamlanan koşumda sonuçlar ve incelenen metin, nesne hatası kodları, meta veri
  hatasında not, metin sınırında kesme ve uyarı, koşum sırasında LLM kaybında `failed`, açılışta
  `interrupted`, LLM çağrı özetlerinin koşuma ve parçaya bağlanması. Kanıt:
  `app/backend/tests/integration/test_object_review_api.py`.
- [x] Task 4 — Requirement 3, 14, 15, 18 / Acceptance 3: akış öncesi `401`, `403
  database_not_allowed`, `409 no_published_rule_set`, `422` (`selection_empty`,
  `too_many_objects`, `object_type_invalid`, `invalid_request`), `429 rate_limited` ve metin
  incelemesiyle ortak sayaç, `503 llm_not_configured`; 50 nesnenin kabulü; olay sırası; kopan
  bağlantıda 5 saniye içinde `cancelled`, yeni çağrı olmaması ve kısmi sonuç yazılmaması; günlükte
  SQL ve model metni olmaması. Kanıt: `app/backend/tests/integration/test_object_review_api.py`,
  `app/backend/tests/unit/test_review_throttle.py`.
- [x] Task 5 — Requirement 1, 2 / Acceptance 4 (arka uç): `/databases` ve
  `/databases/{database}/objects` sayfaları, metin, tür ve tarih süzgeçleri, `403`, `422`,
  `503`/`504` hata sınıfları. Kanıt: `app/backend/tests/integration/test_review_catalog_api.py`.
- [x] Task 6 — Requirement 20, API sözleşmesi / Acceptance 4 (arka uç): katmanlara bölme,
  `OpenAPI` ve üretilmiş ön yüz tipleri. Kanıt: `scripts/quality-gate.sh all` (`ruff`, `mypy`,
  `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`).
- [x] Task 7 — Requirement 1–3, 14, 15, 19 / Acceptance 4: inceleme sayfası, canlı pencere,
  "Analizi durdur", sonuç penceresi ve Vitest testleri. Kanıt:
  `app/frontend/src/pages/ObjectReviewPage.test.tsx` (sunucuda süzgeç, çoklu veritabanı seçimi,
  50 sınırı, SQL Server hatasında Türkçe ileti ve "Listeyi yenile"),
  `app/frontend/src/lib/eventStream.test.ts` (akış çözümleyici, parça sınırları, erken durma,
  kopma), `app/frontend/src/lib/reviewProgress.test.ts` (olay birleştirme),
  `app/frontend/src/contexts/ReviewSessionContext.test.tsx` (`fetch` akışı ve oturum başlığı,
  durdurma, kapanamayan canlı pencere, son olaysız kopma, akış öncesi 409/422/429/503),
  `app/frontend/src/components/review/ReviewResultsView.test.tsx` (sonuç, satır referansı, yanlış
  pozitif işareti). Yerel tarayıcıda SQL Server yokken sayfanın iletisi gözlendi
  (`e2e/sql-review/03-settings-objects-users.mjs`).
- [ ] Task 8 — Gözlemlenebilirlik: koşum ölçümleri. Arka uçta ölçüm kitaplığı yok; yeni bağımlılık
  için sahip kararı ve kabul kaydı gerekiyor. Açık, engelli.
- [ ] Task 9 — Acceptance 5, Acceptance 6: test SQL Server'ı ve onaylı LLM ucuyla tarayıcıda L2
  (gerçek ortamda doğrulama). Kurum ağı ve erişilebilir SQL Server gerekli; açık. Aynı canlı pencere,
  durdurma ve sonuç penceresi metin incelemesinde yerel yedek LLM ucuyla gözlendi
  ([script-review](../004-script-review/tasks.md) Task 4).
