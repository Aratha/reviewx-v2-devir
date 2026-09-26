---
id: "54-bagimlilik-guncelligi"
title: "Sabitlenmiş sürümleri güvenlik bulgularına karşı güncel tut"
scope: governance
authority: mandatory
priority: 54
trigger: always
applies_to: []
gate: "security-scan.yml"
---

# Bağımlılık ve imaj güncelliği

Teknoloji profili hangi teknolojilerin kullanıldığını; bu kural, sürümlerin nasıl ilerlediğini sabitler.
Sürüm sabitlemeleri — paket `manifest`'i, özetle kilitlenmiş gereksinim dosyası, kaydedilmiş kilit
dosyası ve özete sabitlenmiş imaj — geliştirici veya ajan tercihi değil yönetişim sahipli tabandır.

Onaylı güvenlik tarayıcısının (`Trivy`, `Semgrep`, `Dependabot`, `OSV` sorgusu veya iç kural kümesi)
sabitlenmiş sürüm için bulgu üretmesi inceleme zorunluluğu doğurur. Kararı yalnız `CVSS >= 7` gibi
tek bir eşikle verme. CVSS önemini; CISA KEV durumu, EPSS olasılığı, exploit olgunluğu,
reachability/VEX kanıtı, düzeltme varlığı, varlık ve veri kritiklik seviyesi ile birlikte değerlendir.
Erişilebilir veya bilinen istismarı bulunan yüksek etkili açık için en yakın kabul edilmiş düzeltmeyi
hemen al; güvenlik düzeltmesi aşağıdaki olgunluk aralığından muaftır. Düzeltme bulunmuyor ya da geçiş
hemen mümkün değilse sahipli, gerekçeli, süreli ve telafi edici kontrollü istisna gerekir. Ajanın
ağsız değerlendirmesini canlı CVE, KEV, EPSS veya paket kayıt deposu kanıtı sayma.

Başka nedenle yeni sürüm almak, sürümün en az 30 gündür genel erişime açık olmasını gerektirir.
Değişiklikle kayıt defteri/yukarı akış yayın tarihi ve güvenlik kaynaklı yükseltme için duyuru
tanımlayıcısı kaydedilir. Aralığı karşılamak için sabitlemeyi düşürmek yasaktır; mevcut yeni sabitleme,
kendisinden sonraki uygun sürüm hazır olana kadar kalır. Yönetişim sahibi kaydedilmiş olgunluk aralığı
istisnası verebilir; istisna ve uyumluluk kanıtı değişiklikle birlikte taşınır.

`dependency-admission.json` yürütülebilir kayıttır. İncelenmiş envanter özeti; her doğrudan paket
yetkisini, özete sabitlenmiş `OCI` kimliğini ve `commit`'e sabitlenmiş iş akışı eylemini kapsar. Yetki
değişikliği özeti geçersiz kılar. Desteklenen proje iskeleti seçeneği üretilen yetki yüzeyini değiştirirse
kayıt, her tam çeşit için ayrıca incelenmiş özet taşır ve denetleyici `.kt-scaffold/answers.yml` ile
mevcut dosyaların anlaştığını kanıtlar. Üretim sırasında yeni özet hesaplayıp kendi kendini kabul
etmez. `scripts/check-dependency-admission.py`, yönetişim sürüm kanıtını veya açık uyumluluk istisnasını
kaydedip yeni envanteri inceleyene kadar hata durumunda kapalı çalışır. `Dependabot` ve `OSV`
bulguları öneri/kanıt girdisidir; sabitlemeyi tek başına yeniden yazamaz veya kabul edemez.

Yükseltmeler projelere proje iskeleti güncellemesini yeniden oynatma veya yönetişim güncelleme kanalıyla
ulaşır. Tarayıcıyı susturmak için üretilmiş kilidi/özeti elle düzenleme; `manifest`, kilit ve kabul edilmiş
yapıt özetleri tutarlı kalsın diye yetki dosyasından yeniden üret.

## Kilide bağlı alt paket kabulü

`package-inheritance:locked-transitive-20260917` uyarınca kabul edilmiş ana paketin,
aynı adayın kilit dosyasında tam sürüm ve yapıt özetiyle bağlı alt bağımlılıkları için
ayrıca paket adı onayı aranmaz. Sorunsuz alt paket için yeniden insan onayı isteme;
yalnız tarihsel `approved_packages` listesinde bulunmamasını engel sayma.

Kabul edilmiş kök, gerçek bağımlılık yolu, manifest/kilit tutarlılığı, tam sürüm,
yapıt özeti ve aynı aday bağı doğrulanmalıdır. Salt kilitte bulunma, isim benzerliği
veya extras seçimi tek başına bu kanıt değildir. Eksik/geçersiz bağda
`BLOCKED_INCOMPLETE` bildir; kabul varsayma. Doğrudan eklenmiş paketin bağımsız kabulü
zorunludur; başka kökten ulaşılabilmesi bunu kaldırmaz. Geliştirme kapsamındaki kökün
kabulü üretim kullanımına genişlemez. Vendored bileşen için de aynı kanıt gerekir.

Yalnız paket adı izni devralınır. Güvenlik bulguları, lisans politikası/dal seçimi ve
bildirim yükümlülükleri, indirme kaynağı, yayın yaşı ve `dependency-admission.json`
kontrolleri korunur. Ana lisansı alt paketin lisansı sayma; Alpine indirme alanına
veya JSZip lisans dalına bu kararla izin verme. `not-admitted` sınırı değişmez.

Güncellemede değişen paket/sürüm/özet, bağımlılık bağlantısı, kaynak ve lisansları
incele; değişmemiş ağacın paket adı kabulünü yeniden isteme. Mevcut açık güvenlik veya
lisans bulgusunu değişmemiş olması nedeniyle yok sayma. Karar ve kanonik otorite bağı
eksikse eski listeden örtük genel izin üretme.
