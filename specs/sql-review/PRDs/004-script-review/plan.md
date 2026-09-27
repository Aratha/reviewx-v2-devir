# Plan — script-review

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, Version 1.1.0). Proje kipi `separated-web`;
sabit yığın `python-fastapi` arka uçtur. Ortak inceleme davranışının planı
[object-review planıdır](../003-object-review/plan.md); bu plan yalnız farkları yazar.

## Veri modeli ve ayarlar

Yeni tablo yoktur; metin koşumu [object-review](../003-object-review/PRD.md) tablolarını kullanır.
Şema bunu kısıtlarla güvenceler: `review_run.kind = 'script'` iken `object_count = 1`, `label` yalnız
metin koşumunda ve en çok 200 karakterdir; yapıştırılan metin tek `review_run_object` satırının
`source_sql` sütunudur (Requirement 3, 9). Metin sınırı `DWHCODEREVIEW_REVIEW_MAX_SQL_CHARS`
ayarıdır (Requirement 2).

## Katmanlar ve dosyalar

| Katman | Dosyalar | Gereksinim |
|---|---|---|
| Koşum | `app/backend/app/services/review_run_service.py` (`start_script_review`, `_review_script`) | Requirement 1–5, 7–10 |
| Ortak inceleme | `app/backend/app/services/review_engine.py`, `review_prompts.py`, `review_response_parser.py` | Requirement 6, 12 |
| API | `app/backend/app/api/reviews/router.py` (`POST /script-reviews`, `get_script_review_service`), `app/backend/app/schemas/reviews/contracts.py` | API sözleşmesi |
| Ön yüz | `app/frontend/src/pages/ScriptReviewPage.tsx`; canlı ve sonuç pencereleri nesne incelemesiyle ortak | Requirement 2, 11 |

## Uygulama kararları

- Metin baştaki ve sondaki boşluklardan arındırılır; boşsa `422 sql_text_empty` ("SQL metni boş
  olamaz."), sınırı aşarsa `422 sql_text_too_long` ("SQL metni en çok 120.000 karakter
  olabilir."). Etiket arındırılır, boşsa "Yapıştırılan SQL" olur, 200 karakteri aşarsa `422
  label_too_long`. Hata gövdesi metni veya etiketi yinelemez (Requirement 1–3).
- Metin koşumunun hizmet bağımlılıkları SQL Server uyarlayıcısını içermez (`get_script_review_service`
  katalog portu istemez); inceleme SQL Server'a hiç bağlanmaz. İşaretli kurallar kaynaktaki metin
  notunu alır, diğer kurallara meta veri bloğu eklenmez (Requirement 5, 12).
- Olaylar `kind: "script"`, `database: ""`, `object_index: 0`, `objects_total: 1`,
  `schema: "sql"`, `type_code: "SCRIPT"`, `name` = etiket ve `object_label` = "<etiket> (SCRIPT)"
  taşır; `definition_fetch` ve meta veri olayları yoktur. LLM çağrı özetinin nesne adı da
  "<etiket> (SCRIPT)" olur (Requirement 4, 7).
- Sınırı aşan metin reddedildiği için metin koşumunda kesme olmaz; satır numaraları arındırılmış
  metne göredir. Arındırılmış metin başarıyla biten koşumda tek koşum nesnesinin `source_sql`
  değeri olarak yazılır; iptal edilen koşumda yazılmaz (Requirement 6, 8, 9).
- Hız sınırı nesne incelemesiyle aynı kullanıcı sayacıdır (Requirement 10).
- Günlükte etiket ve metin yoktur; koşum olayları metin uzunluğunu ve iki parçalı analiz
  kullanılıp kullanılmadığını (`sql_length`, `two_part`) taşır.

## Dağıtım bağımlılığı

Ingress istek gövdesi sınırı ve chart değer dosyası
[Kubernetes teslim PRD'sinindir](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md);
bu teslimde `helm/` değişmedi.

## Doğrulama komutları

- `scripts/quality-gate.sh all`
- `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`

## İzlenebilirlik

| Gereksinim | Kabul | Görev |
|---|---|---|
| Requirement 3–7, 12 | Acceptance 1 | Task 1 |
| Requirement 1–3, 8–10 | Acceptance 2 | Task 2 |
| Requirement 2, 11 | Acceptance 3 | Task 3 |
| Requirement 2, 8 | Acceptance 5 | Task 4 |
| Acceptance 4 | Acceptance 4 | Task 5 |
| Gözlemlenebilirlik (ölçüm) | — | Task 6 |
