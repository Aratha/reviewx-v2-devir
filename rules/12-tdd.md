---
id: "12-tdd"
title: "Davranışı kırmızı, yeşil ve yeniden düzenleme döngüsüyle geliştir"
scope: process
priority: 30
trigger: always
applies_to: []
gate: "quality_gate"
---

# Test odaklı geliştirme

Her davranış değişikliği için:

1. **Kırmızı:** eksik veya bozuk davranışta başarısız olan testi ekle.
2. **Yeşil:** kabul edilmiş `PRD`'yi karşılayan en küçük tam davranışı uygula.
3. **Yeniden düzenleme:** ilgili test paketi başarılı kalırken tasarımı iyileştir.

## Değişiklik-temelli koşum sıklığı

Test sıklığını ajanın tur sayısına değil değişikliğin riskine ve teslim noktasına bağla:

1. Her küçük kırmızı/yeşil/yeniden düzenleme adımında yalnız değişen davranışı hızla sınayan odaklı
   testi çalıştır.
2. Anlamlı bir kontrol noktasında değişiklikten etkilenen test paketinin tamamını çalıştır.
3. `git commit` veya `governed-review` öncesinde ilgili ürünün tam otomatik kapısını çalıştır ve ancak
   bu kapının eksiksiz sonucu güncel değişiklik kümesiyle eşleşiyorsa L1 iddia et.
4. L2'yi her mikro döngüde değil, gerçek istemci/ortam yeteneğinin sınanabildiği uygun teslim
   noktasında doğrula.
5. L3'ü yalnız sorumlu sahibin açık kararıyla kaydet; test koşumu sahip kararı üretmez.

Her ajan turunda tam test paketi veya E2E çalıştırmak zorunlu değildir. Önceki kanıt yalnız aynı
değişiklik ağacı, snapshot ve yetkili bileşim için güncelse yeniden kullanılabilir; değişiklik bu bağı
bozduğunda gereken en dar basamaktan yeniden başla.

Mevcut PRD yetkisinin yeniden kullanıldığı küçük düzeltmede odaklı test, exact `Requirement <n>` ve
`Acceptance <n>` başvurusu ile ilgili mevcut `tasks.md` izi mikro döngü için yeterlidir; sırf değişiklik
küçük diye yeni PRD oluşturma. Bu, commit veya `governed-review` öncesindeki tam ilgili L1 kapısını
kaldırmaz. Yeni risk/sözleşme sınırı tek satırda değişse bile önce gereken PRD yolunu tamamla.

Uygulama koreografisini değil gözlemlenebilir sözleşmeleri test et. Güven açısından kritik sınır,
uygulanabilir olduğunda gerçek veritabanını, dosya sistemini, `HTTP` uygulamasını veya aşağı akış
uyarlayıcısını kullanır. Sınırın sahtesi kullanılmak zorundaysa imza kısıtlı sahte kullan ve zorunlu/yasak
alanlar dahil üretilen kesin yapıyı sabitle. Yalnız tüketiciyle anlaşması için yazılmış sahte, yalancı
başarı kanıtıdır.

Başarılı yolu, doğrulama ve yetkilendirme hatalarını, kiracı yalıtımını, tekrarlandığında aynı sonucu
veren yeniden denemeyi, uygunsa yazılımsal silme davranışını ve düzeltmeyi gerektiren gerilemeyi kapsa.
Üretilmiş kod testleriyle aynı değişiklikte yayımlanır. Bir kapıyı geçmek için başarısız olan testi
zayıflatma, atlama veya silme.

Çatı davranışı yinelenen test gerektirmez. İş değişmezleri, profil uyarlayıcıları, sözleşme
üretimi, izin denetimleri ve katmanlar arası bağlantı test gerektirir.
