# PRD — kubernetes-delivery

Status: Accepted

Version: 1.0.0

Acceptance date: 2026-09-26

Domain: [application-foundation](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-09-26'da, açık sorulardaki önerileri ve sahip kararlarını
benimseyerek kabul etti.

## Amaç

Uygulamayı PostgreSQL 17 dahil tek Helm chart'ı (Kubernetes'e kurulum paketi) ile nonprod KT Rancher
kümesine, mevcut Azure dağıtım işinin argümansız çağırdığı `helm/dwhcodereview/deploy.sh` üzerinden
güvenle dağıtmak. SQL Server, LLM ve oturum sırları runtime Secret'ta (`dwhcodereview-runtime`)
tutulur; kurallar dosya diskinden PostgreSQL'e taşınır ve şu an çalışan sürümden kayıpsız geçilir.
Chart içi PostgreSQL ve göç Job'u, fabrikanın bunları destekleyen değişikliğinin bu projeye alınmasına
bağlıdır (Decision 3).

## Aktörler ve sonuçlar

- **İşletim ekibi:** Azure dağıtım işini çalıştırır, gizli değişkenleri yönetir. Sonuç: tek komutla
  kurulum veya güncelleme; yayımlanmamış imajda kümeye hiç dokunulmaz, hizmet veren sürüm silinmez.
- **Kullanıcı:** `https://dwhcodereview.ailab-test.kuveytturk.com.tr` adresinden uygulamaya ulaşır;
  geçiş sonrasında yayımlanmış kurallar geçişten öncekiyle birebir aynıdır.
- **Geliştirici:** Aynı yapıyı yerelde Docker Compose ile PostgreSQL 17 üzerinde çalıştırır.

## Değişmezler ve sınırlar

- Decision 1: Tek chart `helm/dwhcodereview/` içinde dört iş yükü vardır: backend, frontend,
  PostgreSQL 17 StatefulSet (kalıcı diskli tek kopya çalışan iş yükü) ve şema göç Job'u (bir kez
  çalışıp biten iş). Redis, gözlemlenebilirlik iş yükü ve kural diski yoktur.
- Decision 2: Chart Secret yazmaz ve değer dosyası sır taşımaz. Sırları `deploy.sh` Azure gizli
  değişkenlerinden yazar; boş veya tanımsız değişken kümedeki mevcut değeri korur.
- Decision 3: Sahibin kararı PostgreSQL'i KT Verim gibi chart içinde çalıştırmaktır. Bugün projeye
  üretilmiş `rules/45-dagitim-hedefi.md` chart'ı backend ve frontend ile sınırlar, `values.yaml`'da
  yalnız bu iki bölüme izin verir ve şema göçünü chart dışında tutar; aynı sınırı fabrika tarafından
  kilitli `scripts/render_charts.py` denetimi uygular. Fabrika bu sınırı kendi değişikliğiyle açıyor
  (Decision 7). Bu PRD'nin PostgreSQL StatefulSet'i ve göç Job'u ile ilgili gereksinimleri o fabrika
  değişikliği fabrikada birleşip bu projeye alındıktan sonra uygulanır; kural ve denetim projede elle
  gevşetilmez.
- Decision 4: `deploy.sh` iskeletteki güvenceleri korur: kümeye dokunmadan önce her imajın
  yayımlandığını doğrular, çalışan (`pending-*`) release'i bekler, yarım kalan güncellemeyi son
  sürüme geri alır ve hizmet vermiş release'i asla kaldırmaz.
- Decision 5: Her iş yükü rules/45 sıkılaştırmasına uyar: kök olmayan kullanıcı, salt okunur kök
  dosya sistemi, boyutu sınırlı yazılabilir alanlar, kapalı ayrıcalık yükseltme, düşürülmüş Linux
  yetenekleri, `RuntimeDefault` seccomp, kapalı hizmet hesabı belirteci, kaynak istek/sınırları,
  yoklamalar ve varsayılanı reddeden NetworkPolicy (pod ağ izin kuralı).
