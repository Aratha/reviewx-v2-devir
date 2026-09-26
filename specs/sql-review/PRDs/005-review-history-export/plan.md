# Plan — review-history-export

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli

Bu PRD'nin sütunları `review_rule_result` ve `review_finding` üzerindedir: `false_positive`,
`false_positive_changed_by`, `false_positive_changed_at` (Requirement 4). Koşum silindiğinde koşum
nesneleri, kural sonuçları, bulgular ve saklanan SQL metni `ON DELETE CASCADE` ile aynı işlemde
kalıcı silinir (Requirement 5); LLM çağrı özetinin koşum bağı `ON DELETE SET NULL` ile boşalır.
Saklama işi için `review_run.finished_at` üzerinde dizin vardır (Requirement 6). Saklama süresi ayarı
`DWHCODEREVIEW_REVIEW_HISTORY_RETENTION_DAYS` (1–365, varsayılan 90) tipli ayarlardadır. Göç:
`schema/alembic/versions/202609260001_directory_login_and_review_data_model.py` (göç `202609260001`).
