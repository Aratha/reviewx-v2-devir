# Plan — llm-connection

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.1.1). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uçtur. `technology-profile.yml#llm_orchestration` gereği LLM
erişimi uygulama portu ile altyapı uyarlayıcısı arasında ayrılır; Decision 5 uyarınca uyarlayıcı
doğrudan `httpx` kullanır ve `requirements-llm.in` (LangChain) etkin değildir.

## Veri modeli ve ayarlar

Şema yetkisi `app/backend/app/domain/models/llm_call.py`; `llm_call_summary` tablosu göç
`202609260001` ile oluşur. Sütunlar Requirement 10'dur; istem, SQL, yanıt metni ve başlık için
sütun yoktur; saklama işi için `started_at` dizini vardır (Requirement 14). Requirement 1'deki
`DWHCODEREVIEW_LLM_*` tipli ayarları `app/backend/app/core/config.py` içindedir.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Port ve kurallar | `app/backend/app/domain/llm.py` (`LlmChatPort`, `LlmRunSession`, `LlmCallSlot`, `LlmCallRecorder`, adres çözümü ve doğrulaması, hata iletileri, 4 MiB ve ilerleme sınırları) | Decision 1, Requirement 2, 3, 9 |
| Ağ politikası ve TLS | `app/backend/app/infrastructure/llm/network.py` | Requirement 4, 5 |
| Uyarlayıcı | `app/backend/app/infrastructure/llm/http_chat.py`, `response_text.py` (kaynaktaki `services/llm_review.py` aktarım bölümü) | Requirement 3, 5–9 |
| Özetler | `app/backend/app/infrastructure/repositories/llm_call_summary_repository.py`, `app/backend/app/services/llm_call_summary_service.py` | Requirement 10–12, 14 |
| Ayarlar hizmeti | `app/backend/app/services/llm_connection_service.py`, `app/backend/app/services/startup_checks.py` | Requirement 1, 2, 4, 13, Decision 4 |
| API | `app/backend/app/api/llm/router.py`, `app/backend/app/schemas/llm/contracts.py`, `app/backend/app/api/integrations.py` | API sözleşmesi, Requirement 11, 13 |
| Yaşam döngüsü | `app/backend/app/main.py` (başlangıç denetimi, saklama işi) | Requirement 1, 14 |
| İmaj | `app/backend/certs/corporate-inference-root.crt`, `app/infra/install-backend-system-packages.sh`, iki Dockerfile | Requirement 5 |
| Bağımlılık | `app/backend/requirements.in` (`httpx==0.28.1`, `httpcore==1.0.9`), kilitli `requirements*.txt`, `dependency-admission.json` | Decision 5 |
| Gözlemlenebilirlik | `app/backend/app/infrastructure/llm/http_chat.py` (`llm_attempt`), `app/backend/app/services/llm_call_summary_service.py`, `app/backend/app/core/telemetry.py` | Gözlemlenebilirlik, Requirement 10 |
| Ön yüz | `app/frontend/src/pages/LlmConnectionPage.tsx`, `app/frontend/src/pages/LlmCallsPage.tsx` | Requirement 11, 13 |

## Uygulama kararları

- Port kullanımı: bir İnceleme koşumu `open_run()` ile tek HTTP istemcisi ve koşum sınırını açar;
  her çağrı `slot()` ile önce koşum, sonra süreç geneli yer bekler (iptal edilen bekleyiş çağrı
  başlatmaz). İki parçalı analizin iki çağrısı aynı yerde sırayla yapılır. Yer içindeki `chat()`
  yeniden denemeleri de içerir ve `LlmChatResult` (metin veya sabit sınıf, HTTP kodu, kullanım)
  döner. Uç veya model yoksa `LlmNotConfigured` yükselir. Portu kullanan inceleme hizmetleri
  [nesne](../003-object-review/PRD.md) ve [metin](../004-script-review/PRD.md) incelemesi
  PRD'lerindedir.
- Adres çözümü kaynaktaki kuralı `urllib.parse` üzerinden tek yardımcıyla uygular. Kullanıcı
  bilgisi, parça, `http`/`https` dışı şema, geçersiz port veya boşluk içeren adres reddedilir;
  `http` yalnız `local`'dedir (başlangıçta ve kayıtta).