- Decision 6: Çalışma zamanı veritabanı rolü yalnız veri okuma/yazma (DML) yetkilidir; tablo
  oluşturma ve değiştirme yalnız göç Job'unun kullandığı sahip rolündedir.
- Sınır: SQL Server, LLM ve dizin ayarlarının anlamı sırasıyla `sql-review` alanının
  sql-server-connection ve llm-connection PRD'lerinde ile directory-login PRD'sindedir; bu PRD
  yalnız onları kümeye taşır. Kural verisinin tablo biçimi rule-management PRD'sindedir.

## Mevcut davranış

- Kaynak `~/codes/dwhcodereview/helm/dwhcodereview/`: backend `/app/data`'ya 5Gi kalıcı disk (PVC)
  bağlar (`review_rules.json`, `llm_logs/requests.jsonl`); disk `helm.sh/resource-policy: keep` ile
  release silinse de kalır. Sır olmayan ayarlar ConfigMap'tedir. Backend çıkışı `10.0.0.0/8`,
  `172.16.0.0/12`, `192.168.0.0/16` ağlarında 1433, 80, 443'e açıktır. Veritabanı yoktur.
- Kaynak `deploy.sh`: `MSSQL_CONNECTION_STRING`, `MSSQL_PASSWORD`, `API_ACCESS_TOKEN`,
  `API_ADMIN_TOKEN`, `LLM_API_KEY`'i runtime Secret'a yazar; çözülmemiş `$(DEĞİŞKEN)` metnini reddeder;
  Secret değişince backend'i yeniden başlatır; `ailab-tls`'i depodaki zincirle doğrular. İmaj yayınını
  denetlemez. `image-build.yml` iki imajı dört etiketle yayımlar; Compose `./backend/data`'yı bağlar.
- Hedef iskelet: chart yalnız backend/frontend, `existingSecret` ve ingress boş; `deploy.sh` imaj
  yayınını bekler, `ailab-tls`'i `kt-verim`'den kopyalar, `pending-*` durumunu çözer,
  `helm upgrade --install --atomic --wait` çalıştırır, runtime Secret yazmaz. Yerel Compose PostgreSQL
  `17.10` içerir ve dışarı çıkmaz.
- Referans KT Verim `helm/kt-verim/`: tek kopya PostgreSQL StatefulSet (açık depolama sınıfı,
  `psql ... SELECT 1` yoklaması), ilk kurulumda normal Job, güncellemede güncelleme öncesi kanca olan
  göç Job'u (yeniden denemesiz), parola önceliği "pipeline > kümedeki değer > yeni üretim".

Davranış değişiklikleri: kural diski kalkar, veri PostgreSQL'e geçer (Requirement 7, 12); çıkış
kuralları onaylı tek adreslere daralır (Requirement 8); Secret anahtarları `DWHCODEREVIEW_` önekini
alır, `API_ACCESS_TOKEN`/`API_ADMIN_TOKEN` kalkar (Requirement 5); `ailab-tls` kopyası ve imaj
denetimi iskeleti izler; eski adlı Ingress'i silme adımı taşınmaz.

## İşlevsel gereksinimler

Requirement 1: `helm template` çıktısı tam olarak backend ve frontend Deployment'ı, PostgreSQL
StatefulSet'i, göç Job'unu, bunların Service'lerini (hepsi `ClusterIP`), tek Ingress'i ve her iş
yükü için NetworkPolicy'yi üretir; Secret, düğüm kapısı, yük dengeleyici veya küme kapsamlı nesne
üretmez. Chart sürümü eski chart'ın `0.2.0` sürümünden büyüktür.

