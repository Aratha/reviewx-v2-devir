---
name: kt-guncelle
description: Yerel proje iskeleti güncellemesini çatışmaları koruyarak uygula. /kt-guncelle çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-guncelle

Yerel proje iskeleti güncellemesini çatışmaları koruyarak uygula.

Argümanlar: hedef dizin ve isteğe bağlı yanıt değişiklikleri.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet guncelle çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.

Güncellemeyle gelen dosyaları aynı güncellemeyle gelen kurallara göre değerlendir, projenin henüz güncellenmemiş mevcut kurallarına göre değil: güncelleme yeni kuralları ve onlara uyan dosyaları birlikte getirir. Projenin açmadığı isteğe bağlı bir şablon (örneğin kapalı veritabanı bölümü) projede hiçbir şeyi değiştirmez; bunu kural çatışması sayma.

Sapan tek bir yönetilen dosyayı kaydedilmiş doğru hâline döndürmek güncelleme değildir; `rules/04-politika-catismasi.md` içindeki geri alma adımını uygula.
