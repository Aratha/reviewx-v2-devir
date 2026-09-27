# Kullanım kılavuzu

DWH Code Review, veri ambarındaki SQL kodunu ekibin yayımladığı inceleme kurallarına göre bir yapay
zekâ modeline (LLM, metni okuyup yorum yazan dil modeli) inceletir. Her kural için "uyumlu" ya da
"ihlal var" sonucunu, sorunlu satırın numarasını ve düzeltme notunu gösterir. Sonucu Excel'de açılan
tablo dosyası (CSV) ya da düzeltme notlarıyla yorumlanmış SQL dosyası olarak indirebilirsiniz.

Bu kılavuz uygulamayı kullanan herkes içindir. Kullanıcı yetkileri ve kural yönetimi
[yönetici kılavuzunda](yonetici-kilavuzu.md), uygulamayı kendi bilgisayarınızda çalıştırmak
[yerel kurulum kılavuzunda](yerel-kurulum.md) anlatılır.

## Uygulamaya nereden girilir

- **Test ortamı (nonprod):** Ekibin ortak kullandığı, kurum sunucularında çalışan sürümdür.
  Adresini ekibinizden alın; tarayıcıda açmanız yeterlidir.
- **Kendi bilgisayarınız (yerel):** Uygulamayı kendiniz başlattıysanız adres
  `http://localhost:8080` olur. Başlatma adımları [yerel kurulum kılavuzundadır](yerel-kurulum.md).

## Giriş

Giriş ekranı "Kurum kullanıcı adınız ve parolanızla giriş yapın." der.

- **Test ortamında** kurum hesabınızla girersiniz: kullanıcı adı `ad.soyad` biçimindedir, parola kurum
  parolanızdır. Parolanız uygulamada saklanmaz; yalnız o anki doğrulama için kurum dizinine
  (kurumun kullanıcı hesaplarını tutan sistem, Active Directory) gönderilir. İlk girişinizde kaydınız
  kendiliğinden açılır ve rolünüz **İnceleyici** olur.
- **Yerelde** kurum dizini kapalıdır. Yerel kurulumda açtığınız test hesabıyla girersiniz.

Oturum kapanma kuralları:

- Uygulamayı kullandığınız sürece oturum kendiliğinden yenilenir.
- 60 dakika hiçbir şey yapmazsanız ya da girişinizin üzerinden 8 saat geçerse yeniden giriş
  istenir.
- Sağ üstteki **Çıkış yap** düğmesi oturumu hemen kapatır.
- Yöneticiniz rolünüzü değiştirirse oturumunuz kapatılır; en geç 15 dakika içinde yeniden giriş
  istenir ve yeni rolünüzle devam edersiniz.

Girişte görebileceğiniz iletiler:

| İleti | Anlamı |
|---|---|
| Kullanıcı adı veya parola geçersiz. | Ad veya parola yanlış. Uygulama hangisinin yanlış olduğunu bilerek söylemez. |
| Çok sayıda hatalı deneme yapıldı. Birkaç dakika sonra yeniden deneyin. | Aynı ad için kısa sürede çok sayıda (15 dakikada 5) hatalı deneme oldu. Biraz bekleyin. |
| Hesabınız pasif durumda. Uygulama yöneticisine başvurun. | Yönetici hesabınızı kapattı. |
| Bu hesap başka bir kullanıcı kaydıyla çakışıyor. Uygulama yöneticisine başvurun. | Aynı e-postayla yerel bir hesap var; yöneticinin düzeltmesi gerekir. |
| Kurum dizinine şu anda ulaşılamıyor. Biraz sonra yeniden deneyin. | Kurum kullanıcı dizinine bağlanılamadı. Sorun sürerse yöneticinize bildirin. |

