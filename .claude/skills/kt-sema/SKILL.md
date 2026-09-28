---
name: kt-sema
description: Kabul edilmiş PRD için teknoloji profiline özgü migrasyon hazırlığını yap. /kt-sema çağrıldığında veya kullanıcı bu işlemi istediğinde kullan.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# /kt-sema

Kabul edilmiş PRD için teknoloji profiline özgü migrasyon hazırlığını yap.

Argümanlar: PRD yolu, değişiklik özeti ve migrasyon adı.

Bu bir yerel uygulayıcı işlemidir: geçerli çalışma alanını yerel ajan araçlarıyla inceleyip düzenle veya isteğe bağlı komut satırı aracı kuruluysa eşdeğer argümanlarla kt-iskelet sema çalıştır. İlke bağlamı için merkezi MCP yönetişim kataloğunu kullan; MCP'den dosya sistemi değişikliği bekleme. Zorunlu davranışları koru; çatışmaları, uyarıları ve eksik kanıtları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle bildir.
