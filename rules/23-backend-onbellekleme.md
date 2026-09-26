---
id: "23-backend-onbellekleme"
title: "Önbellek kullanımını kapsamı belirli, kanonik, yığılma güvenli ve vazgeçilebilir yap"
scope: backend
priority: 50
trigger: path-match
applies_to:
  - "app/backend/**/cache*"
  - "app/backend/**/services/**"
  - "specs/**/PRDs/**"
gate: "cache-contract"
application_modes:
  - separated-web
---

# Arka uç önbellek kullanımı

Platform tabanı yalnız yerel Compose'da `cache` profiline bağlı, varsayılan olarak kapalı bir `Redis`
yuvası sunar; arka uç ona bağımlı değildir, uygulama önbellek uyarlayıcısı veya önbellek çağrı
noktası içermez. İş alanı bunların ikisini yalnız kabul edilmiş `PRD`; önbelleğe alınan
işlemi, doğruluk sınırını, geçersiz kılma veya yaşam süresi politikasını ve kanıtı tanımladığında
getirebilir. Önbellek hiçbir zaman kayıt sistemi değildir; her değer yetkili kaynaktan yeniden
üretilebilmelidir.

Yapılandırılmış istek yükleri için:

1. Anlamsal eşdeğerleri normalleştir: değerlerin kenar boşluklarını temizle, yalnız anlam izin veriyorsa
   harf büyüklüğünü bir örnekle, küme benzeri listeleri sırala, tarihleri `UTC`'ye normalleştir ve açık
   varsayılanları uygula.
2. Belirlenimci alan, eşlem ve küme benzeri liste sıralamasıyla kararlı baytlara kanonikleştir.
3. Kanonik baytların kararlı kriptografik özetini hesapla.

Her anahtar, çıktıyı değiştiren tüm boyutları içerir: kiracı, izin kapsamı veya aktör, yerel ayar,
uygunsa saat dilimi/para birimi, API sürümü, sayfalama, sıralama, projeksiyon ve kanonik istek özeti.
Yetkilendirme farklılığı belirsizse aktör başına kapsamlandır.

Anahtar başına kilit, sınırlı bekleme/yeniden deneme, kilit süresi dolumu ve rastgele sapmayla kaçırma
fırtınasını önle. Önbellek işlemleri hata durumunda açık çalışır: kullanılamayan önbellek
başarımı düşürebilir ancak yetkili davranışı bozamaz veya engelleyemez. Kimlik doğrulama sırrını, ham
erişim belirtecini veya yetkilendirme kararını, onu geçerli kılan iddia/sürüm sınırı ötesinde asla
önbelleğe alma.

Testler anlamsal eşdeğer girdilerin aynı anahtarı paylaştığını, izin/kiracı çeşitlerinin
paylaşmadığını, eşzamanlı kaçırmada yalnız bir hesaplamanın kazandığını ve önbellek hatasının
yetkili yola geri döndüğünü kanıtlar.
