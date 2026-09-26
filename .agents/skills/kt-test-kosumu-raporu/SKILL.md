---
name: kt-test-kosumu-raporu
description: Bir test paketi, tarayıcı, doğrulama, senaryo, teşhis veya ürünün kendi üzerinde denenmesi koşumunun sonucunu sabit şablon olmadan, sade dille ve gözlenen kanıtıyla anlat.
---

<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
# Test koşumu raporu

# Koşum sonucu anlatımı

Test paketi, tarayıcı geçişi, doğrulama taraması, senaryo grubu, teşhis veya iç kullanım koşumundan
sonra sonucu okuyucunun sorusuna göre sade dille anlat. Sabit rapor şablonu, zorunlu grup etiketi,
`M1..Mn` madde numarası veya boş bölüm için `— yok` satırı kullanma. Okur teknik değildir; terimleri
ve komutları `02-iletisim-tarzi` kuralındaki sade dil sözleşmesine göre anlat.

- İlk cümle sonucu veya kök nedeni söyler. Teşhis ya da soru yanıtında rapor kurmadan doğrudan
  cevap ver.
- Gerçekten koşulan komutları ve gözlenen başarılı, başarısız ve atlanan sayılarını belirt. Koşulmayan
  test türü için sayı uydurma veya `0` yazma; koşulmadığını söyle.
- Tamamlanma iddiasını gözlenen kanıta dayandır; sayısız veya kanıtsız "tamamlandı" deme.
- Düzeltilmemiş kusuru, kapsanmayan durumu ve okuyucu kararı gerektiren noktayı açıkça yaz; aksiyonu
  kimin alması gerektiğini belirt.
- Koşum sırasında depo, yapılandırma, ortam veya test verisinde yaptığın değişikliği belirt.
- Başlık, liste veya tabloyu yalnız içerik gerektirdiğinde kullan. Aynı bilgiyi özet ve ayrıntı olarak
  iki kez yazma; uzun çıktıyı gömmek yerine dosya veya komut göster.

`done_report` öneri niteliğindedir; desteklenmeyen kanıt iddiasını sessizce düşürmez, iddia edilen ve
desteklenen seviyeyi açıkça yazar.

Ortak yönetişim kayıtlarını doğrularken ayrı kanıt ver: geçici ortak kökte yazım ve
şema/binding testleri; ikinci bir OS kullanıcısının başkasının kaydını silememe testi; gerçek native
istemci hook gözlemi. Bunlardan biri diğerinin yerine geçmez. Ana/subagent LLM erişim hatalarını,
gözlenen retry'ları ve eksik native event/turn bilgisini raporla. Ham model çıktısı veya error
body'yi rapora kopyalama; kayıt başvurusu, test sonucu ve sınırlı hata sınıfı kullan.