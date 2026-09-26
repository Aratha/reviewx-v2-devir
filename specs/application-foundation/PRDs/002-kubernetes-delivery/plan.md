# Plan — kubernetes-delivery

[PRD](PRD.md) belgesinden türetildi. PRD'nin `Status: Accepted` değeri oluşana kadar uygulamaya geçmeyin.

## İzlenebilirlik

- Requirement 1 → Acceptance 1/Acceptance 2 → Task 1

## Şema göçü etkisi

Göç `202609260001` yalnız genişleticidir (Requirement 4): yeni tablolar, boş olabilen veya
varsayılanlı sütunlar ve mevcut satırların sağladığı kısıtlar ekler. Uygulama rolüne yeni tablolarda
DML yetkisi verilmesi (Requirement 3) chart içi PostgreSQL ve göç Job'u bu projeye alındığında bu
PRD'nin görevlerinde uygulanır; yerel Compose tek `app` rolüyle çalışır. Dizin CA bundle'ı
`app/backend/certs/nonprod-directory-ca.crt` olarak depodadır; imaja girmesi Requirement 9'dur.
