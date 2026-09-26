# Görevler — llm-connection

[Plan](plan.md) belgesinden türetildi. Kanıt: `scripts/quality-gate.sh all` 2026-09-26'da yerel
Compose yığınında geçti. Bu, arka uç kapsamı için L1 (otomatik testlerden geçti) kanıtıdır;
kurum ağındaki gerçek LLM ucuna çağrı yapılmadı.

- [x] Task V1 — Requirement 10, 14 / Acceptance 2: `llm_call_summary` tablosu ve koşum silinince
  bağın boşalması; göç `202609260001`. Kanıt: `app/backend/tests/integration/test_data_model.py`.
- [x] Task V2 — Requirement 1: tipli ayar alanları ve aralıkları. Kanıt:
  `app/backend/tests/unit/test_config.py`, `python3 scripts/check-config-sync.py`.
- [x] Task 1 — Requirement 1, 2 / Acceptance 1: adres çözümü, adres doğrulaması ve başlangıç
  denetimi (`nonprod`'da `https` olmayan adres veya boş model süreci durdurur). Kanıt:
  `app/backend/tests/unit/test_llm_adapter.py` (`test_chat_url_follows_the_source_rule`,
  `test_unsafe_urls_are_rejected`), `app/backend/tests/unit/test_integration_settings.py`.
- [x] Task 2 — Requirement 3, 4, 5, 6, 8, 9 / Acceptance 1: `LlmChatPort` ve `httpx` uyarlayıcısı;
  kendi test CA'sı olan gerçek TCP sahte sunucuyla SSE, düz JSON, `api_v1_chat`, 200 + `error`,
  500, yönlendirme, askıda kalma ve deneme sayısı, bağlantı reddi, 4 MiB, güvenilmeyen sertifika,
  genel adrese çözülen ad, bağlantı anında değişen adres, bağlanılan karşı adres, ortam vekili,
  `User-Agent`/`Authorization`, iptal ve ilerleme sıklığı. Politika ve TLS redlerinde sahte sunucu
  istek gövdesi almaz. Kanıt: `app/backend/tests/unit/test_llm_adapter.py`.
- [x] Task 3 — Requirement 6, 7 / Acceptance 2: 3 Nesne × 10 kurallı koşumda koşum sınırı, iki
  eşzamanlı koşumda süreç geneli sınır, iptal edilen koşumun bekleyen çağrılarının başlamaması.
  Kanıt: `app/backend/tests/unit/test_llm_adapter.py`.
- [x] Task 4 — Requirement 10, 11, 12, 14 / Acceptance 2: özet kaydı, `llm.call` olayının yalnız
  izinli alanları, yazma hatasında incelemenin sürmesi, `/llm-calls` listesi ve tek kayıt, sınır
  doğrulaması, kiracı yalıtımı, işaret dizesinin log, veritabanı ve API yanıtında bulunmaması,
  90 günlük saklama işi ve iki kopyada tek silme. Kanıt:
  `app/backend/tests/integration/test_llm_call_summaries.py`,
  `app/backend/tests/unit/test_llm_call_recorder.py`.
- [x] Task 5 — Requirement 4, 13 / Acceptance 1, Acceptance 3: `/llm-connection` uçları, `local`
  kaydında ağ politikası ve adres denetimi, anahtarın yanıt ve logda bulunmaması, `nonprod`'da
  `PUT` 404 ve yalnız biçim/model; OpenAPI ve üretilmiş tipler. Kanıt:
  `app/backend/tests/unit/test_llm_connection_service.py`,
  `app/backend/tests/integration/test_connection_settings_api.py`,
  `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [ ] Task 6 — Gözlemlenebilirlik: `dwhcodereview_llm_*` ölçümleri ve içerik taşımayan çağrı izi
  (trace). Arka uçta ölçüm/iz kitaplığı veya dışa aktarıcı yok; yeni bağımlılık için sahip kararı
  ve kabul kaydı gerekiyor. Açık, engelli.
- [ ] Task 7 — Requirement 13 / Acceptance 3: LLM bağlantısı sayfası ve Vitest testleri. Bu
  teslimde ön yüz işi kapsam dışı tutuldu; açık.
- [ ] Task 8 — Acceptance 4 ve Acceptance 5: kurum ağından Decision 3 ucuna gerçek inceleme ve
  `nonprod` ayarlarıyla yerel L2 doğrulaması. [Nesne incelemesi](../003-object-review/PRD.md) ve
  Task 7 gerekli; açık.