Requirement 2: PostgreSQL 17 imajı yerel Compose ile aynı sürüm ve özetle (`@sha256`) sabitlenir,
kurum iç registry yolundan çekilir (Decision 8). Tek kopya çalışır; veri, 10Gi boyutlu ve depolama
sınıfı adı açıkça yazılmış ReadWriteOnce PVC'dedir; kaynak isteği 100m CPU/256Mi, sınırı 1 CPU/1Gi'dir
(Decision 9). Veri sağlama
toplamı (`--data-checksums`) açıktır; yoklamalar gerçek kullanıcıyla `SELECT 1` çalıştırır; kapanışa
60 saniye tanınır; SQL cümlesi loglama kapalıdır (parametre değerleri loga düşmesin diye).

Requirement 3: İlk kurulumda boş veri dizininde sahip rolü ve yalnız DML yetkili uygulama rolü
oluşur. Göçler uygulama rolüne yeni tablolarda DML yetkisi verir. Backend yalnız uygulama rolüyle
bağlanır; sahip rolünün bağlantısı yalnız göç Job'unda bulunur.

Requirement 4: Şema göçü `alembic upgrade head` komutudur ve backend imajıyla çalışır (ayrı göç imajı
yoktur). Veritabanını ilk kez getiren kurulumda veya yükseltmede Job, PostgreSQL ile aynı adımda
oluşur ve veritabanı bağlantı kabul edene kadar bekler; sonraki güncellemelerde yeni backend
podlarından önce çalışan kanca olarak koşar. Job'un toplam süresi `activeDeadlineSeconds` (varsayılan
600 saniye) ile sınırlıdır ve yeniden denenmez (`backoffLimit: 0`); `deploy.sh` Job'un bitmesini de
bekler, başarısız göç güncellemeyi durdurur ve `--atomic` önceki sürümü korur. Backend hazır olma yoklaması şema imajın
beklediği sürüme gelene kadar 503 döner. Göçler yalnız genişletici yazılır (eski sürüm yeni şemayla
çalışabilir), çünkü geri almada şema geri indirilmez.

Requirement 5: Runtime Secret `dwhcodereview-runtime` anahtarları ve kaynakları:

| Secret anahtarı | Kaynak | İlk kurulumda yoksa |
|---|---|---|
| `DWHCODEREVIEW_MSSQL_USER` | Azure gizli değişkeni `MSSQL_USER` | Uyarı; SQL Server incelemesi çalışmaz |
| `DWHCODEREVIEW_MSSQL_PASSWORD` | Azure gizli değişkeni `MSSQL_PASSWORD` | Uyarı; SQL Server incelemesi çalışmaz |
| `DWHCODEREVIEW_LLM_API_KEY` | Azure gizli değişkeni `LLM_API_KEY` | Sorun değil; nonprod LLM ucu anahtar istemiyor |
| `DWHCODEREVIEW_JWT_PRIVATE_KEY` | Azure gizli değişkeni `JWT_PRIVATE_KEY` verilirse o; verilmezse `deploy.sh` P-256 anahtarını CSPRNG ile bir kez üretir ve Secret'ta anahtar varken yeniden üretmez (Decision 14) | Üretir |
| `DWHCODEREVIEW_DATABASE_URL` | `deploy.sh`, uygulama rolü parolası ve chart içi PostgreSQL adresinden | Üretir |
| Sır olmayan ayarlar (dizin; SQL Server adresi, portu ve izinli veritabanı listesi; LLM adresi, modeli ve süreç geneli çağrı sınırı) | `deploy.sh` nonprod varsayılanı; aynı adlı pipeline değişkeni ezer | Varsayılanı yazar |

Boş veya tanımsız değişken mevcut değeri korur. Çözülmemiş Azure `$(DEĞİŞKEN)` metni Secret'a
yazılmadan reddedilir. Değerler komut argümanına, Helm değerine ve loga girmez; logda yalnız anahtar
adı görünür. Secret değişip backend pod şablonu değişmediyse backend yeniden başlatılır. Anahtar adları
[SQL Server bağlantısı](../../../sql-review/PRDs/002-sql-server-connection/PRD.md) ve
[LLM bağlantısı](../../../sql-review/PRDs/006-llm-connection/PRD.md) PRD'lerindeki adlarla aynıdır.
Ortam değeri chart'ın backend değerlerinde `DWHCODEREVIEW_ENVIRONMENT=staging` olarak sabittir; bu,
[alan belgesindeki](../../DOMAIN.md) `nonprod` Ortamıdır.

