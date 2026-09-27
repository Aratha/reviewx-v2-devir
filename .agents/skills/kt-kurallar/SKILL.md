---
name: kt-kurallar
description: İlgili kuralların gövdelerini yüklemeden listesini getir. /kt-kurallar çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-kurallar

İlgili kuralların gövdelerini yüklemeden listesini getir.

Argümanlar: kapsam, yol veya tetikleyici.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet kurallar çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.
