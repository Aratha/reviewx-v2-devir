---
id: "33-frontend-yerellestirmesi"
title: "Birden çok dil yapılandırıldığında kullanıcıya dönük her dizgeyi kataloğa taşı"
scope: frontend
authority: mandatory
priority: 60
trigger: path-match
applies_to:
  - "app/frontend/src/**"
  - "docs/**"
gate: "locale-key-parity"
application_modes:
  - separated-web
---

# Ön yüz yerelleştirmesi

Arayüz dilleri `.kt-scaffold/answers.yml` içindeki `locales` listesinden gelir; listedeki ilk dil
birincil dildir. Yeni proje, `--diller` veya `locales` ile başka bir seçim yapılmadıkça tek dille
(`en`) kurulur. Dil listesini her zaman bu dosyadan oku; sabit bir dil çifti varsayma.

Dil sayısı kuralın proje kodu için ne kadar bağlayıcı olduğunu belirler:

- Tek dil yapılandırıldığında proje kodundaki kullanıcıya dönük metin doğrudan o dilde yazılabilir.
- Birden çok dil yapılandırıldığında aşağıdaki katalog koşulları proje kodunun tamamı için
  zorunludur. `locales` listesine ikinci dili ekleyen değişiklik, o ana kadar doğrudan yazılmış
  metni de kataloğa taşır.
- Şablonla gelen platform ekranları (giriş, ana sayfa, oturum yükleniyor durumu, yetkisiz erişim ve
  bulunamadı ekranları) dil sayısından bağımsız olarak her zaman kataloğu kullanır. Böylece sonradan
  dil eklemek yalnız çeviri işi olur.

Katalog kullanılan yerde kullanıcıya dönük her dizge, yerelleştirme bağlamının `t` işleviyle
oluşturulan ileti anahtarıdır. Buna başlık, etiket, düğme, yer tutucu, doğrulama iletisi,
boş/yükleniyor/hata durumu, bildirim, erişilebilir ad ve belge başlığı dahildir. Bileşen içinde
yedek anlatıyı doğrudan kodlama. Anahtar olarak İngilizce cümleler değil `<domain>.<surface>.<meaning>`
gibi açıklayıcı, hiyerarşik adlar kullan.

Her dil için `src/locales/<locale>.json` altında aynı anahtar kümesine sahip bir katalog tut.
Kataloglar tek kayıt defterinden, `src/contexts/IntlContext.tsx` içinden yüklenir. Dil eklemek;
`locales` listesini, yeni kataloğu ve kayıt defteri girdisini tek değişiklikte günceller.
`src/locales/locale-key-parity.test.ts` her katalogda aynı anahtarların bulunduğunu ve kodda
kullanılan her anahtarın her katalogda karşılığı olduğunu denetler; eksik çeviri bu kapıyı
başarısız kılar, geliştirme sırasında sessizce birincil dile dönülmez.

Değişken yerleştirme ve yerel ayarı gözeten sayı, tarih, saat, para birimi ve çoğul biçimlendirmesi
kullan. Parçaları birleştirerek çevrilmiş cümle oluşturma. Yerelleştirme kelimesi kelimesine
değiştirme değil, kendi dilinde doğal anlatımdır ve tek belge tutarlı biçimde tek anlatı dili
kullanır.

Dil API çıktısını veya önbelleği etkilediğinde çözümlenmiş dili paylaşılan istemci üzerinden gönder
ve önbellek anahtarına dahil et. Tarayıcı doğrulaması etkilenen her yapılandırılmış dili kapsar veya
hangi dilin çalıştırıldığını tam olarak raporlar.
