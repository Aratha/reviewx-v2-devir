---
id: "43-sema-yorumlari"
title: "Veritabanı anlamını profiline özgü açıklamalarla sorgulanabilir tut"
scope: schema
priority: 70
trigger: path-match
applies_to:
  - "schema/**"
  - "app/backend/**/domain/**"
gate: "schema-comment-check"
application_modes:
  - separated-web
---

# Şema açıklamaları

Kalıcı tablo/sütun anlamını, veritabanı açıklama üretebiliyorsa seçilen şema yetkisine; üretemiyorsa
incelenmiş `SQL` göçüne koy. Açıklama karar tarihçesini değil mevcut davranışı açıklar.

Şunlar için açıklama zorunludur:

- her tablonun amacı ve sahibi olan sınırlı bağlam;
- her tanımlı değer ve varsa kod yansıması dahil sıralı değerler ve bit alanları;
- hedef ve sahiplik anlamı dahil tablolar/sınırlar arası referanslar;
- bilinen kod yollarının yazdığı `props` anahtarları;
- uygulamanın şu an tüketmediği uyumluluk alanları;
- açık olmayan benzersizlik, yazıcı, saklama veya yaşam döngüsü sözleşmeleri.

Açık tip gerçeklerini yorumlama. Üç nokta yazma veya sıralı değer uydurma. Kod yansıması yoksa açıkça
belirt ve yansıma eklenene kadar yetkiyi tek tanım olarak tut.

Şimdiki zaman kullan. Genel şema açıklamasına olay, tarih, göç numarası, plan bölümü, ticari ortak,
kaynak ürün veya sektöre özgü örnek koyma. Alan söz varlığına yalnız kabul edilmiş alan `PRD`'si
sahip olduktan sonra izin verilir.

Açıklama değişikliklerini üretilmiş göçte incele ve göç ettirilmiş veritabanına karşı doğrula;
veritabanına ulaşmayan yalnız kaynak yorumu bu kuralı karşılamaz.