Kaynak: [dizin girişi PRD'si](../../specs/application-foundation/PRDs/001-directory-login/PRD.md)
(PRD: bir özelliğin ne yapacağını ve nasıl kabul edileceğini yazan belge).

## Roller ve menü

Her kullanıcının tek rolü vardır. Menüde yalnız rolünüzün açabildiği sayfalar görünür.

| Menü | Sayfa | İnceleyici | Kural yöneticisi | Süper yönetici |
|---|---|:---:|:---:|:---:|
| Genel | Ana sayfa | ✓ | ✓ | ✓ |
| İnceleme | Nesne incelemesi | ✓ | ✓ | ✓ |
| İnceleme | SQL betiği incelemesi | ✓ | ✓ | ✓ |
| İnceleme | İnceleme geçmişi | Kendi incelemeleri | Herkesinki (salt okunur) | Herkesinki (salt okunur) |
| İnceleme | Yayımlanmış kurallar | ✓ | ✓ | ✓ |
| Yönetim | Kurallar | — | ✓ | ✓ |
| Yönetim | SQL bağlantısı, LLM bağlantısı | — | Yalnız yerelde | Yalnız yerelde |
| Yönetim | LLM çağrıları | — | ✓ | ✓ |
| Yönetim | Kullanıcılar | — | — | ✓ |

- **İnceleyici:** İnceleme yapar, kendi sonuçlarını görür, işaretler ve indirir.
- **Kural yöneticisi:** İnceleyicinin yaptığı her şeye ek olarak kuralları düzenler ve yayımlar,
  herkesin incelemesini salt okunur görür, yapay zekâ çağrılarının özetini izler.
- **Süper yönetici:** Rolleri atayan uygulama yöneticisidir; kural yöneticisinin yaptıklarını da
  yapabilir.

Menüde bir sayfanın görünmemesi tek güvence değildir; sunucu her istekte rolünüzü ayrıca denetler.

## Nesne incelemesi

Veritabanındaki saklı yordam (procedure), görünüm (view) ve fonksiyonları incelemek içindir.

1. Menüden **Nesne incelemesi**ni açın.
2. **Nesne listesi için veritabanı** kutusundan bir veritabanı seçin. Listede yalnız inceleme için
   izin verilmiş ve çalışır durumdaki veritabanları görünür.
3. Nesneleri daraltmak için **Ara** (şema, ad veya tür), **Tür** ve **Bu tarihten sonra oluşturulan
   veya değişen** alanlarını kullanın.
4. İncelemek istediğiniz satırları işaretleyin. Başlıktaki kutu, görünen satırların tümünü seçer.
5. Başka bir veritabanı seçip işaretlemeye devam edebilirsiniz; önceki seçimleriniz korunur. Sayaç
   "n / 50 seçili · m veritabanı" biçiminde toplamı gösterir. Bir incelemede en çok 50 nesne olur.
6. **Seçilenleri incele** düğmesine basın.

İnceleme her zaman **en son yayımlanmış kural sürümüyle** yapılır. Hiç yayımlanmış kural yoksa
inceleme başlamaz ve "Henüz yayımlanmış kural yok; inceleme başlatılamaz." iletisi görünür.

Bir nesnenin metni 120.000 karakterden uzunsa yalnız ilk 120.000 karakteri incelenir ve sonuçta "Metnin
yalnız ilk 120.000 karakteri incelendi." uyarısı görünür. 45.000 karakteri aşan metin her kural için iki
parçada incelenir; canlı pencerede o kuralın yanında **İki parça** yazar.

"Nesne meta verisi gerekir" işaretli kurallarda, nesnenin kullandığı diğer nesnelerin ve sütunların
özeti de modele gönderilir. Bu özet yalnız nesne incelemesinde vardır.

Kaynak: [nesne incelemesi PRD'si](../../specs/sql-review/PRDs/003-object-review/PRD.md).

## SQL betiği incelemesi

Veritabanında olmayan ya da elinizde duran SQL metnini incelemek içindir. SQL Server bağlantısı
gerekmez.

1. Menüden **SQL betiği incelemesi**ni açın.
2. İsterseniz **Sonuçlarda görünecek ad (isteğe bağlı)** alanına kısa bir ad yazın (en çok 200
   karakter). Boş bırakırsanız ad "Yapıştırılan SQL" olur.
3. SQL metnini yapıştırın. Alttaki sayaç karakter sayısını gösterir; sınır 120.000 karakterdir. Sınırı
   aşan metin kesilmez, hiç gönderilmez.
4. **Kurallara göre incele** düğmesine basın.

Sayfadaki uyarıyı dikkate alın: metin kurum içi yapay zekâ modeline gönderilir ve inceleme geçmişinde
saklanır. **Kişisel veri ve parola içeren metin yapıştırmayın.**

Kaynak: [SQL betiği incelemesi PRD'si](../../specs/sql-review/PRDs/004-script-review/PRD.md).

## Canlı inceleme penceresi

İnceleme başlayınca **Canlı inceleme** penceresi açılır:

- Üstte ilerleme çubuğu ve "x / y nesne tamamlandı" sayacı vardır.
- Her nesne için aşama görünür: Tanım okunuyor, Meta veri alınıyor, İnceleniyor, Tamamlandı veya Hata.
- Her kural için kural kimliği (örneğin `Kural05`), **Kritik** ya da **Normal** grubu ve modelin o
  ana kadar ürettiği metin miktarı görünür. Bir kurala yanıt alınamazsa **Yanıt alınamadı** yazar.

İnceleme sürerken başka sayfalara geçebilirsiniz; üst çubukta "İnceleme sürüyor · %n" yazar ve
tıklayınca pencere yeniden açılır. **Tarayıcı sekmesini kapatmayın ve sayfayı yenilemeyin:** bağlantı
koparsa inceleme durur.

**Analizi durdur** incelemeyi keser. Yeni kural çağrısı 5 saniye içinde durur, yarım kalan sonuçlar
saklanmaz ve pencerede "İnceleme durduruldu." yazar.

İnceleme bitince pencerenin altında **CSV indir**, **SQL indir**, **Sonuçları göster** ve **Kapat**
düğmeleri çıkar.

## Sonuçları okumak

**İnceleme sonuçları** penceresinde her nesne ayrı bir bölümdür. Bölüm başlığında "x uyumlu · y ihlal"
özeti yazar.

| Durum | Anlamı |
|---|---|
| Uyumlu | Kurala uyuluyor. |
| İhlal var | Kurala uyulmayan yer bulundu; altında bulgular listelenir. |
| Kapsam dışı | Kural bu koda uygulanmıyor; uyumlu sayılır. |
| Değerlendirilemedi | Modelden kullanılabilir yanıt alınamadı; kısa nedeni yazar. |

Her bulguda şunlar vardır:

- **Önem:** Yüksek, Orta veya Düşük.
- **Açıklama:** Sorunun ne olduğu ve nasıl düzeltileceği. Ayrı bir "öneri" alanı yoktur; düzeltme notu
  bu açıklamadır.
- **Konum:** Örneğin "Satır 12–15". Satır numarası incelenen metnin kendi satırıdır.
- **Kod parçası:** Sorunlu satırlardan bir alıntı.

Sonuçları üstteki **Metin ara**, **Kural durumu** ve **Önem (ihlallerde)** alanlarıyla süzebilirsiniz;
**Süzgeci sıfırla** hepsini temizler.

Bir kuralın metnini görmek için **Yayımlanmış kurallar** sayfasını açın. Sayfa en son sürümü gösterir;
**Sürüm** kutusundan eski bir sürümü de açabilirsiniz. Kurallar **Kritik (HIGH)** ve
**Normal (LOW / MEDIUM)** olmak üzere iki gruptadır.

Kaynak: [kural yönetimi PRD'si](../../specs/sql-review/PRDs/001-rule-management/PRD.md).

## Yanlış pozitif işaretlemek

Model bazen gerçekte sorun olmayan bir yeri ihlal diye gösterir. Buna **yanlış pozitif** denir.

- Bir bulgunun ya da bulgusu olmayan bir "İhlal var" sonucunun yanındaki **Yanlış pozitif** kutusunu
  işaretleyin. İşaret sunucuda saklanır; sayfayı yenileseniz de, başka bilgisayardan girseniz de
  korunur.
- Yalnız incelemeyi başlatan kişi işaret koyup kaldırabilir. Kural yöneticisi başkasının incelemesindeki
  işaretleri görür ama değiştiremez.
- İşaretli bulgular CSV dosyasında `false_positive` sütununda `true` olarak kalır; SQL dosyasındaki
  düzeltme listesine yazılmaz.

## İnceleme geçmişi

Biten her inceleme sunucuda saklanır. **İnceleme geçmişi** sayfasında hangi bilgisayardan girerseniz
girin aynı kayıtları görürsünüz.

- Solda kayıt listesi vardır: tür (**Nesne** ya da **SQL**), durum, başlangıç zamanı, başlık ve
  "Kural sürümü n · x nesne · y bulgu" özeti. Bir kayda tıklayınca sağda sonuçları açılır.
- Durumlar: **Tamamlandı**, **Hata**, **Durduruldu** (siz durdurdunuz), **Yarıda kesildi** (uygulama
  inceleme sürerken yeniden başladı) ve **Sürüyor**. Durdurulan ve yarıda kesilen incelemenin sonucu
  saklanmaz.
- İnceleyici yalnız kendi incelemelerini görür; başka bir inceleyici sizin kayıtlarınızı göremez.
- Kural yöneticisi sayfanın üstünde **Benim incelemelerim** ile **Tüm incelemeler** arasında seçim yapar.
  Başkasının incelemesi "Bu inceleme başka bir kullanıcıya ait; yalnız okunabilir." notuyla açılır.
- **Sil** yalnız sizin bitmiş incelemenizi, **Tümünü sil** yalnız sizin bitmiş incelemelerinizi siler;
  ikisi de önce onay sorar. Silme; sonuçları, işaretleri ve saklanan SQL metnini kalıcı olarak kaldırır.
  Süren inceleme silinemez.

## Dışa aktarma (CSV ve SQL)

Canlı pencerede, sonuç penceresinde ve geçmişteki her kaydın altında iki düğme vardır. Dosyalar
sunucuda saklanan incelemeden üretilir; SQL Server'a yeniden bağlanılmaz, model yeniden çağrılmaz.

- **CSV indir:** Adı `sql-review-` ile başlayan, Excel'de Türkçe karakterleriyle açılan tablo
  dosyasıdır. Sütunlar sırasıyla: `generated_at`, `database`, `schema`, `name`, `object_type`,
  `rule_id`, `tier`, `status`, `severity`, `description`, `line_reference`, `code_snippet`,
  `false_positive`. `=`, `+`, `-` veya `@` ile başlayan hücrelerin önüne `'` eklenir; böylece Excel o
  hücreyi formül olarak çalıştırmaz. Bu yüzden `-- yorum` gibi bir kod parçası `'-- yorum` görünür.
- **SQL indir:** Adı `sql-review-source-` ile başlar. Dosyanın başında "SQL Review - Duzeltilmesi
  Gereken Yerler" başlıklı bir yorum bloğu vardır; her madde `- kural — Satir N — açıklama`
  biçimindedir. Altında incelenen SQL metni durur. Nesne incelemesinde her nesne
  `-- [veritabanı] şema.ad (tür)` başlığıyla ve aralarında `GO` satırıyla yazılır. Yorumdaki
  "Satir N", indirdiğiniz dosyadaki gerçek satır numarasıdır.

İnceleme hata ile bittiyse, durdurulduysa veya yarıda kesildiyse saklanmış SQL metni yoktur; **SQL
indir** düğmesi kapalıdır ve "SQL indirme kapalı: bu inceleme için saklanmış SQL metni yok." yazar.

## Saklama süresi (90 gün)

- İncelemeler, sonuçları, işaretleri ve incelenen SQL metni, incelemenin bitişinden **90 gün** sonra
  kendiliğinden silinir. Silme günde en az bir kez çalışır.
- İncelenen SQL metnini yalnız incelemeyi başlatan kişi ve kural yöneticisi görebilir. Metin uygulama
  günlüklerine yazılmaz.
- Yapay zekâ çağrılarının özetleri (zaman, model, süre, sonuç) de 90 gün saklanır. Bu özetlerde SQL
  metni ve model yanıtı yoktur.
- Uygulamanın veritabanı için yedek alınmaz. Saklamak istediğiniz sonucu CSV veya SQL olarak indirin.

Kaynak: [inceleme geçmişi ve dışa aktarma PRD'si](../../specs/sql-review/PRDs/005-review-history-export/PRD.md).

## "SQL Server bağlantısı yapılandırılmamış." ne demek

Bu ileti **Nesne incelemesi** sayfasında veritabanı listesinin yerine görünür. Uygulamanın bağlanacağı
SQL Server'ın adresi ya da okuma hesabı bu ortamda henüz verilmemiştir. Uygulamada bir arıza yoktur.

- Veritabanı ve nesne listesi gelmez, bu yüzden nesne incelemesi yapılamaz.
- **SQL betiği incelemesi** SQL Server'a hiç bağlanmadığı için normal çalışır. İncelemek istediğiniz
  kodu kopyalayıp oraya yapıştırabilirsiniz.
- Test ortamında bağlantıyı dağıtımı yöneten ekip tanımlar
  ([yönetici kılavuzu](yonetici-kilavuzu.md#sql-server-ve-llm-ayarları)). Yerelde kural yöneticisi
  kendi ayarını girer ([yerel kurulum](yerel-kurulum.md#sql-server-ve-yapay-zekâ-modeline-bağlanmak)).

Kaynak: [SQL Server bağlantısı PRD'si](../../specs/sql-review/PRDs/002-sql-server-connection/PRD.md).

## Sık görülen iletiler

| İleti | Ne yapmalı |
|---|---|
| Henüz yayımlanmış kural yok; inceleme başlatılamaz. | Kural yöneticisinin kuralları yayımlamasını bekleyin. |
| Bu veritabanı inceleme için izinli değil. | Veritabanı izin listesinde yok. Eklenmesi için yöneticinize başvurun. |
| SQL Server'a ulaşılamadı. / SQL Server zamanında yanıt vermedi. | **Listeyi yenile** ile yeniden deneyin; sürerse yöneticinize bildirin. |
| Tanım alınamadı (nesne yok veya yetki yok). | Nesne silinmiş ya da okuma hesabının onu görme yetkisi yok. Diğer nesneler incelenmeye devam eder. |
| Çok fazla inceleme başlattınız; biraz sonra yeniden deneyin. | Bir dakikada en çok 30 inceleme başlatılabilir. Biraz bekleyin. |
| Kural "Değerlendirilemedi", nedeni "LLM sunucusu yanıt vermedi (zaman aşımı)." gibi | Model yoğun ya da ulaşılamıyor. İncelemeyi daha sonra yeniden başlatın. |
| Oturumunuzun süresi doldu. Lütfen yeniden giriş yapın. | Yeniden giriş yapın. |