Requirement 6: PostgreSQL parolaları ayrı `dwhcodereview-postgres` Secret'ındadır; `deploy.sh` onları
ilk kurulumda CSPRNG (tahmin edilemez rastgele üreteç) ile üretir ve Secret varken asla yeniden
üretmez (veritabanı ilk parolayı diskte tuttuğu için). Backend bu Secret'ı görmez.

Requirement 7: Backend'e kural diski bağlanmaz; yazılabilir tek alanı boyutu sınırlı `/tmp`'dir.
Kurallar, inceleme sonuçları ve LLM çağrı özetleri PostgreSQL'dedir. Eski PVC (`dwhcodereview`)
güncellemeyle silinmez; Requirement 12 doğrulanana ve geri alma süresi (Acceptance 3'ten iki hafta
sonra, Decision 13) bitene kadar kalır.

Requirement 8: Ağ kuralları (varsayılan: her şey kapalı):

| İş yükü | Giriş | Çıkış |
|---|---|---|
| backend | `kube-system` ingress denetleyicisi, TCP 8000 | DNS (`kube-system`, 53); PostgreSQL 5432; SQL Server `/32` adresi, yapılandırılan port (varsayılan 1433) (Decision 11); LLM `10.14.3.99/32` 443; LDAPS `10.13.9.1/32` 636 |
| frontend | `kube-system` ingress denetleyicisi, TCP 8080 | Yok |
| PostgreSQL | Yalnız backend ve göç Job'u, TCP 5432 | Yok |
| göç Job'u | Yok | DNS; PostgreSQL 5432 |

Dış adresler `deploy.sh`'ın nonprod girdileridir; `0.0.0.0/0` ve boş liste reddedilir. Listede
olmayan hedefe backend'den bağlantı kurulamaz.

Requirement 9: `.github/workflows/image-build.yml` `main` dalından yalnız backend ve frontend
imajlarını iskeletin release Dockerfile'larıyla üretir ve `ghcr.io/kt-vibecoding/dwhcodereview-backend`
ile `-frontend` adlarına `latest`, UTC tarih, kısa ve tam commit etiketiyle yayımlar. Küme onları
`cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/dwhcodereview-{backend,frontend}` yolundan çeker.
Dizin CA bundle'ı backend imajına herkese açık sertifika dosyası olarak girer.

Requirement 10: Argümansız `deploy.sh` şu sırayı izler: girdileri doğrular; Azure `latest` isteğini
tam 40 karakterlik `BUILD_SOURCEVERSION` etiketine çözer; PostgreSQL dahil her imajın yayımını
`IMAGE_WAIT_SECONDS` (20 dakika) bekler ve yoksa kümeye dokunmadan durur; namespace'i ve eksikse
`ailab-tls`'i hazırlar; iki Secret'ı hazırlar; zorunlu anahtar eksikse durur; `pending-*` release'i
çözer; `helm upgrade --install --atomic --wait --timeout 30m` çalıştırır; gerekirse backend'i yeniden
başlatır. Ingress `nginx` sınıfıyla `dwhcodereview.ailab-test.kuveytturk.com.tr` adresini `ailab-tls`
ile sunar. `--render` kümeye erişmeden aynı değerlerle çıktı üretir.

Requirement 11: Yerel Compose iskeletin `scripts/stack.sh` akışıyla PostgreSQL 17, backend, frontend
ve nginx'i başlatır; göçler `scripts/db.sh apply` ile uygulanır; yerel sırlar Git dışında üretilir.
Varsayılan yerel ağ dışarı çıkmaz; SQL Server ve LLM'e yerel erişim yalnız açıkça seçilen ayrı bir
Compose profiliyle açılır (Decision 15).

