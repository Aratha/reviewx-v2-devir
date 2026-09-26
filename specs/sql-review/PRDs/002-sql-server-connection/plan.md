# Plan — sql-server-connection

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Veri modeli ve ayarlar

Bu PRD PostgreSQL'e tablo eklemez (Veri ve geçiş). Requirement 1'deki tipli ayar alanları
`app/backend/app/core/config.py` içinde tanımlandı ve `app/backend/.env.example` ile yerel Compose
ortamına eklendi (`DWHCODEREVIEW_MSSQL_*`; parola sır olarak yalnız kabuk ortamından gelir). Alan
sınırları (port, süreler, eşzamanlılık) başlangıçta doğrulanır. `nonprod` başlangıç doğrulaması,
bağlantı dizesi yardımcısı, port ve uyarlayıcı bu PRD'nin görevlerinde kalır.
