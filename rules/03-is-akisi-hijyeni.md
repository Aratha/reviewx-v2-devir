---
id: "03-is-akisi-hijyeni"
title: "Depo değişikliklerini açık, geri alınabilir ve kullanıcıya ait tut"
scope: governance
authority: mandatory
priority: 30
trigger: always
applies_to: []
gate: "review"
---

# İş akışı hijyeni

Sürüm denetimi yayını kullanıcıya aittir. Kullanıcı tam olarak ilgili işlemi açıkça istemedikçe
`stage`, `commit`, `push` veya `tag` yapma; geçmişi yeniden yazma; `pull request` oluşturma/birleştirme
ya da dal değiştirme. Salt okunur `status`, `diff` ve geçmiş incelemesine izin verilir. Değişiklik
içeren çalışma ağacındaki ilgisiz kullanıcı değişikliklerini koru.

Anlık komut veya yardımcı yazmadan önce `scripts/` dizinini incele ve mevcut sarmalayıcıyı kullan.
Depoda tek kullanımlık betik, hata ayıklama yapıtı veya üretilmiş çıktı bırakma. Eksik işi yer
tutucu, yorum bloğu, bayat işaret veya uydurulmuş başarılı sonuçla asla gizleme.

Teslimat aşaması başlatma veya kabul edilmiş kapsamın bir bölümünü beklemeye alma. Mevcut kabul edilmiş
PRD kapsamındaki davranışsız küçük ya da büyük mekanik düzenlemeler için yeni PRD üretme; exact
`Requirement <n>`/`Acceptance <n>` başvurusunu mevcut `tasks.md` ve koşum kanıtında yeniden kullan.
Kabul ölçütü değişiyorsa aynı PRD'yi revize edip yeniden kabul ettir. Kapsam gerçekten bağımsız aktör,
sonuç, değişmez veya risk sınırı olarak ayrılıyorsa kendi kabul ölçütleri olan, yol haritasına bağlı
başka bir `PRD` oluştur; işi “sonra” notuna gömme. Kabul edilmiş `PRD`'nin gerektirdiği katmanları tek
ve tutarlı değişiklikte tamamla.

Tek güncel otoriteyi koru. Bir özellik, sözleşme, davranış veya sürüm yenisiyle değiştirildiğinde
eski biçimi `PRD`, plan, görev, doküman, kural, şema, kod ve testten sil; yalnız güncel ve tek
yürürlükteki hal kalır. Geriye uyumluluk katmanı, eski biçim okuyucusu, uyumluluk alanı veya takma
ad bırakma. Belgeyi yerinde revize et; değişiklik bölümü, değişiklik günlüğü, “tarihsel” bölüm veya
eski kabul paragrafı ekleme. Geçmiş git geçmişinde ve tarihli koşum kanıtında durur; etkin dosyalar
bu kayıtları güncel sözleşme olarak göstermez. Her sözleşmenin tek sahibi olan dosya vardır; diğer
dosyalar onu tekrar etmez, ona bağlantı verir. Testler güncel sözleşmeyi doğrular; eski ifade veya
davranışın kalmasını şart koşmaz.

Yıkıcı veri veya dosya sistemi işlemleri, yıkıcı eylemi ve hedefi adlandıran açık yetki gerektirir.
Önce tam hedefi salt okunur biçimde çözümle. Veritabanı göçleri geliştirici ortamından yalnızca
yerel veritabanına uygulanabilir; dağıtım ortamları göç sürümünü kullanır.

Üretilmiş yönetişim dosyaları salt okunur çıktılardır. `rules/` kaynağını değiştir, tüm
istemcileri yeniden üret ve sapma kapısını çalıştır. Proje iskeleti güncellemesi, ekipçe düzenlenmiş
dosyaların üzerine sessizce yazmaz; sonraki şablondan kaldırılmış dosyaları yalnız özet sahipliği
doğrulanırsa siler, düzenlenmiş dosyayı çakışma olarak korur.