Requirement 12: Kurallar PostgreSQL'e [kural yönetimi PRD'sinin](../../../sql-review/PRDs/001-rule-management/PRD.md)
Requirement 9'daki içe aktarım göçüyle, göç Job'u içinde girer; ayrı bir aktarım komutu yoktur
(Decision 12). Güncellemeden önce işletim ekibi çalışan eski backend'deki `review_rules.json`
dosyasının SHA-256 parmak izini salt okunur alır; iz o gereksinimdeki izle aynı değilse güncelleme
başlamaz. Güncellemeden sonra kural sayısı ve kimlik+metin içerik özeti eski dosyayla eşittir. LLM
günlük dosyası aktarılmaz; eski diskte kalır.

Requirement 13: Geri alma: başarısız güncelleme `--atomic` ile kendiliğinden önceki sürüme döner;
elle geri alma `helm rollback` ile yapılır ve şemayı geri indirmez. Geçiş öncesi sürüme dönüş,
korunan eski disk ve eski Secret anahtarları sayesinde eski uygulamayı geçiş anındaki kurallarla
açar; geçişten sonra PostgreSQL'de yapılan kural değişiklikleri eski uygulamaya taşınmaz.

## API sözleşmesi

N/A — HTTP API yoktur. Dağıtım arayüzü: `helm/dwhcodereview/deploy.sh [--render|--apply]`;
argümansız çağrı `--apply`, kanonik `values.yaml`, release ve namespace `dwhcodereview` demektir.
Girdiler ortam değişkenidir: `IMAGE_TAG`, `BUILD_SOURCEVERSION`, `TF_BUILD`, Requirement 5'teki gizli
değişkenler, sır olmayan ayar değişkenleri, çıkış adresleri, `IMAGE_WAIT_SECONDS`,
`PENDING_WAIT_SECONDS`, `HELM_TIMEOUT`. Çıkış kodu 0 başarı, 1 dağıtım hatası, 2 geçersiz girdidir;
log işaretleri `[IMAGE]`, `[RUNTIME]`, `[RELEASE]`, `[MIGRATION]` önekini taşır.

## Güvenlik ve yetkilendirme

- `deploy.sh` mevcut Azure `KUBECONFIG` bağlantısını kullanır; kubeconfig içeriği, Secret değeri ve
  registry belirteci loga yazılmaz; geçici dosyalar yalnız sahibine açıktır.
- Süper yönetici oluşturma dağıtımın parçası değildir; rules/58 gereği işletim ekibi elle yapar.
- Eski geniş çıkış kuralı taşınmaz; SQL Server'a yalnız onaylı adreslerden gidilir.

## Veri ve geçiş

- Kalıcı veri yalnız PostgreSQL PVC'sindedir. StatefulSet disk talebi release kaldırılsa da silinmez.
- Geçiş sırası: (1) eski backend çalışırken kural dosyasının parmak izi salt okunur alınır ve
  Requirement 12'ye göre karşılaştırılır, (2) yeni chart aynı release ve namespace'e kurulur, (3) göç
  Job'u (Requirement 4) şemayı kurar ve kuralları içe aktarır, (4) kural sayısı ve içerik özeti eski
  dosyayla karşılaştırılır. Backend hazır olma yoklaması şema beklenen sürüme gelene kadar 503
  döndüğü için yeni sürüm yayımlanmış kurallarla hizmet vermeye başlar.
- Eski PVC, eski Secret anahtarları (`MSSQL_CONNECTION_STRING`, `API_ACCESS_TOKEN`, `API_ADMIN_TOKEN`
  ve öneksiz diğerleri) ve eski Azure değişkenleri geri alma süresi bitene kadar kalır; sonra işletim
  ekibi tek elle adımla siler (Decision 13).
- Yedekleme Decision 10'dadır.

## Gözlemlenebilirlik

