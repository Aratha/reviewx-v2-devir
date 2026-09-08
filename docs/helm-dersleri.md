
# Helm Hata Dersleri

Helm, values veya deployment override'ını değiştirmeden önce bu bağlayıcı listeyi oku.

Yeni ve genellenebilir bir Helm dersi mevcut maddelerde yoksa aynı hata düzeltme commit'inde tek cümle ekle; aynı dersi tekrar yazma.

- `secrets.authSecret` değerini repoya veya `app.env` içine yazma ve normal upgrade'de yenileme; canlı Secret'ı koru.
- Secret adını şablonlarda ayrı ayrı üretme; `secret.yaml`, `envFrom` ve `lookup` aynı yardımcıyı kullansın.
- Başlatılmış PostgreSQL PVC'sinde values'tan gelen `postgresPassword` ile parolayı ezme; upgrade'de canlı Secret'ı koru, canlı Secret yoksa deploy'u durdur.
- Temiz PostgreSQL başlangıcında PVC'yi silme; doğrulanmış yeni `PGDATA` alt dizinine geç, eski dizini koru ve uygulamayı hedef DB nesli doğrulanmadan başlatma.
- İnternetsiz Kubernetes node'unda public PostgreSQL imajı kullanma; digest-pinned kaynağı CI'da tara ve uygulamayla aynı kurum repository'sine yayınla.
- Bootstrap Secret sürümünü yükseltirken Secret veya PVC'yi silme; uygulamanın eski marker'ı koruyup yeni marker'ı atomik yazmasını sağla.
- Bootstrap kapalıyken eski Secret marker'larını deploy kapısı yapma; tam rollback artığını koru, kısmi parola setini reddet.
- Özelliği kapatan bir overlay ile o özelliğin negatif Helm kapısını sınama; testte özelliği açıkça etkinleştir ve beklenen hata mesajını doğrula.
- `POSTGRES_PASSWORD` ve `DATABASE_URL` için tek çözümlenmiş parolayı kullan ve bağlantı bilgisini yüzde-kodla.
- `--reset-values` veya `--reuse-values` eski sırları korur diye güvenme; kalıcı sırları canlı veya harici Secret'a bağla.
- `secrets.create: true` ile `secrets.existingSecret` değerini birlikte kullanma ve harici Secret'ı eksik anahtarla oluşturma.
- Harici Secret içeriğini döndürdükten sonra podu rollout-restart et; çalışan podun env ve mount içeriği kendiliğinden yenilenmez.
- Admin parolasını values'a veya loga yazma; kaynağı marker ile izle, external kipte chart ADMIN_PASSWORD üretme ve external→chart geçişini açık parola olmadan yapma.
- Admin yakınsamasını install/upgrade/rollback hook'larında değişmez marker ID'sine bağla; 0.4.4 öncesi hook'suz revision'a rollback yapma, forward deploy ve onaylı reset kullan.
- DB kullanan hook'a uygulamayla aynı özel CA mountunu ve nodeSelector/tolerations/affinity alanlarını taşı.
- SMTP parolasını repodaki values'a yazma; güvenli CI girdisi veya `smtp.auth.existingSecret` kaynaklarından birini seç ve `SMTP_USER` ile birlikte yapılandır.
- Opsiyonel hızlı-canlı SMTP Secret'ı fallback iken CI parolası gelirse iki kaynağı Pod'a bağlama; chart-owned kaynağı tek otorite yap.
- SMTP'yi bir ortamda kapatırken host ve kullanıcıyı boşalt, parola ve CA Secret referanslarını kaldır, teslim varsayılanını `0` yap ve renderda SMTP Secret referansı kalmadığını doğrula.
- Eksik SMTP Secret'ını yalnız hızlı canlı kipte ve chart-owned uygulama Secret'ıyla `smtp.auth.optional: true` yap; normal kipte zorunlu tut ve Secret geldikten sonra rollout yap.
- `ingress.hosts` veya `swat.ailabtest...` kullanma; tek kanonik hostu `ingress.host: swat.ailab-test.kuveytturk.com.tr` olarak ver.
- Chart TLS'i kapalıyken tam eşleşen HTTPS `APP_PUBLIC_URL` olmadan `COOKIE_SECURE: "1"` ile deploy etme.
- Chart TLS'i açıksa `APP_PUBLIC_URL` değerini elle yazma; origin'i `ingress.host` üzerinden türet.
- `ssl-redirect` veya `force-ssl-redirect` değerini kapatma; dış TLS'te güvenilir forwarded-proto sınırını ve HTTPS yönlendirme hedefini doğrula.
- Values doğrulamasında önce `hasKey`, sonra kesin tip kontrolü yap ve metin tabanlı `0/1` değerlerinde `--set-string` kullan.
- Render testinde YAML metninin tırnaklı olmasına güvenme; aynı skalerin tırnaklı ve tırnaksız çıktısını eşdeğer kabul et.
- Frontend/backend ayrımında eski backend selector, Secret ve PVC kimliklerini koru; aynı-origin `/api` yönlendirmesini ve yalnız frontend imajı değişince diğer Pod şablonlarının değişmediğini gerçek render ile doğrula.
- Rancher Apps UI'ın yükleyeceği tek dosya chart kökündeki `values.yaml`'dır; zorunlu değerleri `values-test.yaml` gibi ortam dosyasına bırakma, `questions.yaml` ile sor ve guard mesajında UI alan adını da yaz.
- Chart'ı en az bir gerçek `helm template` renderıyla doğrulamadan commit etme; yorum satırının sonuna yapışan bir anahtar YAML'ı bozmadan sessizce başka bir map'e düşer.
- `--set-string`, `-f` ile verilen dosyalardan daha yüksek önceliklidir; CI sırrı script'e ulaşmadığında gönderilen **boş** değer ortam dosyasındaki geçerli değeri siler ve fail-fast guard'ını yanlış yere tetikler. Zorunlu sırları ayrı bir fallback bloğunda tut ya da bayrağı yalnızca değer doluysa ekle.
- `--set-string` değeri virgülden böler; `SERVER=host,1433` içeren bağlantı dizesi hata vermeden kırpılır. Bağlantı dizesi gibi virgül/ters bölü içeren değerleri `--set-file` ile geç.
