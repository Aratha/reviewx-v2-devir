# Plan — object-review

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.0.0). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uç ve `React`/`Vite` ön yüzdür. Gerçek SQL Server ve onaylı LLM
ile tarayıcı doğrulaması açık görevdir.

## Veri modeli ve ayarlar

Şema yetkisi `app/backend/app/domain/models/review.py`; tablolar göç `202609260001` ile oluştu.

- `review_run`: `public_id`, kiracı, başlatan kullanıcı, tür (`object` = nesne, `script` = metin),
  metin koşumunun etiketi, sabitlenen kural sürümü (yayımlanmış sürüme kısıtlayıcı dış anahtar),
  nesne sayısı (1–50), durum (`running`, `completed`, `failed`, `cancelled`, `interrupted`),
  başlangıç ve bitiş zamanı, hata kodu ve iletisi (Requirement 3, 4, 16).
- `review_run_object`: sıra, veritabanı, şema, ad, tür kodu, görünen tür, nesne hatası,
  `parse_warning` ve en çok 120.000 karakter `source_sql` (Requirement 8, 12, 16).
- `review_rule_result` ve `review_finding`: Requirement 13 alanları.
- Göç `202609260003` (`schema/alembic/versions/202609260003_review_result_severity_and_line_reference.py`):
  kural sonucunun önemi yalnız `FAIL` sonucunda doludur (`severity_only_for_fail` kısıtı; eski
  satırlarda `FAIL` dışındaki önem boşaltılır) ve iki tablodaki satır referansı 500 karaktere
  genişler, çünkü çözümleyici virgüllü satır listesini 500 karaktere kadar tutar (Requirement 11,
  13).

Ayarlar mevcuttur: `DWHCODEREVIEW_REVIEW_MAX_SQL_CHARS` (120.000; tablo sınırının üstüne
çıkamaz), `DWHCODEREVIEW_REVIEW_TWO_PART_THRESHOLD_CHARS` (45.000),
`DWHCODEREVIEW_REVIEW_RATE_LIMIT_WINDOW_SECONDS` (60) ve
`DWHCODEREVIEW_REVIEW_RATE_LIMIT_MAX_REQUESTS` (30). Yeni ayar yoktur.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Alan tipleri | `app/backend/app/domain/review.py` (kural, kural sonucu, bulgu, nesne sonucu, meta veri kaynağı), `app/backend/app/domain/sql_server.py` (`is_allowed`, sabit iletiler) | Requirement 13, 20 |
| İstem ve bölme | `app/backend/app/services/review_prompts.py` (sistem ve kullanıcı istemi, `L001` numaralama, iki parça, parça notları, meta veri notu) | Requirement 6, 8, 9 |
| Çözümleme ve birleştirme | `app/backend/app/services/review_response_parser.py` | Requirement 9–11 |
| Kural başına inceleme | `app/backend/app/services/review_engine.py` (`TextReviewer`) | Requirement 7, 9, 12, 17 |
| Koşum | `app/backend/app/services/review_run_service.py` (`ReviewRunService`, `ReviewExecution`, `ReviewRunRegistry`, `interrupt_stale_runs`) | Requirement 3–7, 14–16, 18 |
| Katalog listeleri | `app/backend/app/services/review_catalog_service.py` | Requirement 1, 2 |
| Kalıcılık | `app/backend/app/infrastructure/repositories/review_repository.py` | Requirement 16 |
| Hız sınırı | `app/backend/app/core/review_throttle.py` | Requirement 18 |
| API | `app/backend/app/api/reviews/router.py`, `app/backend/app/schemas/reviews/contracts.py`, `app/backend/app/schemas/reviews/events.py`, `app/backend/app/api/integrations.py`, `app/backend/app/api/router.py` | API sözleşmesi, Requirement 14 |
| Yaşam döngüsü | `app/backend/app/main.py` (açılışta yarıda kalan koşumlar, kapanışta süren koşumlar) | Requirement 16 |
| Sözleşme | `specs/openapi/dwhcodereview-api.yaml`, `app/frontend/src/types/api.d.ts` (üretilmiş) | Acceptance 4 |
| Ön yüz | `app/frontend/src/pages/ObjectReviewPage.tsx`, `app/frontend/src/components/review/` (nesne tablosu, canlı ve sonuç pencereleri), `app/frontend/src/contexts/ReviewSessionContext.tsx`, `app/frontend/src/lib/eventStream.ts` (`fetch` ile akış), `app/frontend/src/lib/reviewProgress.ts`, `app/frontend/src/services/catalog.ts`, `app/frontend/src/services/reviews.ts` | Requirement 1–3, 14, 15, 19 |

## Uygulama kararları

- Kaynak davranış taşıma: istemler, `L001` numaralama, bölme, parça notları ve meta veri notları
  kaynaktaki `backend/services/llm_review.py` ile bayt bayt aynıdır. Çözümleme ve birleştirme
  işlevleri kaynaktaki karşılıklarıyla 9.000 rastgele model yanıtında aynı sonucu verdi (geçici
  karşılaştırma, depoya eklenmedi). İki bilinçli fark: en eski yanıt biçimindeki (kökte çıplak
  dizi) bulgular, depo yalnız `KuralNN` kabul ettiği için incelenen kuralın kimliğini alır;
  durum ve önem alan tipleridir.
- Meta veri: sabitlenen sürümde işaretli kural varsa nesne başına bir kez alınır; alınamazsa
  işaretli kurallara "Bağımlılık veya kolon özeti alınamadı; yalnızca SQL metnine güven." notu
  gider. Boş özet kaynaktaki notu, metin koşumu kaynaktaki metin notunu kullanır (Requirement 6).
