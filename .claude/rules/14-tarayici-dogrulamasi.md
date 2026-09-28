<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - app/frontend/**
  - e2e/**
  - specs/**/PRDs/**
---

# Arayüz davranışını gerçek tarayıcı ve kaydedilmiş senaryolarla doğrula

# Tarayıcı doğrulaması

Arayüzü etkileyen değişiklik hem otomatik ön yüz testlerini hem de çalışan yığına karşı canlı geçişi
gerektirir. `SPA` ve API'yi birlikte sunan yapılandırılmış ters vekil kökenini kullan; gerçek API'ye
vekillik edemiyorsa ön yüz geliştirme sunucusuna karşı doğrulama yapma.

Gerçek oturum açma formunu kullan. Belirteç enjekte etme veya kimlik doğrulamayı atlama. Platform ve
üretilmiş alan test verisi kurulumu, uygulama `super_admin` hesabını kullanabilir; atlama yoluyla geçiş
kusurunu gizleyeceği için yetkilendirmeye özgü kabul noktaları ayrıca olağan rol kullanmalıdır.

Her kabul noktası için:

1. Gerçek rotaya git.
2. Erişilebilirlik ağacını oku.
3. Dönen öğe referansları üzerinden etkileşim kur.
4. Beklenen rolü, erişilebilir adı, durumu, gezinmeyi, hatayı, yüklenmeyi veya boş sonucu doğrula.
5. Hata sonrasında kodu değiştirmeden önce konsol ve ağ kanıtını incele.

Sabit uyku yerine somut durumu bekle. Ekran görüntüsünü yalnız erişilebilirlik ağacının ifade
edemediği görsel özellikler için kullan. Yerel ayara duyarlı davranışı etkilenen her yapılandırılmış
yerel ayarda doğrula veya yerel ayarı açıkça sabitleyip raporla.

Kalıcı senaryolar `e2e/<domain>/` altında bulunur, paylaşılan test düzenini kullanır, `finally` yolunda
genel API'ler üzerinden temizlik yapar ve `e2e/QUALITY_MANIFEST.md` içine bir yüzey satırı kaydeder.
Tam olarak neyin çalıştırıldığını ve gözlemlendiğini raporla; derleme geçişi canlı kanıt değildir.
