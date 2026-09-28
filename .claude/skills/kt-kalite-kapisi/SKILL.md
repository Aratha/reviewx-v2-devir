---
name: kt-kalite-kapisi
description: Yerel kalite kapısını çalıştır veya kanıt akışını hazırla. /kt-kalite-kapisi çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-kalite-kapisi

Yerel kalite kapısını çalıştır veya kanıt akışını hazırla.

Argümanlar: aşama, kapsam, tarayıcı kanıtı ve yerel kod çalıştırma onayı.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet kalite-kapisi çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.