`deploy.sh` her adımı sabit işaretle yazar (imaj yayımı, Secret anahtar adları, release durumu, göç
sonucu); hata iletisi girilen değeri yankılamaz. PostgreSQL ve backend logları stdout'a gider; chart
gözlemlenebilirlik iş yükü içermez (rules/25 ayrı PRD ister). Yeni ölçüm tanımlanmaz.

## Dağıtım etkisi

Mevcut Azure işi aynı komutla çalışmaya devam eder; yeni gizli değişken `MSSQL_USER` Azure
kitaplığına eklenir, `JWT_PRIVATE_KEY` isteğe bağlıdır (Decision 14); `API_ACCESS_TOKEN` ve
`API_ADMIN_TOKEN` geri alma süresinden sonra kaldırılır. Namespace'te PostgreSQL diski ve `dwhcodereview-postgres` Secret'ı
oluşur. Küme tarafında depolama sınıfı ve LDAPS/SQL Server/LLM ağ erişimi gerekir.

## Test stratejisi

- Chart: `helm lint`, render ve yapı testleri; her iş yükünde sıkılaştırma, yoklama ve kaynak
  denetimi; Secret üretilmemesi; kural diskinin olmaması; boş veya `0.0.0.0/0` çıkış listesinin reddi.
- `deploy.sh`: sahte `kubectl`/`helm`/registry ile Secret birleştirme, boş değişkenin korunması, JWT
  anahtarının ilk kurulumda bir kez üretilip sonraki çalıştırmalarda korunması,
  `$(...)` reddi, değerin argümana ve loga düşmemesi, yayımlanmamış imajda kümeye dokunmama,
  `pending-*` bekleme ve geri alma, hizmet vermiş release'in kaldırılmaması, gereksiz restart olmaması.
- Göç: boş veritabanında `alembic upgrade head`, uygulama rolünün tablo oluşturamaması.
- Aktarım: göç Job'u boş veritabanında içe aktarım göçünü çalıştırır, kural sayısı ve içerik özeti
  depodaki `review_rules.json` kopyasıyla eşleşir, tekrar çalıştırmada değişiklik olmaz (göçün kendi
  testleri kural yönetimi PRD'sindedir).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: chart, `deploy.sh`, göç ve aktarım testleri
  Requirement 1–10, 12 ve 13 için geçer; güncellenmiş chart denetimi kırmızı değildir.
- [ ] Acceptance 2: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da PostgreSQL 17 çalışır,
  göç uygulanır, hazır olma yoklaması 200 döner, tarayıcıda giriş ve kural ekranı açılır; içe
  aktarılan kural sayısı ve içerik özeti depodaki `review_rules.json` kopyasıyla eşleşir
  (Requirement 11, 12).
- [ ] Acceptance 3: L2 — Canlı nonprod küme koşumu (yerel kanıttan ayrı): argümansız Azure işi
  release'i kurar; podlar hazır, PostgreSQL diski bildirilen boyut ve sınıfta bağlı, göç Job'u
  başarılı; HTTPS adresi `ailab-tls` ile açılır; backend LDAPS, SQL Server ve LLM'e ulaşır, listede
  olmayan adrese ulaşamaz; eski diskteki dosyanın parmak izi kural yönetimi Requirement 9'daki izle
  aynıdır ve PostgreSQL'deki kurallar onunla eşleşir; eski disk yerindedir (Requirement 1–10, 12).
- [ ] Acceptance 4: L2 — Nonprod'da sahibin izniyle geri alma provası: bir önceki sürüme
  `helm rollback` sonrası uygulama hazır olur ve veri kaybı olmaz (Requirement 13).

## Kararlar

- Decision 7: Chart içi veritabanı fabrikada çözülür: fabrika `feat/chart-postgres-workload` dalında
  (fabrika deposunun `main` dalına açılan `PR`) üretilen chart'lara açık seçimle (`opt-in`, yalnız
  istenirse) etkinleşen bir PostgreSQL 17 StatefulSet'i ve Alembic göç Job'u ekliyor. Bu PRD o
  değişikliğin fabrikada birleşmesine ve bu projeye alınmasına bağlıdır (Decision 3).