- Ağ politikası iki yerde uygulanır: her denemeden önce ad çözülür ve bütün adresler özel ağ
  aralığında olmalıdır; bağlantı katmanında (`httpcore` ağ arka ucu) ad yeniden çözülür, yalnız
  denetlenmiş adrese bağlanılır ve bağlanılan karşı adres yeniden denetlenir. Red, TLS'ten ve
  herhangi bir istek baytından önce olur. Aralıklar: 10/8, 172.16/12, 192.168/16, 127/8,
  169.254/16, 100.64/10, ::1, fe80::/10, fc00::/7 (IPv4 eşlemeli IPv6 dahil).
- TLS `DWHCODEREVIEW_LLM_CA_BUNDLE` verilmişse yalnız o dosyayla, verilmemişse imajın sistem güven
  deposuyla (kurum kök CA'sı eklenmiş) doğrulanır; ana makine adı denetimi açıktır. Ortam vekili
  (`trust_env=False`) kullanılmaz, yönlendirme izlenmez (3xx `upstream_status`). Gövde ve akış
  4 MiB'ı aşarsa `response_too_large`.
- Süreler: okuma ayardan, bağlantı `min(120, okuma)`; ad çözümü bağlantı süresiyle sınırlıdır.
  Yalnız `timeout` sınıfı (bağlantı veya okuma zaman aşımı) yeniden denenir; bekleme
  `min(1,5 × 2^n, 12)` saniyedir.
- Hata sınıfları: `httpx` zaman aşımları `timeout`; TLS kökenli bağlantı hatası `tls_error`; diğer
  bağlantı hataları ve çözülemeyen ad `connect_error`; politika reddi `network_policy_denied`;
  2xx dışı kod `upstream_status`; çözülemeyen/boş/`error` alanlı gövde veya protokol hatası
  `invalid_response`; iptal `cancelled`. İptalde deneme `cancelled` özetiyle kaydedilir ve iptal
  yeniden yükseltilir.
- İlerleme olayı `LlmStreamProgress` yalnız kural kimliği, belirteç ve karakter sayısı taşır;
  bir çağrı için iki olay arası en az 0,2 saniyedir. Son sayılar inceleme PRD'lerinin `rule_done`
  olayında verilir.
- Her deneme için bir `llm.call` log olayı ve bir `llm_call_summary` satırı yazılır (Requirement 10
  alanları; koşum kimliği dışarıya `public_id` ile verilir). Yazma hatası incelemeyi durdurmaz,
  `llm_call_summary.write_failed` yalnız hata türünü taşır.
- Saklama işi arka uç sürecinde başlangıçta ve 6 saatte bir çalışır; `pg_try_advisory_xact_lock`
  ile aynı anda tek kopya siler, 90 günden eski satırları fiziksel olarak siler ve
  `llm_call_summary.retention_run` olayını yazar. Toplu silme ucu yoktur.
- `local`'de ayar değişikliği süreç içi `LlmConnectionStore`'dadır; kayıt çözülen adresi ağ
  politikasına göre denetler, uymayan veya çözülemeyen adresi 422 `network_policy_denied`,
  biçimsiz adresi 422 `llm_url_invalid` ile reddeder. `nonprod`'da `PUT` yoktur (404) ve `GET`
  yalnız biçim ve modeli döner.

## Dağıtım bağımlılığı

Sır olmayan değerlerin chart'a taşınması ve RunAI adresine daraltılmış ağ çıkış kuralı
[Kubernetes teslim PRD'sinindir](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md);
bu teslimde `helm/` değişmedi.

## Doğrulama komutları

- `python3 scripts/check-config-sync.py`, `python3 scripts/check-dependency-admission.py`
- `scripts/quality-gate.sh backend` ve devir için `scripts/quality-gate.sh all`
- `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 1, 2 | Acceptance 1, Acceptance 5 | Task V2, Task 1 |
| Requirement 3, 5, 6, 8, 9 | Acceptance 1 | Task 2 |
| Requirement 4 | Acceptance 1 | Task 2, Task 5 |
| Requirement 7 | Acceptance 2 | Task 3 |
| Requirement 10, 11, 12, 14 | Acceptance 2, Acceptance 3 | Task V1, Task 4, Task 7 |
| Requirement 13 | Acceptance 3, Acceptance 5 | Task 5, Task 7 |
| Gözlemlenebilirlik (ölçüm ve iz) | — | Task 6 |
| Acceptance 4 | Acceptance 4 | Task 8 |
