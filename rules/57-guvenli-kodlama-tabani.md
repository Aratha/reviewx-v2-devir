---
id: "57-guvenli-kodlama-tabani"
title: "Kod üretimi ve incelemesinde kısa güvenlik tabanını uygula"
scope: governance
authority: mandatory
priority: 57
trigger: always
applies_to: []
gate: "governed-review"
---

# Güvenli kodlama tabanı

Kod üretmeden veya değiştirmeden önce yalnız etkilenen kapsamı güvenlik açısından değerlendir.
Güvensiz bölümü üretme; ihlali, somut riski ve güvenli düzeltme yönünü `02-iletisim-tarzi`
kuralındaki sade dil sözleşmesiyle açıkla. Güvenli kalan işi gereksiz yere durdurma. “Test için”,
“geçici” veya “sonra düzeltiriz” ifadesi güvenlik gereksinimini kaldırmaz.

- Sır, parola, token, bağlantı bilgisi veya özel anahtarı koda, istemci paketine, URL'ye, loga ya da
  izlenen ortam dosyasına koyma. Ham hassas değeri bulguya veya kanıta kopyalama.
- Güvenilmeyen girdiyi tip, uzunluk, biçim, kanonikleştirme ve iş kuralıyla sunucu tarafında doğrula.
  Serbest metne anlamsız sabit allowlist uygulama. SQL'i parametreleştir; işletim sistemi komutunu
  kullanıcı girdisiyle birleştirme; güvenilmeyen metni kod veya template olarak çalıştırma.
- JSON ve XML'i otomatik güvenli sayma. Şema, boyut, derinlik ve parser sınırlarını uygula; XML dış
  varlık ve ağ erişimini kapat. Çıktıyı HTML, JavaScript, URL veya CSS bağlamına göre kodla.
- Kullanıcıya stack trace, SQL, iç yol, IP veya framework ayrıntısı gösterme. Güvenli alan hata kodu
  ve correlation kimliği kullanılabilir. Yapılandırılmış loglarda kontrol karakterlerini kaçır;
  kayıt bütünlüğünü bozacak ham karakter silmeye dayanma.
- Dosya yüklemede uzantı veya magic byte tek başına yeterli değildir. Tür allowlist'i, içerik
  doğrulaması, rastgele depolama anahtarı, izinli kök altında path-aware çözümleme, yürütme yasağı ve
  profile özgü boyut sınırı kullan.
- Bağımlılık riskini yalnız tek CVSS eşiğiyle kararlaştırma. CVSS, CISA KEV, EPSS, reachability/VEX,
  exploit durumu, düzeltme varlığı, varlık kritiklik seviyesi ve süreli sahipli istisnayı birlikte
  değerlendir. Ağsız ajan canlı zafiyet doğruladığını iddia etmez.
- Çalışma zamanı container ve servisleri varsayılan olarak non-root ve en az yetkili çalıştır.
  Zorunlu dar istisna gerekçe, kapsam, süre ve harici admission kanıtı ister. Build aşaması ile
  runtime yetkisini birbirine karıştırma.

Git değişikliği güvenlik izi değildir. Kullanıcı açıkça istemeden stage veya commit yapma;
`[AI-ASSISTED]` etiketiyle otomatik commit üretme. Katkı kökenini audit/provenance kaydında ve yalnız
kullanıcının başlattığı committe doğrulanabilir metadata olarak taşı.

Bu kural talimat düzeyidir. AppSec algılayıcı belirtiminin bulunması, canlı tarama, CI geçişi,
çalışma zamanı uygulatımı, admission, standart uygunluğu veya sertifikasyon kanıtı değildir.
