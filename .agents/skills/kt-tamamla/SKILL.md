---
name: kt-tamamla
description: İddia edilen kanıt seviyesini güncel snapshot ve bileşime bağlı kanıtla karşılaştır. /kt-tamamla çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-tamamla

İddia edilen kanıt seviyesini güncel snapshot ve bileşime bağlı kanıtla karşılaştır.

Argümanlar: değişiklik özeti, iddia edilen seviye; L0 — Yazıldı, henüz çalıştırılmadı; L1 — Otomatik testlerden geçti; L2 — Gerçek istemci/ortamda doğrulandı; L3 — Sorumlu sahibi kabul etti.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet tamamla çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.
