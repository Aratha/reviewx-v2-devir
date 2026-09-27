---
id: "50-kalite-kapisi"
title: "Devir öncesinde belirlenimci değişiklik sonrası kalite kapısını çalıştır"
scope: quality
authority: mandatory
priority: 50
trigger: always
applies_to: []
gate: "scripts/quality-gate.sh"
application_modes:
  - separated-web
---

# Değişiklik sonrası kalite kapısı

Geliştirme sırasında en dar ilgili kontrolleri, devir öncesinde `scripts/quality-gate.sh all` komutunu
çalıştır. Tam kapı seçilen profili kullanır ve şu sıradaki ilk hatada durur:

1. yapılandırma yüzeyi eşzamanlaması;
2. adı `_test` ile biten benzersiz, profile özgü `PostgreSQL` veritabanı oluşturulması;
3. vazgeçilebilir veritabanına profile özgü göç dağıtımı;
4. arka uç biçimlendirici/`lint` ve tip denetimleri;
5. `RUN_POSTGRES_INTEGRATION=1` ile arka uç birim ve canlı `PostgreSQL` tümleştirme test paketleri;
6. aynı test veritabanına karşı göç hedef durumu, uygulanan geçmiş ve sapma doğrulaması;
7. çevrimdışı `OpenAPI` dışa aktarımı ve kaydedilmiş sözleşme sapma denetimi;
8. ön yüz `lint`'i, üretim derlemesi, birim test paketi ve kaydedilmiş tip sapma denetimi;
9. yönetişim sapması ve dağıtım `chart`'larının oluşturulması.

Vazgeçilebilir veritabanı başarı, hata veya kesintide silinir. Tam kapı, yapılandırılmış uygulama
veritabanına asla göç uygulamaz. Daha dar `backend` kapsamı veritabanı oluşturmaz veya canlı `PostgreSQL`
testlerini açmaz; göç denetimleri yapılandırılmış veritabanını yazmadan inceler. Devir kanıtı için tam
kapıyı kullan.

Şema yetkisi veya göç değiştiğinde profile özgü göç doğrulama/durum/sapma denetimlerini çalıştır.
Ayar değiştiğinde yapılandırma eşzamanlamasını; teslimat dosyası değiştiğinde `chart`
sözleşmesi/hazırlığını; kod, bağımlılık, imaj veya `manifest` değiştiğinde güvenlik tarayıcısını
çalıştır. Arayüz değişiklikleri tarayıcı kuralını da gerektirir; tarayıcı geçişi derleme veya
birim testinin yerini almaz.

Üretilmiş yapıtlar kaydedilmiş sözleşmedir. Yeniden üret ve beklenmeyen farkta başarısız ol; sapma
adımını atlama veya üretilmiş çıktıyı elle yamalama. Hatayı gerçek komut ve gözlenen çıktıyla
raporla. Tüm kontrolleri geçen ağaç üretmek için ilgisiz, kullanıcı sahipli değişikliği düzeltme;
yalıt ve raporla.

Otomasyon yalnız üretilmiş kapının ürettiği `KT_GATE_SCOPE`, `KT_GATE_STEP` ve `KT_GATE_TESTS`
kayıtlarını tüketir. Bu kayıtları kaldırma, yeniden adlandırma veya insan odaklı anlatıdan üretme.

Yerel standart girdi/çıktı veya komut satırı arayüzü yürütmesi `local-executed` kökenini kaydeder ve
yalnız yürütmeyi gerçekten gözleyen aynı işlem çağrısında L1'i destekleyebilir. Repo içinde sonradan
okunan `.kt-scaffold/evidence.json` değiştirilebilir bir geçmiş kaydıdır; exact snapshot'la eşleşse
bile kendi beyanıyla L1/L2 otoritesi veya yeniden kullanılabilir tasdik oluşturmaz.
Akış yapabilen `HTTP` çağırıcısı iş istasyonunda kod çalıştıramaz: önce çalışma alanı ve kapı
özetlerine bağlı komut hazırla, tam komutu yerelde çalıştır, sonra işaret çıktısını dönen sınamayla
sonuçlandır. Bu kanıt `client-reported` kalır. `runner-attested` kaydı da exact artifact bağını
doğrulayan harici bir attestation çözümleyicisi yoksa yalnız bilgilendirme amaçlıdır. Böyle bir
çözümleyici bu sürümde yoktur; L2 eksik kanıtla türetilmez.

Atlanan ve kullanılamayan kanıtı koşum sonucunda açıkça belirt (`53-test-kosumu-raporu.md`).
