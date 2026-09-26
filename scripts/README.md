# Betikler

Tek seferlik komutlar yerine bu giriş noktalarını kullanın. İskelet sürümünü, yerel yığını, profil
özelindeki geçişleri, üretilen sözleşmeleri, Helm paket politikasını ve kalite sırasını sabitler. `e2e.sh`,
güvenli biçimde başarısız olan tarayıcı girişidir; varsayılan olarak
`KT_SCAFFOLD_OFFLINE_BUNDLE` ile belirtilen kabul edilmiş çevrimdışı paketi kullanır ve
bant dışı kabul özetini `KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256` içinde ister. Çözülmüş sabit profilin
türlü ayarları, `.env.example`, yerel Compose ortamı ve kök `helm/` dizinindeki Helm paketinin önceden
oluşturulmuş `backend.existingSecret` sınırının senkron kaldığını kanıtlamak için
`python3 scripts/check-config-sync.py` çalıştırın.

`check-dependency-admission.py`, normalleştirilmiş doğrudan bağımlılık, OCI ve iş akışı eylemi
envanterini ağ olmadan yeniden kurar ve `dependency-admission.json` ile karşılaştırır. Sabitleme
değişikliği; olgunluk/güvenlik kanıtı incelenene kadar ilk kurulumu, yerel kalite kapısını ve CI'ı
başarısız kılar. `security-gate.sh`, Gitleaks, Semgrep ve çevrimdışı Trivy'yi çalıştırmadan önce banka
tarafından kabul edilen tarayıcı anlık görüntüsünü kapalı, sembolik bağ içermeyen envanter olarak
doğrular. Trivy; çalışma zamanı/geliştirme bağımlılık kilitlerini, gizli bilgileri ve IaC
yanlış yapılandırmasını tarar; tek uygulama Helm paketini yalnız güvenlik taramasına ait sentetik imaj,
gizli bilgi referansı, ağ eşleri ve giriş değerleriyle ayrı işler.

`compile-dependency-locks.sh`, sabitlenmiş `pip-tools` aracını profilin Python 3.13 arka uç kapsayıcısında
çalıştırır ve iki özet kilidini belirli doğrudan otoritelerden yeniden üretir. Aday envanteri kabul
etmeden kontrol edip yazdırır. Yönetişim yeni özetle sürüm/istisna kanıtını kaydeder ve birleştirme
öncesinde tam kalite ve güvenlik kapılarını çalıştırır.

`verify-offline-bundle.sh` CI/derleme kabul sınırıdır. Banka yönetimli iki değeri, mühürlü yapıtları ve
ana makine platformunu doğrular; Python wheel deposu, npm önbelleği, Playwright tarayıcı ağacı veya
çalışma zamanı imaj arşivi yoksa derleme öncesinde başarısız olur.

`check-governance-drift.py`, içerik adresli derlemi ve bütün üretilmiş istemci projeksiyonlarını yerel
üreteç kurulumu gerektirmeden doğrular. `render-clients.sh --check` bu doğrulayıcıyı kullanır; yazma kipi
yerel ajan işlemidir veya isteğe bağlı kurulu CLI'ı kullanır. `export-project-metadata.py` yalnız
yönetişim MCP'sinin kabul ettiği sınırlı `.kt-scaffold/project-manifest.json` dosyasını üretir; çalışma
alanını gezmez ve kaynak, gizli bilgi, bağımlılık durumu veya veritabanı verisi içermez.
Generated `.pre-commit-config.yaml`, mevcut Gitleaks taramasının yanında bu ağsız ve belirlenimci
sapma denetimini de çalıştırır; pre-commit hiçbir LLM veya on iki Agent incelemesi çağırmaz ve
çevrimiçi otorite tazeliğini yenilemez.

`stack.sh`, Compose'u başlatmadan önce `dev-secrets.sh` ile yerel geliştirme sırlarını hazırlar ve
Compose'a verir: arka ucun JWT imza anahtarı (`JWT_PRIVATE_KEY`), PostgreSQL `app` rolünün parolası
(`POSTGRES_PASSWORD`) ve Redis parolası (`REDIS_PASSWORD`). Sırlar ilk kullanımda `openssl` ile
rastgele üretilir ve yalnız sahibinin okuyabileceği biçimde Git'in yok saydığı `app/infra/.data/`
dizininde durur; hiçbiri Git'e girmez. Kabuk ortamında ya da Git'in yok saydığı `app/infra/.env`
içinde tanımlı bir değer üretileni geçersiz kılar. Yığını yeniden oluşturmak oturumları ve veriyi
korur. İmza anahtarını silmek bütün yerel oturumları geçersiz kılar; PostgreSQL parolası veri birimi
ilk oluşturulurken uygulandığı için parolayı değiştirmek `stack.sh down --volumes` ile yerel veriyi
silmeyi gerektirir. Bu sırlar paylaşılan veya dağıtılmış ortamda kullanılmaz.

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
Yoksa `render-charts.sh` işleme öncesinde açık araç zinciri hatasıyla başarısız olur.
