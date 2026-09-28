# Betikler

Tek seferlik komutlar yerine bu giriş noktalarını kullanın. İskelet sürümünü, yerel yığını, profil
özelindeki geçişleri, üretilen sözleşmeleri, Helm paket politikasını ve kalite sırasını sabitler. `e2e.sh`,
güvenli biçimde başarısız olan tarayıcı girişidir; varsayılan olarak
`KT_SCAFFOLD_OFFLINE_BUNDLE` ile belirtilen kabul edilmiş çevrimdışı paketi kullanır ve
bant dışı kabul özetini `KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256` içinde ister. Çözülmüş sabit profilin
türlü ayarları, `.env.example`, yerel Compose ortamı ve kök `helm/` dizinindeki Helm paketinin arka uç
`Secret` sınırının (projenin `backend.existingSecret` adı ve üretilen `<release>-database` bağlantısı)
ve gizli olmayan `backend.config` ayarlarının senkron kaldığını kanıtlamak için
`python3 scripts/check-config-sync.py` çalıştırın.

`check-dependency-admission.py`, normalleştirilmiş doğrudan bağımlılık, OCI ve iş akışı eylemi
envanterini ağ olmadan yeniden kurar ve `dependency-admission.json` ile karşılaştırır. Sabitleme
değişikliği; olgunluk/güvenlik kanıtı incelenene kadar ilk kurulumu, yerel kalite kapısını ve CI'ı
başarısız kılar. `security-gate.sh`, Gitleaks, Semgrep ve çevrimdışı Trivy'yi çalıştırmadan önce banka
tarafından kabul edilen tarayıcı anlık görüntüsünü kapalı, sembolik bağ içermeyen envanter olarak
doğrular. Trivy; çalışma zamanı/geliştirme bağımlılık kilitlerini, gizli bilgileri ve IaC
yanlış yapılandırmasını tarar; tek uygulama Helm paketini yalnız güvenlik taramasına ait sentetik imaj,
gizli bilgi referansı, ağ eşleri ve giriş değerleriyle ayrı işler.

`compile-dependency-locks.sh`, arka uç kilitlerini (`requirements.txt`, `requirements-dev.txt` ve
`requirements-llm.txt`) `app/backend/*.in` dosyalarından yeniden üretir. Önce aday envanteri kabul
etmeden kontrol edip yazdırır. Sonra `stack.sh build backend` ile yerel yığının kullandığı arka uç
geliştirme imajını derler; kilitler böylece uygulamanın çalıştığı Python 3.14 sürümüyle üretilir.
Sabitlenmiş `pip-tools` aracını bu imajdan açılan ve iş bitince silinen ayrı bir kapsayıcıda
(`docker run --rm`) çalıştırır. Bu kapsayıcı komutu çalıştıran kullanıcının kimliğiyle çalışır, böylece
kilit dosyaları o kullanıcıya ait kalır; `app/backend` dizinini bağlar ve paket deposuna Docker'ın
varsayılan ağından ulaşır. Yerel yığının dışa kapalı ağı değişmez. Kapsayıcıya yalnız vekil sunucu
(`proxy`, dış ağa çıkışı aracılayan sunucu) değişkenleri `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` ve
küçük harfli karşılıkları adıyla geçer; değerleri komut satırında görünmez. Paket deposu ayarı
(`PIP_INDEX_URL` gibi) geçmez, çünkü `pip-compile` varsayılan dışındaki depo adresini içindeki kimlik
bilgisiyle birlikte kilit dosyasına yazar. Docker yoksa, çalışmıyorsa veya imaj derlenemezse betik
açık bir iletiyle durur. Yönetişim yeni özetle sürüm/istisna kanıtını kaydeder ve birleştirme öncesinde
tam kalite ve güvenlik kapılarını çalıştırır.

`verify-offline-bundle.sh` CI/derleme kabul sınırıdır. Banka yönetimli iki değeri, mühürlü yapıtları ve
ana makine platformunu doğrular; Python wheel deposu, npm önbelleği, Playwright tarayıcı ağacı veya
çalışma zamanı imaj arşivi yoksa derleme öncesinde başarısız olur.

