---
id: "52-uctan-uca-ozellik"
title: "Kabul edilmiş her yeteneği etkilenen tüm katmanlarda teslim et"
scope: quality
authority: mandatory
priority: 70
trigger: always
applies_to: []
gate: "done_report"
application_modes:
  - separated-web
---

# Uçtan uca yetenek tamamlanması

Kabul edilmiş `PRD`'yi, yanındaki `plan.md`/`tasks.md` dosyalarını, alan bağlamını, çözümlenmiş profili
ve en yakın tamamlanmış dikey kalıbı okuyarak başla. Atıf yapılan dosyaları güncel koda karşı doğrula.
Katmanı yalnız `PRD`, `N/A — <reason>` olarak işaretlediğinde atla.

Yetenek şu yüzeyleri etkiliyorsa onları bağımlılık sırasıyla tamamla:

1. kaydedilmiş şema yetkisi ve üretilmiş/incelenmiş göç;
2. kalıcılık/alan modeli veya profile eşdeğer yapı;
3. kiracı/`RBAC` değişmezlerini koruyan depo/uyarlayıcı ve uygulama hizmeti;
4. tipli API istek/yanıt/hata sözleşmesi ve bağımlılık bağlantısı;
5. profile özgü birim/tümleştirme testleri;
6. çevrimdışı `OpenAPI` dışa aktarımı ve kaydedilmiş sözleşme;
7. üretilmiş ön yüz API tipleri ve alan hizmeti;
8. yerelleştirilmiş sayfa/bileşen, rota, menü ve izin kapısı;
9. kabul ölçütlerine bağlı ön yüz testi ve kaydedilmiş tarayıcı senaryosu;
10. `PRD`'nin gerektirdiği yapılandırma, işçi, önbellek, gözlemlenebilirlik, `chart`, katman,
    `Secret` referansı ve genel belge etkileri.

Uyumluluğa duyarlı şema değişikliği için önce ekleme yapan dağıtım sırası kullan: uyumlu yapı ekle,
okuyucuyu/yazıcıyı dağıt, açık işlemle geçmiş veriyi doldur, davranışı değiştir, sonra eski yapıyı
yalnız ayrıca yetkilendirilmiş yıkıcı kapsam altında kaldır.

Bayat `OpenAPI`/tip, arka uç koruması olmayan rota, ortam yüzeyinde olmayan ayar, kayıtsız model/sağlayıcı,
çevrilmemiş dizge veya oluşturulamayan iş yüküyle devir yapma. `done_report` her eksik katmanı ve
gerçekten ulaşılan en yüksek kanıt seviyesini adlandırır.
