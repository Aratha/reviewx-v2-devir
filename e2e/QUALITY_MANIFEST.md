# Kalite bildirimi

| Yüzey | Senaryo | Kanıt |
|---|---|---|
| Platform kimlik doğrulaması | auth/01-super-admin-login.mjs | Korumalı yönlendirme, oturum açma, belirtecin yalnız bellekte tutulması, `HttpOnly` yenileme çerezi, başka kökenden yenilemenin reddi, kiracı ret/kabulü, yeniden yüklemede çerezle oturumun geri gelmesi, oturum kapatma ve kapanan oturumun yenilenememesi |
| Kurallar ve roller (sql-review kural yönetimi) | sql-review/01-rules-and-roles.mjs | Kural yöneticisi kural ekler, kaydeder ve yayımlar; inceleyici Kurallar sayfasını göremez, taslak ucundan 403 alır ve yeni sürümü salt okunur görür; `finally` kuralı kaldırıp yeniden yayımlar |
| SQL betiği incelemesi, geçmiş ve dışa aktarım | sql-review/02-script-review-history.mjs | 120.001 karakter reddi, canlı ilerleme, "Analizi durdur" ve durdurmadan 5 saniye sonra LLM çağrısı olmaması, satır referanslı bulgu, yanlış pozitif işareti, ikinci tarayıcıda geçmiş, CSV ve SQL indirme, ikinci inceleyiciye 404, kural yöneticisinin salt okunur görmesi, silme. `APP_E2E_LLM_BASE_URL` yoksa yalnız "yapılandırılmamış" reddi |
| Bağlantı sayfaları, nesne incelemesi hata durumu, kullanıcı yönetimi | sql-review/03-settings-objects-users.mjs | Yerelde düzenlenebilir SQL/LLM sayfaları, kaydetmeden bağlantı testi ve sabit hata iletisi, LLM çağrı listesi, inceleyiciye kapalı menüler ve 403, SQL Server yokken nesne sayfası iletisi, süper yöneticinin rol ve durum değiştirmesi, rol değişince oturumun kapanması, pasif hesap girişi |

Alan satırları yalnız kabul edilmiş PRD'ler tarafından eklenir.