- Eşzamanlılık: koşum 006'daki `LlmChatPort` üzerinden tek oturum açar; her kural çağrısı bu
  oturumun yerini alır, iki parçalı analizin iki çağrısı aynı yerde sırayla yapılır. Nesneler ve
  kurallar aynı anda başlatılır; sınırı port uygular (Requirement 7, Decision 4).
- Uyarılar: kural uyarıları "[KuralNN] uyarı" biçiminde birleşir; aynı LLM hatasını alan kurallar
  tek satırda toplanır ("[Kural01, Kural03] LLM sunucusuna bağlanılamadı."); eski biçim uyarıları
  gösterilmez; metin kesildiyse "Metnin yalnız ilk 120.000 karakteri incelendi." en başa gelir
  (Requirement 8, 12). LLM hatası kuralı `UNKNOWN` yapar ve yalnız 006'nın sabit Türkçe iletisini
  taşır (Requirement 17).
- Koşum kaydı: kontrol sırası kimlik → rol → hız sınırı → istek → LLM yapılandırması → kural
  sürümü. Koşum satırı ve seçim satırları (veritabanı, şema, ad, tür) ilk olaydan önce tek
  işlemde yazılır; sonuçlar, bulgular ve incelenen metin yalnız başarıyla biten koşumda tek
  işlemde yazılır. Böylece durdurulan veya hata alan koşum geçmişte başlığıyla görünür ama kısmi
  sonuç ve metin taşımaz (Requirement 15, 16).
- Akış öncesi ek hata: LLM ucu veya modeli yapılandırılmamışsa koşum başlamaz, `503
  llm_not_configured` döner. Koşum sırasında uç kaybolursa koşum `failed` ve `error` olayı
  `llm_not_configured` olur.
- Canlı ilerleme: yanıt `text/event-stream`; her olay tek `data:` satırında `phase` alanlı JSON'dur
  (`ReviewStreamEvent` birleşimi OpenAPI'de belgelenir). Olaylar kaynaktakine ek olarak `kind`
  (`object`/`script`) taşır; `object_error` `code` ve `message` taşır. 15 saniye olay yoksa
  `: ping` yorum satırı gelir (olay değildir; vekil zaman aşımına karşı). `complete` olayı
  `run_id` ve sonuç listesini taşır: sonuçta kural sonuçları (`rule_results`) ve bulgular
  (`findings`) `public_id` kimlikleriyle gelir, böylece canlı pencere yanlış pozitif ucunu
  doğrudan kullanır (Requirement 19); `source_sql` yalnız bu olayda vardır.
- İptal: koşum ayrı bir görevde çalışır. Yanıt nasıl biterse bitsin (durdur düğmesi, kopan
  bağlantı, sunucu kapanışı) görev iptal edilir: bekleyen çağrı başlamaz, süren çağrı kapanır,
  koşum `cancelled` (kapanışta `interrupted`) olur ve sonuç yazılmaz. Süreç açılışında `running`
  kalmış koşumlar `interrupted` ve `review_interrupted` koduyla işaretlenir; veritabanına
  ulaşılamazsa açılış durmaz. Chart tek kopya çalıştırır (`replicaCount: 1`); birden çok kopyada
  bir kopyanın açılışı ötekinin süren koşumunu kesilmiş sayar (açık risk).
- Hız sınırı süreç içidir, kiracı ve kullanıcı başına kayan penceredir; nesne ve metin
  incelemesi aynı sayacı kullanır, reddedilen istek `Retry-After` taşır (Requirement 18).
- Günlük: `review_run.started`, `review_run.completed`, `review_run.cancelled`,
  `review_run.failed` olayları `run_id`, kullanıcı `public_id`, tür, sürüm, nesne ve kural sayısı,
  süre ve `UNKNOWN` sayısını; `review_run.object_error` yalnız veritabanı, şema, ad ve kodu taşır.
  SQL, kod parçası, meta veri, etiket ve model yanıtı yazılmaz.

## Dağıtım bağımlılığı

Göç `202609260003` dağıtımdaki göç işiyle uygulanır. Ayarların chart değer dosyasında
belgelenmesi, SSE için ingress okuma süresi ve tamponlama ayarı
[Kubernetes teslim PRD'sinindir](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md);
bu teslimde `helm/` değişmedi. Yanıt `X-Accel-Buffering: no` ve `Cache-Control: no-cache` taşır.

## Doğrulama komutları

- `scripts/quality-gate.sh all`
- `scripts/db.sh validate`, `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`
- `python3 scripts/check-config-sync.py`, `python3 scripts/check-dependency-admission.py`,
  `python3 scripts/check-governance-drift.py`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 8–13 | Acceptance 1 | Task 1 |
| Requirement 6, 7, 9, 12, 17 | Acceptance 2 | Task 2 |
| Requirement 4, 5, 16 | Acceptance 2 | Task 3, Task V1 |
| Requirement 3, 14, 15, 18 | Acceptance 3 | Task 4 |
| Requirement 1, 2 | Acceptance 4 | Task 5 |
| Requirement 20, API sözleşmesi | Acceptance 4 | Task 6 |
| Requirement 1–3, 19 (ön yüz) | Acceptance 4 | Task 7 |
| Gözlemlenebilirlik (ölçüm) | — | Task 8 |
| Acceptance 5, Acceptance 6 | Acceptance 5, Acceptance 6 | Task 9 |
