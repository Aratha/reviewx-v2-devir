---
id: "45-dagitim-hedefi"
title: "Her değişikliği sıkılaştırılmış Kubernetes hedefine dağıtılabilir tut"
scope: deployment
authority: mandatory
priority: 45
trigger: path-match
applies_to:
  - "helm/**"
  - "app/infra/**"
  - ".github/workflows/**"
gate: "charts-render.yml"
application_modes:
  - separated-web
---

# Dağıtım hedefi

Her proje iskeleti, internet çıkışı olmayan yönetilen, üretim dışı `Kubernetes` kümesini hedefler.
DevOps standardı gereği tek uygulama `chart`'ı `helm/<ürün-kısa-adı>/` dizinindedir ve dağıtım giriş
noktası aynı dizindeki `deploy.sh` dosyasıdır. `chart` kendi kendine yeterlidir; arka uç ve ön yüz iş
yüklerini, projenin kabul edilmiş `PRD`'si bildirdiğinde ise bir PostgreSQL 17 `StatefulSet`'ini ve bir
Alembic şema geçişi `Job`'unu içerir. Önbellek, işleyici veya gözlemlenebilirlik iş yükü, alt `chart`,
ortam katmanı, bağımlılık arşivi veya çalışma zamanı indirmesi içermez.
Bu hedefi karşılayamayan değişiklik tamamlanmış değildir.

Oluşturulan her iş yükü şu kontrollerin tamamını karşılamalıdır:

- arka uç ve ön yüz imajı kanonik iç `GHCR` proxy-cache yolundan gelir; GitHub `main` yapısı tam 40
  karakter kaynak commit etiketini yayımlar ve Azure dağıtımı `latest` isteğini aynı
  `BUILD_SOURCEVERSION` etiketine çözer;
- `chart`, `Secret` yazmaz; değer/katman gizli malzeme içermez; iş yükü önceden oluşturulmuş
  `Secret`'a adıyla bağlanır;
- kapsayıcı açıkça kök olmayan kullanıcı/grupla çalışır, ayrıcalık yükseltmeyi kapatır, tüm
  `Linux` yeteneklerini düşürür, `RuntimeDefault` `seccomp` kullanır ve salt okunur kök dosya sistemine
  sahiptir;
- her yazılabilir yol, açıkça boyutu sınırlı bir birimdir;
- kabul edilmiş yetenek `Kubernetes` API erişimi gerektirmedikçe hizmet hesabı belirteci bağlama kapalıdır;
- tüm kapsayıcılar kaynak istek/sınırı bildirir; `HTTP` iş yükü başlatma/hazırlık/canlılık
  yoklaması içerir;
- her iş yükü giriş/çıkış `NetworkPolicy` kuralı içerir; boş eş kümesi izin vermez, reddeder;
- yönetilen test RKE2 hedefinde Ingress controller `kube-system` namespace'indedir; `nginx`
  IngressClass adı namespace adı değildir ve ağ politikası `ingress-nginx` varsayamaz;
- `Service`, `ClusterIP` tipindedir; iş yükü düğüm kapısı, yük dengeleyici veya küme kapsamlı nesne
  oluşturmaz;
- kalıcı birim istemi boyut bildirir; `Job`, `Always` dışı yeniden başlatma politikası kullanır.

Kanonik `values.yaml` `backend` ve `frontend` bölümlerini, ayrıca varsayılanı kapalı `postgres` ve
`migration` bölümlerini taşır. `backend` ve `frontend` bölümleri
`cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/<proje>-<bileşen>` yolunu ve `latest` varsayılanını
taşır; Azure çağrısında `deploy.sh` bu varsayılanı tam kaynak commit etiketiyle ezer. İstenirse açık
bir imaj özeti etikete üstün gelir. Önceden oluşturulmuş `Secret`, backend çıkış eşleri ve ingress
host/TLS değerleri ortam girdisi olarak boş kalır. Backend ve frontend giriş politikaları kanonik RKE2
controller namespace'i `kube-system` için doğru portu önceden taşır. `scripts/render-charts.sh`,
kaydedilmiş ortam katmanı kullanmadan sentetik değerlerle yapısal sözleşmeyi hem veritabanı ve geçiş
kapalıyken hem açıkken kanıtlar.

`postgres.enabled` açıldığında veritabanı iş yükü yukarıdaki kontrollere ek olarak şunları karşılar:

- tek kopya `StatefulSet`'tir ve bileşen etiketi `database`'dir; imaj, yerel Compose'daki PostgreSQL 17
  imajıyla aynı `sha256` özetiyle sabitlenir, özet boşsa işleme durur; ortam depo yolunu özet
  değişmeden kurum içi aynaya çevirebilir;
- veri, boyutu ve depolama sınıfı adı açıkça yazılmış `ReadWriteOnce` kalıcı birim istemindedir;
  depolama sınıfı ortam girdisidir ve boşsa işleme durur;
