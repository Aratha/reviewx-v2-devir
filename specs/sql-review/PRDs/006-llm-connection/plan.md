# Plan — llm-connection

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli ve ayarlar

Şema yetkisi `app/backend/app/domain/models/llm_call.py`; `llm_call_summary` tablosu `schema/alembic/versions/202609260001_directory_login_and_review_data_model.py` (göç `202609260001`) ile
oluşur. Sütunlar Requirement 10'dur: `public_id`, `started_at`, `review_run_id` (boş olabilir,
`ON DELETE SET NULL`), nesne etiketi, kural kimliği, `part_index` (boş = tek parça, 1, 2), deneme
sırası, istek biçimi, model, uç ana makine adı, akış, sonuç sınıfı, HTTP kodu, süre, belirteç ve
karakter sayıları. İstem, SQL, yanıt metni ve başlık için sütun yoktur. Saklama işi için
`started_at` dizini vardır (Requirement 14). Requirement 1'deki `DWHCODEREVIEW_LLM_*` tipli ayar
alanları ve aralıkları tanımlandı; `nonprod` başlangıç doğrulaması, port ve uyarlayıcı bu PRD'nin
görevlerinde kalır.
