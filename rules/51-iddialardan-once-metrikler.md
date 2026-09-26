---
id: "51-iddialardan-once-metrikler"
title: "Başarım, doygunluk veya kök neden iddiasından önce ölç"
scope: quality
priority: 60
trigger: on-demand
applies_to:
  - "app/**"
  - "schema/**"
  - "helm/**"
  - "plans/**"
  - "specs/**"
gate: "review"
---

# İddia öncesi ölçüm

Güncel inceleme kanıtını okumadan darboğaz, doygunluk, `N+1` kalıbı, tükenmiş havuz, çalışma zamanı
gerilemesi, kapasite tavanı veya kök neden iddia etme. Böyle her ifade; ölçümü/sorguyu, gözlenen değeri,
zaman aralığını/zaman damgasını, ortamı ve tepe mi kararlı durum mu olduğunu belirtir. Bu kanıt yoksa
boyutun ölçülmediğini söyle.

Ölçüm disiplini:

1. Tepe, ortalama, yüzdelik ve anlık örnekleri ayır; biri diğerini kanıtlamaz.
2. Belirtiyle nedeni ayır. Bağıntı; mekanizmayı ve suçlanan katmanın kuyruk/ret/sınır kanıtını gerektirir.
3. Sert hata kanıtını kontrol et: durum dökümü, hata sayacı, yeniden başlatma, sonlanma nedeni,
   veritabanı hatası, kilit beklemesi ve ilgili günlükler.
4. Sunucu tarafı verisini istemci/vekil taşıma hatasından ve uygulama yanıtından ayır.
5. Yükün artışı/azalışı sırasındaki kısa hız aralıklarını kararsız say ve yük üreticisiyle
   çapraz denetle.
6. Genellemeden önce izin, kiracı, önbellek, istek yapısı ve dağıtım çeşitlerini karşılaştır.

Ölçümler ilgili katmanın hedefi sınırladığını göstermeden daha fazla kopya, büyük veritabanı,
havuz değişikliği, dizin veya önbelleği düzeltme olarak önerme. Başka biri gözlemi tekrarlayabilsin
diye sorguyu kaydet.