- kapsayıcı `999` kullanıcı/grubuyla kök olmadan çalışır; `/var/run/postgresql` ve `/tmp` boyutu
  sınırlı birimlerdir; veri sağlama toplamı (`--data-checksums`) açıktır; kapanışa 60 saniye tanınır;
- kimlik bilgileri yalnız önceden oluşturulmuş `postgres.existingSecret`'tan `envFrom` ile gelir;
  başlatma/hazırlık/canlılık yoklamaları yapılandırılmış kullanıcıyla gerçek `SELECT 1` sorgusu
  çalıştırır;
- `NetworkPolicy` girişi yalnız aynı sürümün backend ve geçiş podlarından veritabanı portuna açar;
  çıkış listesi boştur, yani her çıkış reddedilir.

`migration.enabled` yalnız `postgres.enabled` ile birlikte açılır; aksi hâlde işleme durur. Geçiş
`Job`'u şu sözleşmeyi karşılar:

- backend imaj kimliğiyle `alembic upgrade head` çalıştırır; ayrı geçiş imajı yoktur;
- yeniden başlatma politikası `Never`, `backoffLimit` değeri `0`'dır ve `activeDeadlineSeconds` süre
  sınırı vardır; başarısız geçiş yeniden denenmez, incelenir;
- bağlantısını yalnız önceden oluşturulmuş `migration.existingSecret`'tan `envFrom` ile alır; backend
  bu `Secret`'ı görmez;
- `NetworkPolicy` girişi kapatır; çıkışı yalnız küme DNS'ine ve veritabanı portuna açar;
- kimlik bilgisi taşımayan bekleme kapsayıcısı, veritabanı `Service`'i bağlantı kabul edene kadar
  bekler; `Service` bağlantıyı yalnız `SELECT 1` hazırlık yoklaması geçtikten sonra kabul eder;
- çalışma sırası geçişin daha önce çalışıp çalışmadığına göre seçilir: önceki bir sürümün oluşturduğu
  geçiş `NetworkPolicy`'si yoksa (ilk kurulum ya da veritabanını ilk kez ekleyen güncelleme) `Job`
  veritabanıyla aynı anda oluşturulan sıradan sürüm kaynağıdır; varsa `Job` yeni backend
  podlarından önce çalışan `pre-upgrade` Helm kancasıdır (`hook`). Geçiş hiçbir durumda backend'in
  hazır olmasını beklemez; bu yüzden backend hazır olma yoklaması şema güncellenene kadar "hazır
  değil" yanıtı verebilir ve dağıtım kilitlenmez;
- `deploy.sh` Helm'i `--atomic --wait --wait-for-jobs` ile çalıştırır; başarısız geçiş sürümü
  başarısız kılar ve önceki sürüm korunur. Geri almada şema geri indirilmez; geçişler eski sürümün
  çalışabileceği biçimde genişletici yazılır.

Oluşturulan `.github/workflows/image-build.yml`, backend ve frontend imajlarını `main` üzerinde
`latest`, UTC tarih, kısa SHA ve tam SHA etiketleriyle `ghcr.io`'ya yayımlar.
`helm/<ürün-kısa-adı>/deploy.sh`, mevcut Azure `KUBECONFIG` bağını kullanarak Helm'i doğrudan
çalıştırır. Bu teslim hattı ikinci bir yayın
makbuzu, yeniden inceleme veya ayrı audit hunisi gerektirmez. Apply yolu kümede değişiklik yapmadan önce
render edilen her imajın registry'de yayımlandığını sorar ve geç yayını bekler; imaj yayımlanmamışsa
namespace, `Secret` veya Helm değişikliği yapmadan durur. Registry yanıt vermezse bunu belirtir ve
Helm'in hazır podu koruyan rollout güvencesiyle devam eder.
Apply yolu yeni namespace'te eksik olan paylaşılan `ailab-tls` Secret'ını mevcut `kt-verim`
namespace'inden runner kimliğiyle kopyalar; değerleri Git'e, Helm argümanına veya loga yazmaz.
Beklemedeki (`pending-*`) Helm release için önce çalışan işlemin bitmesi beklenir. Yarım kalmış
`pending-upgrade` veya `pending-rollback` son release'e geri alınır; geri alma başarısızsa upgrade
yapılmaz. Hizmet vermiş release kaldırılmaz; yalnız hiç kurulmamış `pending-install` kaldırılır.

Çalışma zamanı veritabanı rolü yalnız `DML` yetkilidir; şemayı yalnız geçiş `Job`'unun `Secret`'ındaki
bağlantı değiştirir. Yayımlanmış `chart` sürümleri değişmezdir. Oluşturma ve hazırlık denetimi
doğrulamadır; dağıtım yetkisi değildir.
