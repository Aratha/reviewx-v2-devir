# Yerel altyapı

Yerel yığın PostgreSQL, seçilen arka uç, ortak ön yüz ve aynı kaynaklı ters vekil sunucu içerir.
Redis yalnız önbellek yuvasıdır: `cache` Compose profiline bağlıdır, varsayılan yığında başlamaz ve
arka uç ona bağımlı değildir. Kabul edilmiş bir önbellek PRD'si onu `--profile cache` ile açar.
Uygulama/veri çalışma zamanı ağı kurum içi işaretlidir; bu servisler internete erişemez. Docker
Desktop, yalnız iç köprüden port yayımlayamadığı için yalnız nginx ve isteğe bağlı Grafana, ana
makineye dönük uç köprüye de katılır. Port yalnız geri döngü adresindedir, DNS kapalıdır ve
yapılandırmada dışa giden üst akış yoktur; çevreleyen dış ağ trafiği kontrolü banka ana makine
güvenlik duvarıdır. Seçiliyse gözlemlenebilirlik de iç ağda kalır.

Bütün üçüncü taraf imajları sürüm ve özetle (`@sha256:`) sabitlenmiştir. Makinede yoksa Docker
bu sabit özeti kayıt deposundan kendisi indirir; özet değişmediği için indirilen imaj incelenen
imajın aynısıdır. Çevrimdışı CI imajları paketten önceden yükler, bu durumda indirme yapılmaz.
Yayımlanan portlar yalnız geri döngü adresine bağlanır. İsteğe bağlı toplayıcı yalnız yerel Tempo,
Prometheus ve Loki servislerine aktarır; Grafana panosu yerel olarak hazırlanır. Bu katman açıkken
arka uç izlerini ve ölçümlerini OTLP/gRPC ile iç ağdaki toplayıcıya gönderir
(`DWHCODEREVIEW_OTEL_EXPORTER_OTLP_ENDPOINT`); katman yoksa arka uç hiçbir sinyal göndermez.
Bu Compose katmanını etkinleştirmeden önce Git tarafından yok sayılan `.env` içinde `GRAFANA_ADMIN_PASSWORD`
ayarlayın; anonim erişim, güncelleme denetimi, analiz, Gravatar ve eklenti indirme kapalıdır.

Her çalışma zamanı/temel imaj referansı, kaydedilmiş varsayılanı özetle sabitlenmiş kalan ortam
geçersiz kılmasıdır. Banka dağıtımı yalnız kayıt deposu ön ekini terfi ettirilmiş iç imaja çevirir;
özet incelenmiş kimlik olarak kalır. `DEPENDENCY_MODE=offline` ile mutlak
`PYTHON_WHEELHOUSE_CONTEXT` ve `NPM_CACHE_CONTEXT` yolları doğrulanmış paketi BuildKit'e
bağlar. Çevrimdışı Python ve ön yüz derlemeleri yalnız kabul edilmiş bağımlılıkları kullanır.
`connected` kipi de yalnız kontrollü ortam yapılandırmasıyla sağlanan banka yönetimli paket yansılarını
kullanır. Üretilen çevrimdışı CI, mutlak `KT_SCAFFOLD_OFFLINE_BUNDLE` ile ayrı dağıtılan
`KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256` kabul özetini ister, imaj yüklemeden önce doğrular ve bütün
adlandırılmış bağlamları açıkça ayarlar; bağlı bağımlılık çözümlemesine geri dönmez.

Loki ve Tempo, yeniden başlatmalar arasında veriyi korurken kök olmayan kimlikte kalır. Adlandırılmış
birimleri `/loki` ve `/var/tempo` yollarına bağlanır; sabitlenmiş imajlar bu dizinlerin UID/GID 10001
sahibidir ve Docker'ın yeni birim kopyalaması, kök başlatıcı olmadan doğru sahibi korur. Her iki servis
kimliğini açıkça beyan eder, salt okunur kök dosya sistemi kullanır, bütün yetkinlikleri kaldırır,
`no-new-privileges` etkinleştirir; yalnız kabul edilmiş durum birimleri yazılabilirdir.

`scripts/stack.sh` kullanın; Compose proje adını ve dosya seçimini tutarlı tutar ve PostgreSQL, Redis
(yalnız `cache` profili açıkken kullanılır) ile arka uç imza anahtarının Git dışında üretilen yerel
sırlarını verir (`scripts/README.md`). Compose bu sırları `stack.sh` olmadan başlatıldığında açık
hatayla durur.