- Decision 8: PostgreSQL imajı yerel Compose'daki `postgres:17.10` ile aynı özettedir; kurum iç
  registry yolu, KT Verim'in çalışan PostgreSQL podunun imaj adı salt okunur sorgulanarak belirlenir ve
  Decision 7'deki fabrika değişikliğinin imaj yolu kuralına uyar.
- Decision 9: PostgreSQL diski 10Gi'dir; depolama sınıfı KT Verim PostgreSQL diskininkiyle aynıdır ve
  açıkça yazılır; kaynak isteği 100m CPU/256Mi, sınırı 1 CPU/1Gi'dir (Requirement 2).
- Decision 10: Yedek günlük `pg_dump` ile ayrı 5Gi diske alınır ve 7 gün saklanır; kurumun yedekleme
  hizmeti varsa o tercih edilir. Decision 7'deki fabrika değişikliği yalnız StatefulSet'i ve göç Job'unu
  getirdiği için yedek `CronJob`'u (zamanlanmış iş) chart'a, fabrika bu iş yükünü de desteklediğinde bu
  PRD'nin revizyonuyla girer; o zamana kadar yedek bu teslimin parçası değildir.
- Decision 11: SQL Server çıkışı yalnız işletim ekibinin verdiği nonprod SQL Server `/32` adresine ve
  yapılandırılan SQL Server portuna (varsayılan 1433) açılır
  ([SQL Server bağlantısı PRD'si](../../../sql-review/PRDs/002-sql-server-connection/PRD.md)
  Decision 9); eski geniş kural ve 80 portu kaldırılır.
- Decision 12: Kural dosyası kümeye taşınmaz; kurallar kural yönetimi PRD'sinin içe aktarım göçüyle
  girer ve işletim ekibi yalnız eski dosyanın parmak izini karşılaştırır (Requirement 12). Böylece elle
  dosya taşıma, `kubectl exec` ile veri verme ve geçici pod gerekmez.
- Decision 13: Eski disk, eski Secret anahtarları ve eski Azure değişkenleri Acceptance 3'ten iki hafta
  sonra işletim ekibinin elle yaptığı tek adımla silinir; `deploy.sh` hiç anahtar silmez.
- Decision 14: JWT imza anahtarı Azure değişkeninde taşınmaz; `deploy.sh` ilk kurulumda P-256 anahtarını
  bir kez üretir ve korur, pipeline değişkeni verilirse o geçerlidir (Requirement 5).
- Decision 15: Yerel Compose varsayılan olarak SQL Server ve LLM'e çıkmaz; isteyen geliştirici için
  açıkça seçilen ayrı bir Compose profili vardır (Requirement 11).
- Decision 16: Yeni kod mevcut `kt-vibecoding/DWHCodeReview` deposunun `main` dalından yayımlanır; GHCR
  paket adları ve Azure işi bu depoya bağlıdır (Requirement 9).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- Decision 7'deki fabrika değişikliği birleşip projeye alınmadan chart denetimi PostgreSQL ve göç
  Job'u için kırmızı kalır; denetimi projede gevşetmek kuralı sessizce zayıflatmak olur.
- Tek kopya PostgreSQL'de disk arızası, yedek (Decision 10) devreye girene kadar veri kaybıdır.
- İlk güncelleme eski chart'tan yeni chart'a aynı release'te yapılır; beklenmeyen nesne çakışması
  `--atomic` ile eski sürüme döner ve geçiş ertelenir.
- Geri almada şema geri inmez; genişletici olmayan göç eski sürümü bozar.
- Nonprod'daki kural dosyası depodaki kopyadan farklıysa geçiş, kopya ve kural yönetimi PRD'sindeki
  parmak izi yenilenene kadar bekler.
- Parmak izi alındıktan sonra eski uygulamada yapılan kural değişikliği yeni sürüme taşınmaz; geçiş
  penceresinde kural düzenleme durdurulmalıdır.