`check-governance-drift.py`, içerik adresli derlemi ve bütün üretilmiş istemci projeksiyonlarını yerel
üreteç kurulumu gerektirmeden doğrular. `render-clients.sh --check` bu doğrulayıcıyı kullanır; yazma kipi
yerel ajan işlemidir veya isteğe bağlı kurulu CLI'ı kullanır. `export-project-metadata.py` yalnız
yönetişim MCP'sinin kabul ettiği sınırlı `.kt-scaffold/project-manifest.json` dosyasını üretir; çalışma
alanını gezmez ve kaynak, gizli bilgi, bağımlılık durumu veya veritabanı verisi içermez.
Generated `.pre-commit-config.yaml`, Gitleaks (gizli bilgi tarayıcısı) ile yalnız commit'e girecek
stage edilmiş değişiklikleri tarar: `app/infra/.env` ve `app/infra/.data/` gibi Git'in yok saydığı
yerel dosyalar commit'i durdurmaz, stage edilmiş değişiklikteki gizli bilgi durdurur. Deponun
tamamını CI'daki `security-gate.sh` tarar. Aynı yapılandırma bu ağsız ve belirlenimci sapma
denetimini de çalıştırır; pre-commit hiçbir LLM veya on iki Agent incelemesi çağırmaz ve çevrimiçi
otorite tazeliğini yenilemez.

`stack.sh`, Compose'u başlatmadan önce `dev-secrets.sh` ile yerel geliştirme sırlarını hazırlar ve
Compose'a verir: arka ucun JWT imza anahtarı (`JWT_PRIVATE_KEY`), PostgreSQL `app` rolünün parolası
(`POSTGRES_PASSWORD`) ve Redis parolası (`REDIS_PASSWORD`). Sırlar ilk kullanımda `openssl` ile
rastgele üretilir ve yalnız sahibinin okuyabileceği biçimde Git'in yok saydığı `app/infra/.data/`
dizininde durur; hiçbiri Git'e girmez. Kabuk ortamında ya da Git'in yok saydığı `app/infra/.env`
içinde tanımlı bir değer üretileni geçersiz kılar. Yığını yeniden oluşturmak oturumları ve veriyi
korur. İmza anahtarını silmek bütün yerel oturumları geçersiz kılar; PostgreSQL parolası veri birimi
ilk oluşturulurken uygulandığı için parolayı değiştirmek `stack.sh down --volumes` ile yerel veriyi
silmeyi gerektirir. Bu sırlar paylaşılan veya dağıtılmış ortamda kullanılmaz.

`stack.sh` ve `compile-dependency-locks.sh`, Compose proje adını `compose-project.sh` ile çözer:
varsayılan ürün kısa adıdır, `COMPOSE_PROJECT_NAME` onu değiştirir. Aynı projenin ikinci kopyasını ayrı
bir yığınla çalıştırmak için `app/infra/README.md` içindeki "Aynı projenin ikinci kopyası" bölümüne
bakın.

`db.sh`, `KT_SCAFFOLD_TEST_DATABASE` adı `_test` ile biten bir veritabanını gösterdiğinde arka ucun
yapılandırılmış bağlantısında yalnız veritabanı adını değiştirir; parola komut satırına çıkmaz.

`quality-gate.sh all`, `_test` ile biten benzersiz, profil özelindeki PostgreSQL veritabanını oluşturur,
kaydedilmiş geçiş geçmişini dağıtır, canlı entegrasyon paketini etkinleştirir, hedef durum sapmasını
kanıtlar ve her çıkış yolunda veritabanını kaldırır. Yapılandırılmış uygulama veritabanını geçirmez.
`quality-gate.sh backend` daha dardır: canlı PostgreSQL testlerini atlar ve yalnız yapılandırılmış
veritabanına karşı salt okunur geçiş doğrulaması yapar. Kararlı `KT_GATE_SCOPE`, `KT_GATE_STEP` ve
`KT_GATE_TESTS` satırları iskelet işleminin tükettiği makine kanıtıdır; olağan
araç çıktısı insanlar içindir.

Tam kapının Helm paket politikası adımı, depoya ait işleyiciyi `kt-iskelet` arkasındaki belirli Python
yorumlayıcısıyla çalıştırır. Bu kabul edilmiş CLI sürümünü Helm ile birlikte `PATH` üzerinde tutun.
Yoksa `render-charts.sh` işleme öncesinde açık araç zinciri hatasıyla başarısız olur. Adım, chart'ı
sentetik değerlerle denetler; projeye ait `values-project.yaml` varsa temel değerlerle birlikte onu da
aynı denetimden geçirir ve içinde gizli bilgi görürse reddeder. `deploy-hooks.sh` varsa yalnız
yazımını (`bash -n`) denetler, çalıştırmaz.
