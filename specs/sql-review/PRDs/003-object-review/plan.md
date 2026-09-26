# Plan — object-review

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli

Şema yetkisi `app/backend/app/domain/models/review.py`; tablolar `schema/alembic/versions/202609260001_directory_login_and_review_data_model.py` (göç `202609260001`) ile oluşur.

- `review_run`: `public_id`, `tenant_id`, `owner_user_id`, `kind` (`object` = nesne,
  `script` = metin), `label` (yalnız metin koşumunda), `rule_set_version_id` (yayımlanmış sürüme
  kısıtlayıcı dış anahtar), `object_count` (1–50), `status` (`running`, `completed`, `failed`,
  `cancelled`, `interrupted`), `started_at`, `finished_at`, `error_code`, `error_message`
  (Requirement 3, 4, 16).
- `review_run_object`: sıra, veritabanı, şema, ad, tür kodu, tür, nesne hatası, `parse_warning`,
  en çok 120.000 karakter `source_sql` (Requirement 8, 12, 16).
- `review_rule_result`: `public_id`, sıra, kural kimliği, grup, durum (`PASS`, `FAIL`,
  `NOT_APPLICABLE`, `UNKNOWN`), önem (`HIGH`, `MEDIUM`, `LOW`), karar dayanağı, en çok 500
  karakter açıklama ve kod parçası, satır referansı (Requirement 13).
- `review_finding`: `public_id`, kural sonucuna bağlı sıra, kural kimliği, önem, en çok 4.000
  karakter açıklama ve kod parçası, satır referansı (Requirement 13).

Ayarlar: iki parça eşiği, metin sınırı ve koşum başlatma hız sınırının penceresi ile sayısı
(`DWHCODEREVIEW_REVIEW_*`) tipli ayarlarda tanımlandı (Requirement 8, 9, 18); kullanımları bu PRD'nin
görevlerinde kalır.