`project_init` çözümlenmiş proje amacı ve profilleri gerektirir, dolu hedefi reddeder, kardeş hazırlık
dizininde oluşturur, tüm ağacı doğrular ve günlüklü işlemle yayımlar. Kuru koşum veya deneme proje
iskeleti modu yoktur. Hata durumunda yalnızca ilk oluşturma işleminin sahip olduğu yolları geri alır.
Sonraki üreticiler atomik yazar ve mevcut ekip dosyasının üzerine yazmak yerine çakışmayı reddeder.

İlk proje kurulumunda kanonik dosyalar doğrulanıp nihai hedefe yayımlandıktan sonra kök `.venv`,
teknoloji profiline uygun güvenilen yerel Python'un standart `venv`/`ensurepip` işlemiyle, projeye
dağıtılan `.kt-scaffold/hooks/python_environment.py hazirla` komutuyla hazırlanır. Bu dar izin
uygulama kodu yürütme, paket indirme/yükseltme, requirements kurulumu, PATH veya kurumsal çalıştırma
politikası değişikliğini kapsamaz. Prompt kancası `.venv` olmadan her prompt'u durdurduğundan HTTP
içerik tesliminde yetkili yerel istemci bu komutu kanca ayarlarından önce çalıştırır ve yalnız
`status` ile `observed_version` makbuzunu bildirir; makbuz olmadan kanca ayarları gelmez ve kurulum
tamamlanmaz. Dosya yakınsaması ve ortam hazırlığı ayrı kanıtlardır. Ortam içeriğini veya yollarını MCP'ye yükleme;
kanonik taramadan yalnız ayrıca doğrulanmış tam kök `.venv` dizinini aşağıya inmeden ayır, başka
beklenmeyen yolları gizleme. Mevcut ortamın güvenini ve yol sınırını doğrulamadan içindeki kodu
çalıştırma; bozuk ortamı koruyup reddet. Güncelleme ortam oluşturmaz veya yeniden kurmaz.

İlk proje kurulumu, kanonik dosyalar doğrulandıktan sonra hedef zaten bir Git çalışma ağacında
değilse `main` dalıyla depo açar ve yalnız kanonik dosyaları içeren tek ilk commit'i oluşturur. Bu
adım kullanıcının proje oluşturma isteğinin parçasıdır ve yukarıdaki `stage`/`commit` sınırının tek
istisnasıdır. Var olan depoyu yeniden açma veya ona commit ekleme; kişisel Git kimliği uydurma. HTTP
içerik tesliminde bu adımı `delivery.phase=initial-commit` yanıtındaki `delivery.initial_commit`
talimatıyla yetkili yerel istemci yapar ve ölçtüğü sonucu `git_repository` alanında bildirir;
bildirim gelmeden kurulum tamamlanmaz, sonucu uydurma. Bu
commit, yönetilen inceleme makbuzu istemeyen tek commit'tir: commit kancası onu
`INITIAL_SCAFFOLD_COMMIT` adıyla yalnız hiç commit'i olmayan depoda `main` dalında, talimattaki
commit komutu tek başına ve birebir çalıştırıldığında ve kayda hazırlanan dosyalar üreticinin
`.kt-scaffold/manifest.json` kaydıyla birebir aynıyken geçirir. Komutu değiştirme, başka komutla
birleştirme veya dosya ekleyip çıkarma; makbuz uydurma. Kanca veya imzalama commit'i reddederse
`--no-verify` kullanma, kancayı kapatma; git adımını tamamlanmadı olarak bildir.

Genel `MCP` yüzeyi, taslak ve yönetişim bilgi düzlemidir. Çalışma alanı kaynağını, sırrını,
bağımlılık ağacını, veritabanı verisini veya tam dosya sistemi anlık görüntüsünü ona asla
yükleme. Tüm depo değişiklikleri, kod yürütme, test ve kanıt yerel ajana aittir. `MCP` güncelleme
niyetlerini yerel kopyayla uzlaştır, her zorunlu davranışı koru ve yerel sahipli yönetişim dosyalarını
değiştirmeden önce kabul, uyarlama, erteleme veya ret kararlarını kaydet.
