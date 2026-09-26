# Plan — rule-management

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli

Şema yetkisi `app/backend/app/domain/models/rule_set.py`; tablolar `schema/alembic/versions/202609260001_directory_login_and_review_data_model.py` (göç `202609260001`) ile oluşur.

- `rule_set_draft`: kiracı başına tek kayıt (`tenant_id` tekil), `revision` değişiklik sayacı
  (Requirement 4), `next_rule_number` ilk serbest kural numarası (Requirement 3); son değiştiren ve
  zaman iskeletin `updated_by`/`updated_at` sütunlarıdır.
- `rule_set_draft_rule`: taslak kuralı; doğal anahtar (`rule_set_draft_id`, `rule_code`), grup
  (`critical`/`normal`), grup içi sıra, en çok 8.000 karakter metin, `requires_metadata`
  (Requirement 2). Kaydetmede taslaktan çıkan kural yazılımsal silinir; kullanılmış kimlik
  görünür kalır (Requirement 3).
- `rule_set_version`: `public_id`, kiracı içinde tekil `number`, `published_at`,
  `published_by_user_id` (içe aktarımda boş), `source` (`arayuz`/`ice-aktarim`), `content_sha256`
  (Requirement 5, 8). Uygulamada güncelleme ve silme yolu yoktur.
- `rule_set_version_rule`: sürümle birlikte eklenen ve değişmeyen kurallar.
- Kural kimliği biçimi `^Kural(0[1-9]|[1-9][0-9]+)$` veritabanı kısıtıdır.

Bu dalgada yapılmayan: Requirement 9 içe aktarım veri göçü ve kaynak dosya kopyası.
