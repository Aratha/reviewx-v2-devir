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
noktası aynı dizindeki `deploy.sh` dosyasıdır. `chart` kendi kendine yeterlidir; yalnız arka uç ve ön
yüz iş yüklerini içerir. Alt `chart`, ortam katmanı, bağımlılık arşivi veya çalışma zamanı indirmesi
içermez.
Bu hedefi karşılayamayan değişiklik tamamlanmış değildir.

Oluşturulan her iş yükü şu kontrollerin tamamını karşılamalıdır:

- imaj, kanonik iç `GHCR` proxy-cache yolundan gelir; GitHub `main` yapısı tam 40 karakter kaynak
  commit etiketini yayımlar ve Azure dağıtımı `latest` isteğini aynı `BUILD_SOURCEVERSION` etiketine
  çözer;
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

Kanonik `values.yaml` yalnız `backend` ve `frontend` bölümlerini taşır. Her bileşen
`cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/<proje>-<bileşen>` yolunu ve `latest` varsayılanını
taşır; Azure çağrısında `deploy.sh` bu varsayılanı tam kaynak commit etiketiyle ezer. İstenirse açık
bir imaj özeti etikete üstün gelir. Önceden oluşturulmuş `Secret`, backend çıkış eşleri ve ingress
host/TLS değerleri ortam girdisi olarak boş kalır. Backend ve frontend giriş politikaları kanonik RKE2
controller namespace'i `kube-system` için doğru portu önceden taşır. `scripts/render-charts.sh`,
kaydedilmiş ortam katmanı kullanmadan sentetik değerlerle yapısal sözleşmeyi kanıtlar.

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

Çalışma zamanı veritabanı rolü yalnız `DML` yetkilidir. Şema geçişi bu uygulama `chart`'ının parçası
değildir ve ayrı yönetişim akışında yürütülür. Yayımlanmış `chart` sürümleri değişmezdir. Oluşturma ve
hazırlık denetimi doğrulamadır; dağıtım yetkisi değildir.
