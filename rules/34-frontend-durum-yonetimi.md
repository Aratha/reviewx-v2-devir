---
id: "34-frontend-durum-yonetimi"
title: "Paylaşılan durumu küçük tut ve JWT/RBAC oturum anlamını eşzamanla"
scope: frontend
priority: 70
trigger: path-match
applies_to:
  - "app/frontend/src/contexts/**"
  - "app/frontend/src/hooks/**"
  - "app/frontend/src/lib/authStorage.*"
gate: "auth-contract"
application_modes:
  - separated-web
---

# Ön yüz durum yönetimi

Birden çok rota veya uzak bileşen aynı değere ihtiyaç duymadıkça bileşene yerel durum kullan. Bağlamları
konuya göre böl; taban, kimlik doğrulama/oturum ve yerel ayar bağlamı sağlar. Her bağlam tipli tüketici
kancasını dışa aktarır, sağlayıcı dışında kullanıldığında hata verir ve kararlı değeri ezberler.
İlgisiz alan durumları içeren uygulama genelinde tek bağlam oluşturma.

`AuthContext`, `/me` tarafından dönen `JWT` destekli geçerli oturumu temsil eder: aktörün genel kimliği,
etkin kiracı, roller, kanonik izinler veya belgelenmiş kısa kodlar ve açık `super_admin` bayrağı. Şema
başlangıç verisi, arka uç genişletmesi/koruması ve ön yüz yorumu anlaşmalıdır. Rolü/izni sahibi olan
tüm yüzeylerde ekle veya yeniden adlandır ve uyumu kimlik doğrulama sözleşmesi testiyle koru.

Ön yüz rota/menü kapıları kullanılabilirliği iyileştirir fakat yetki vermez. Doğru kaynak arka uçtur.
`super_admin` her uygulama rotasını gösterebilir; ancak bu bayrak veritabanı, kapsayıcı veya küme
ayrıcalığı anlamına gelmemelidir. Erişim belirteçlerini yalnız `authStorage` üzerinden sakla ve temizle;
asla günlükleme veya `URL` içine koyma.

Yalnız `31-frontend-api-butunlesmesi.md` tarafından tanımlanan, oturum süresi dolumunu kanıtlayan yanıtta
otomatik oturum kapatma yap. Ağ, vekil, yukarı akış ve ilgisiz yetkilendirme hatasında oturumu koru.

Eşzamanlı olmayan etkilerde bileşenin kaldırılması/anahtar değişikliği sırasında bayat tamamlanmayı iptal et
veya yok say. Bağımlılık dizileri kararlı tanımlayıcı içerir; her oluşturmada yüklemeyi yeniden tetikleyen
taze çeviri veya bildirim kapanımı ekleme. Yükleniyor, boş, hata ve başarılı durumlarını açıkça modelle.
