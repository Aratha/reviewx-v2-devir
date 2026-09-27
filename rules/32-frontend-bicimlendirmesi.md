---
id: "32-frontend-bicimlendirmesi"
title: "Erişilebilir arayüzleri anlamsal belirteçlerden ve paylaşılan temel bileşenlerden oluştur"
scope: frontend
priority: 50
trigger: path-match
applies_to:
  - "app/frontend/src/components/**"
  - "app/frontend/src/pages/**"
  - "app/frontend/src/globals.css"
gate: "frontend-test.yml"
application_modes:
  - separated-web
---

# Ön yüz stil sistemi

Üretilmiş temel bileşenleri ve anlamsal tasarım belirteçlerini kullan. Birincil, soluk, yıkıcı, kenarlık,
yüzey ve ön plan gibi tema niyetlerini gelişigüzel sabit renkle veya yinelenen bileşen `CSS`'iyle
değiştirme. Yeni görsel değeri tekrarlamadan önce belirteçleri merkezi olarak genişlet.

Sayfaları paylaşılan yerleşim, başlık, kart/bölüm, form, tablo/liste, yükleniyor, boş, hata ve bildirim
kalıplarından oluştur. Genişlik, aralık, yazı ölçeği ve bilgi yoğunluğunu en yakın teslim edilmiş
yüzeyle tutarlı tut. Dar ve geniş görünüm alanlarını destekle; sabit ekran boyutuna veya piksel konumuna
bağlı yerleşimlerden kaçın.

Doğal `HTML` anlamsal öğelerini tercih et. Her etkileşim görünür üzerine gelme/odak/devre dışı durumunu,
erişilebilir adı, klavye davranışını ve açık işaretçi ipucunu içerir. Yerel olmayan tıklanabilir öğe;
eşdeğer rol, odaklanabilirlik ve `Enter`/`Space` işlemesi sağlamalıdır; mümkünse düğme veya bağlantı
kullan. Fareyle tıklanabilen tablo satırı ayrıca klavyeyle erişilebilir birincil eylem sunar.

İşletmenden iç veritabanı kimliği yazmasını asla isteme. İlişkiler için aranabilir ve etiketli seçim
yüzeyi kullan. Kritik kurulum akışları etkisiz denetim sunmak yerine ön koşulları ve devre dışı
durumları açıklamalıdır.

Erişilebilirlik ağacı doğrulamaları anlamı ve durumu korur. Ekran görüntüleri; yerleşim, tema ve uyarlanan
davranış gibi görsel özellikler için ayrılmıştır.
