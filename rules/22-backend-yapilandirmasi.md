---
id: "22-backend-yapilandirmasi"
title: "Tüm yapılandırmayı tek tipli ayarlar yüzeyinden geçir"
scope: backend
authority: mandatory
priority: 40
trigger: path-match
applies_to:
  - "app/backend/**"
  - "app/infra/**"
  - "helm/**"
gate: "configuration-sync"
application_modes:
  - separated-web
---

# Yapılandırma ve sırlar

Sabit `Python`/`FastAPI` arka ucu tek tipli ayarlar nesnesi sunar. Uygulama kodu yapılandırmayı yalnızca
bu nesne üzerinden okur; doğrudan süreç ortamı okumaları ayar yükleyicisi ve açık başlatma giriş
noktalarıyla sınırlıdır. Test geçersiz kılmalarını atlayan modül düzeyinde ayar anlık görüntüsü
oluşturma.

Her ortam anahtarı `.kt-scaffold/answers.yml` içinde kayıtlı ön eki kullanır. Örnek ön eki asla
doğrudan kodlama. Yeni ayar, aynı değişiklik tüm geçerli yüzeyleri güncelleyene kadar eksiktir:

1. tipli ayarlar bildirimi ve başlatma doğrulaması;
2. gerçek sır değil yer tutucu içeren `app/backend/.env.example`;
3. her tüketen hizmetin yerel `Compose` ortam bloğu;
4. `helm/<ürün-kısa-adı>/values.yaml` içindeki `backend.existingSecret` ile seçilen, önceden oluşturulmuş
   tek uygulama `Secret` sınırı.

Yapılandırma değişikliklerinden sonra `python3 scripts/check-config-sync.py` çalıştır. Kontrol, geçerli
anahtarları sabit yığın tipli ayarlarından türetir; ön eksiz veya yabancı ön ekli uygulama ortamı
anahtarlarını ve onaylı ayar yükleyicisi/başlatma sınırları dışındaki doğrudan süreç ortamı
okumalarını reddeder.

Kök Helm chart'ının tam olarak bir `values.yaml` dosyası vardır; yalnız `backend` ve `frontend`
bölümlerini taşır. İmaj yolu, etiket varsayılanı, sunucu adı ve `Secret` gibi dağıtım girdilerinin
sahibi `45-dagitim-hedefi` kuralıdır; bu kural onları yeniden tanımlamaz. Yapısal işleme testi gizli
olmayan sentetik değerleri komut satırından sağlar; ikinci bir değer dosyası veya ortam katmanı
üretmez.

Helm chart'ı, arka uçta `envFrom` üzerinden önceden oluşturulmuş `Secret`'a adıyla referans verir;
anahtar başına sır eşlemesi listelemez. Gizli malzeme; kaynak, örnek dosya, çizelge değeri, günlük,
üretilmiş yanıt veya proje iskeleti bildirimine asla girmez. `super_admin` başlatma parolası
etkileşimli olarak veya çağıran süreçten okunur, parola özeti saklamak için kullanılır ve atılır;
normal ayar değildir. Başlatma komutu yapılandırılmış kimlik için tekrarlandığında aynı sonucu verir,
açık `super_admin` yetkisini korur ve parolayı veya özetini asla yazdırmaz.

Zorunlu ayarları süreç başlangıcında doğrula. `URL`'leri dize birleştirme yerine tek güvenli
birleştirme/ayrıştırma yardımcısıyla oluştur. Ortama göre farklılaşan değeri dağınık uygulama
dallarında değil platformun ayrı dağıtım kabul girdisinde tut.
