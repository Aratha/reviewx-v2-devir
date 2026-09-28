---
name: kt-spesifikasyon
description: Yalnız yeni bağımsız yetenek için yol haritasına bağlı taslak PRD oluştur; küçük uygulamada mevcut kabul edilmiş PRD yetkisini yeniden kullan. /kt-spesifikasyon çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-spesifikasyon

Yalnız yeni bağımsız yetenek için yol haritasına bağlı taslak PRD oluştur; küçük uygulamada mevcut kabul edilmiş PRD yetkisini yeniden kullan.

Argümanlar: alan, bağımsız yetenek, amaç ve ayrıntı modu.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet spesifikasyon çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.
