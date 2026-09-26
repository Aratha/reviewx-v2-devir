# Plan — script-review

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli

Yeni tablo yoktur; metin koşumu [object-review](../003-object-review/PRD.md) tablolarını kullanır.
Şema bunu kısıtlarla güvenceler: `review_run.kind = 'script'` iken `object_count = 1`, `label` yalnız
metin koşumunda ve en çok 200 karakterdir; yapıştırılan metin tek `review_run_object` satırının
`source_sql` sütunudur (Requirement 3, 9). Metin sınırı ayarı `DWHCODEREVIEW_REVIEW_MAX_SQL_CHARS`
tipli ayarlardadır (Requirement 2).
