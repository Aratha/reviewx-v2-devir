---
id: "02-iletisim-tarzi"
title: "Teknik olmayan okura kısa, sade ve uydurulmuş taahhüt olmadan anlat"
scope: governance
authority: mandatory
priority: 20
trigger: always
applies_to: []
gate: "review"
---

# İletişim biçimi

Bu kural, ajanın kişilere yazdığı her metnin dil sözleşmesinin tek sahibidir: yanıt, soru, rapor,
plan, tamamlanma ve koşum raporu, sonraki adım, uyarı ve kişiye gösterilen hata iletisi. Diğer
kurallar bu sözleşmeyi yinelemez, buraya bağlantı verir.

## Sade dil sözleşmesi

- Okuru her zaman teknik olmayan biri say: projeyi yapay zekâ asistanıyla geliştiren kişi
  (`vibecoder`), test ekibi ve ürün sahibi. Bu varsayım yalnız yeni kavramlar için değil, her
  yanıt için geçerlidir.
- Jargon, kısaltma ve terim yerine sade Türkçe sözcük seç. Teknik terim veya kısaltma
  kaçınılmazsa kısa sade açıklamasını yanıtta geçtiği her yerde hemen yanına yaz (parantez içinde
  veya tek yan cümleyle). Okurun önceki bir açıklamayı hatırladığını varsayma; terimi ilk
  kullanımda açıklayıp sonrakilerde açıklamasız bırakma.
- Komut, kod, tanımlayıcı, dosya yolu ve kesin makine sözleşmesi bayt bayt aynı kalır; çevirme
  veya sadeleştirme. Örneğin `04-politika-catismasi` kuralındaki `POLICY_CONFLICT` belirteci
  değişmez. Yanına ne yaptığını veya ne anlama geldiğini sade sözcüklerle yaz.
- Sade dil uzun yazmak değildir. Aşağıdaki kısalık ilkeleri geçerlidir; açıklama yığmak yerine
  terimi sade sözcükle değiştir.
- Aynı terimi her ajan aynı biçimde açıklasın diye terim sözlüğünü kullan; sözlükte olmayan
  terimi aynı kısalıkta açıkla.

## Terim sözlüğü

- `PRD`: bir özelliğin ne yapacağını ve nasıl kabul edileceğini yazan ürün gereksinim belgesi.
- `PR` (`pull request`): değişikliğin ana koda alınmadan önce incelenmesi için açılan istek.
- `commit`: değişikliklerin proje geçmişine kalıcı bir kayıt olarak eklenmesi.
- `branch` (dal): ana koddan ayrı ilerleyen çalışma kolu.
- `push`: yerel kayıtların ortak sunucudaki depoya gönderilmesi.
- `worktree`: aynı projenin ayrı bir klasörde açılmış ikinci çalışma kopyası.
- `CI`: kod gönderildiğinde testleri sunucuda kendiliğinden çalıştıran denetim.
- `MCP`: yapay zekâ asistanının proje fabrikası gibi dış araçlara bağlandığı bağlantı yöntemi.
- `stdio` bağlantısı: aracın asistanla aynı bilgisayarda çalıştığı yerel bağlantı.
- `HTTP` bağlantısı (uzak sunucu): aracın ağdaki bir sunucuda çalıştığı bağlantı; bu sunucu
  bilgisayardaki dosyaları göremez.
- uygulayıcı (`applicator`): sunucudan gelen dosyaları bilgisayara yazan yerel araç.
- yakınsama (`converged`): bilgisayardaki dosyaların beklenen dosyalarla birebir aynı hâle
  gelmesi.
- `SHA-256` özeti (`digest`): dosya içeriğinden hesaplanan parmak izi; içerik değişirse o da
  değişir.
- `manifest`: projedeki dosyaları ve parmak izlerini listeleyen kayıt dosyası.
- `idempotent`: aynı işlemi yeniden çalıştırmanın sonucu değiştirmemesi.
- izdüşüm (`projection`): ortak kuralların her yapay zekâ asistanının okuyacağı dosya biçimine
  çevrilmiş kopyası.
- kabul (`admission`): bir aracın kurumsal kullanım için resmen onaylanması.
- kanca (`hook`): mesaj gönderme veya dosya yazma gibi anlarda kendiliğinden çalışan denetim.
- `prompt`: yapay zekâ asistanına yazılan mesaj.
- yönetişim: projenin kurallarını, denetimlerini ve kayıtlarını yöneten düzen.
- kalite kapısı: değişiklikten sonra testleri ve denetimleri birlikte çalıştıran kontrol.
- yönetilen inceleme (`governed-review`): değişiklik kaydedilmeden önce on iki uzman ajanın
  yaptığı denetim.
- `PASS`, `FAIL`, `HARD-FAIL`, `BLOCKED_INCOMPLETE`: inceleme kararı; sırasıyla geçti, kaldı,
  kesin bir kural ihlali yüzünden kaldı, eksik bilgi yüzünden karar verilemedi.
- `L0`–`L3`: kanıt seviyesi; kodu `13-tamamlanma-tanimi` kuralındaki sade adıyla birlikte yaz.
- `stage` ve anlık görüntü (`snapshot`): kayda alınmak üzere seçilen değişiklikler ve onların o
  andaki donmuş hâli.
- makbuz (`receipt`): bir denetimin sonucunu gösteren kayıt dosyası.

## Genel ilkeler

- Kullanıcının konuşma diline uy. Etkin insan/model yönetişim metnini Türkçe tut; kodu,
  tanımlayıcıları, sağlayıcıya ait `frontmatter` alanlarını ve makine sözleşmelerini İngilizce koru.
- Bir spesifikasyon seçilen tek bir dili kullanabilir; anlatı dillerini karıştıramaz. Teknik adlar,
  yollar ve `Decision 1` gibi etiketler kararlı kalır.
- Sonuç veya mevcut durumla başla. Soyut bir kavramı kısa ve somut bir örnekle anlat.
- Kısa ol. Yararlı ve kapsam içi iş sürerken özet paragrafları, uydurulmuş kontrol noktaları veya devam
  etme isteği ekleme.
- Aynı anda en fazla bir engelleyici soru sor. Seçim gerekiyorsa ayrık seçenekleri sonuçlarıyla sun.
- Çalışmayı saat veya gün cinsinden tahmin etme. Bunun yerine kapsamı, bağımlılığı, kanıtı ve engeli
  belirt.
- Durum isteğine tamamlanan, bekleyen ve ortam gerçekleriyle yanıt ver; istenmemiş menü veya öneri ekleme.
- İstenmedikçe `commit` mesajı önerme.
- Kullanıcı dosya sistemi veya veri silmeyi açıkça yetkilendirmedikçe “unut” veya “onu atla” gibi sözler
  konuşma bağlamındadır.
- Depo yapıtları kaynak ürünü, kurumu, ticari ortağı veya ilgisiz başka bir depoyu adlandıramaz.
  Kaydedilmiş profilin gerçekten seçtiği teknoloji adlarına izin verilir.

Koşum sonuçlarını `53-test-kosumu-raporu.md` ilkeleriyle sade dille anlat; kısalık, gözlenen kanıtı
veya açık kalan noktayı atlamaya gerekçe değildir.
