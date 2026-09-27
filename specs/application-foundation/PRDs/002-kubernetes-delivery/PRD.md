# PRD — kubernetes-delivery

Status: Accepted

Version: 1.4.0

Acceptance date: 2026-09-27

Domain: [application-foundation](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-09-27'de, Decision 17'deki sahip kararıyla ve
directory-login PRD'sinin Decision 13'teki nonprod ilk süper yönetici kararıyla hizalanmış haliyle
kabul etti.

## Amaç

Uygulamayı PostgreSQL 17 dahil tek Helm chart'ı (Kubernetes'e kurulum paketi) ile nonprod KT Rancher
kümesine, mevcut Azure dağıtım işinin argümansız çağırdığı `helm/dwhcodereview/deploy.sh` üzerinden
güvenle dağıtmak. Nonprod dağıtımı işletim ekibinin ayar veya gizli değişken vermesini beklemeden
çalışır (Decision 17): ortam adresleri ve sır olmayan ayarlar projeye ait değer katmanı
`helm/dwhcodereview/values-project.yaml` dosyasında, oturum imza anahtarı, isteğe bağlı SQL Server
ve LLM kimlik bilgileri ve isteğe bağlı süper yönetici başlangıç parolası projeye ait kanca
`helm/dwhcodereview/deploy-hooks.sh`'ın hazırladığı runtime Secret'tadır (`dwhcodereview-runtime`);
veritabanı sırlarını `deploy.sh` üretir. Kurallar
PostgreSQL'e içe aktarım göçüyle girer.

## Aktörler ve sonuçlar

- **İşletim ekibi:** Azure dağıtım işini çalıştırır. Sonuç: tek komutla kurulum veya güncelleme; ek
  ayar veya gizli değişken gerekmez; yayımlanmamış imajda kümeye hiç dokunulmaz, hizmet veren sürüm
  silinmez. SQL Server hesabını vermek isterse `MSSQL_USER`/`MSSQL_PASSWORD` gizli değişkenlerini
  tanımlar.
- **Proje sahibi:** Nonprod `admin` süper yöneticisinin ilk parolasını seçer ve Azure gizli
  değişkeni `DWHCODEREVIEW_ADMIN_PASSWORD` olarak tanımlar. Sonuç: ilk dağıtımdan sonra `admin`
  girer; sonraki dağıtımlar hesaba dokunmaz
  ([directory-login](../001-directory-login/PRD.md) Requirement 14, Decision 13).
- **Kullanıcı:** `https://dwhcodereview.ailab-test.kuveytturk.com.tr` adresinden uygulamaya ulaşır;
  yayımlanmış kurallar depodaki içe aktarım kopyasıyla birebir aynıdır.
- **Geliştirici:** Aynı yapıyı yerelde Docker Compose ile PostgreSQL 17 üzerinde çalıştırır.

## Değişmezler ve sınırlar

- Decision 1: Tek chart `helm/dwhcodereview/` içinde dört iş yükü vardır: backend, frontend,
  PostgreSQL 17 StatefulSet (kalıcı diskli tek kopya çalışan iş yükü) ve şema göç Job'u (bir kez
  çalışıp biten iş). Redis, gözlemlenebilirlik iş yükü ve kural diski yoktur.
- Decision 2: Chart Secret yazmaz; `values.yaml` ve `values-project.yaml` sır taşımaz. Runtime
  Secret'ı `deploy-hooks.sh`, veritabanı Secret'larını `deploy.sh` kümede hazırlar; boş veya
  tanımsız değişken kümedeki mevcut değeri korur.
- Decision 3: PostgreSQL, KT Verim'deki gibi chart içinde çalışır. Fabrikanın `rules/45-dagitim-hedefi.md`
  kuralı chart içi PostgreSQL'i ve göç Job'unu açık seçimle (`opt-in`) destekler ve kilitli
  `scripts/render_charts.py` denetimiyle uygular; bu proje ikisini `values-project.yaml` ile açar.
  Kural ve denetim projede elle gevşetilmez.
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

- Kümede çalışan eski release (`dwhcodereview` release'i ve namespace'i, 2026-09-27 salt okunur
  gözlem): backend ve frontend Deployment'ları, `dwhcodereview-dwhcodereview-entry-08473377d7fb`
  Ingress'i, backend ConfigMap'i ve backend'e `/app/data` için bağlı 5Gi `nfs-sc` PVC
  `dwhcodereview-backend-data` (`helm.sh/resource-policy: keep`). İş yükü adları yeni chart'ın
  ürettiği adlarla aynıdır; güncelleme aynı nesneleri yerinde değiştirir. Eski uygulama kural
  dosyası yerine koddaki 25 varsayılan kuralla çalışıyordu (disk imajdaki dosyayı örtmüştü); bu
  yüzden taşınacak kural verisi yoktur (Decision 12).
- Kaynak `deploy.sh`: `MSSQL_CONNECTION_STRING`, `MSSQL_PASSWORD`, `API_ACCESS_TOKEN`,
  `API_ADMIN_TOKEN`, `LLM_API_KEY`'i runtime Secret'a öneksiz yazar; çözülmemiş `$(DEĞİŞKEN)`
  metnini reddeder; Secret değişince backend'i yeniden başlatır; `ailab-tls`'i depodaki zincirle
  doğrular. İmaj yayınını denetlemez. `image-build.yml` iki imajı dört etiketle yayımlar.
- Hedef iskelet: chart backend, frontend ve açık seçimle PostgreSQL ile göç Job'u; `deploy.sh`
  imaj yayınını bekler, `ailab-tls`'i `kt-verim`'den kopyalar, varsa proje kancasını çalıştırır,
  veritabanı Secret'larını üretir, `pending-*` durumunu çözer ve
  `helm upgrade --install --atomic --wait --wait-for-jobs` çalıştırır. Yerel Compose PostgreSQL
  `17.10` içerir ve dışarı çıkmaz.
- Referans KT Verim `helm/kt-verim/`: tek kopya PostgreSQL StatefulSet (`nfs-sc` depolama sınıfı,
  `postgres:17-alpine` imajı düğümün Docker Hub aynasından çekilir), sır önceliği "pipeline >
  kümedeki değer > yeni üretim".

Davranış değişiklikleri: kural diski kalkar, veri PostgreSQL'e geçer (Requirement 7, 12); çıkış
kuralları onaylı adreslere daralır (Requirement 8); Secret anahtarları `DWHCODEREVIEW_` önekini
alır, `API_ACCESS_TOKEN`/`API_ADMIN_TOKEN` kalkar (Requirement 5); sır olmayan ayarlar pipeline
değişkeni yerine `values-project.yaml`'dan gelir; `ailab-tls` kopyası ve imaj denetimi iskeleti
izler; eski adlı Ingress'i silme adımı taşınmaz.

## İşlevsel gereksinimler

Requirement 1: `helm template` çıktısı tam olarak backend ve frontend Deployment'ı, PostgreSQL
StatefulSet'i, göç Job'unu, bunların Service'lerini (hepsi `ClusterIP`), tek Ingress'i ve her iş
yükü için NetworkPolicy'yi üretir; Secret, düğüm kapısı, yük dengeleyici veya küme kapsamlı nesne
üretmez. Chart sürümü eski chart'ın `0.2.0` sürümünden büyüktür.

Requirement 2: PostgreSQL 17 imajı yerel Compose ile aynı sürüm ve özetle (`@sha256`) sabitlenir ve
KT Verim'in çektiği yoldan, düğümün Docker Hub aynası üzerinden `postgres` deposundan çekilir
(Decision 8). Tek kopya çalışır; veri, 10Gi boyutlu ve depolama sınıfı `nfs-sc` açıkça yazılmış
ReadWriteOnce PVC'dedir; kaynak isteği 100m CPU/256Mi, sınırı 1 CPU/1Gi'dir (Decision 9). Veri
sağlama toplamı (`--data-checksums`) açıktır; yoklamalar gerçek kullanıcıyla `SELECT 1` çalıştırır;
kapanışa 60 saniye tanınır; SQL cümlesi loglama kapalıdır (parametre değerleri loga düşmesin diye).

Requirement 3: İlk kurulumda boş veri dizininde sahip rolü oluşur. Göç Job'u Alembic'ten önce, sahip
rolüyle, süper kullanıcı olmayan ve yalnız `SELECT`, `INSERT`, `UPDATE`, `DELETE` ile dizi kullanımı
yetkili uygulama rolünü oluşturur veya günceller; varsayılan yetkiler Alembic'in sonradan oluşturduğu
tablolara da uzanır. Backend yalnız uygulama rolüyle bağlanır; sahip rolünün bağlantısı yalnız göç
Job'unda bulunur.

Requirement 4: Şema göçü `alembic upgrade head` komutudur ve backend imajıyla çalışır (ayrı göç imajı
yoktur). Veritabanını ilk kez getiren kurulumda veya yükseltmede Job, PostgreSQL ile aynı adımda
oluşur ve veritabanı bağlantı kabul edene kadar bekler; sonraki güncellemelerde yeni backend
podlarından önce çalışan kanca olarak koşar. Job'un toplam süresi `activeDeadlineSeconds` (varsayılan
600 saniye) ile sınırlıdır ve yeniden denenmez (`backoffLimit: 0`); `deploy.sh` Job'un bitmesini de
bekler, başarısız göç güncellemeyi durdurur ve `--atomic` önceki sürümü korur. Backend hazır olma yoklaması şema imajın
beklediği sürüme gelene kadar 503 döner. Göçler yalnız genişletici yazılır (eski sürüm yeni şemayla
çalışabilir), çünkü geri almada şema geri indirilmez.

Requirement 5: Runtime Secret `dwhcodereview-runtime`'ı `helm/dwhcodereview/deploy-hooks.sh`
hazırlar. Anahtarları ve kaynakları:

| Secret anahtarı | Kaynak | Hiç verilmezse |
|---|---|---|
| `DWHCODEREVIEW_JWT_PRIVATE_KEY` | Azure gizli değişkeni `JWT_PRIVATE_KEY` verilirse o; yoksa kümedeki değer; o da yoksa kanca P-256 anahtarını CSPRNG ile bir kez üretir (Decision 14) | Üretir |
| `DWHCODEREVIEW_MSSQL_USER` | İsteğe bağlı Azure gizli değişkeni `MSSQL_USER`; yoksa kümedeki değer | Yazılmaz; uygulama açılır, SQL Server alanı "yapılandırılmamış" görünür |
| `DWHCODEREVIEW_MSSQL_PASSWORD` | İsteğe bağlı Azure gizli değişkeni `MSSQL_PASSWORD`; yoksa kümedeki değer | Yazılmaz; uygulama açılır, SQL Server alanı "yapılandırılmamış" görünür |
| `DWHCODEREVIEW_LLM_API_KEY` | İsteğe bağlı Azure gizli değişkeni `LLM_API_KEY`; yoksa kümedeki değer | Yazılmaz; nonprod LLM ucu anahtar istemiyor |
| `DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD` | İsteğe bağlı Azure gizli değişkeni `DWHCODEREVIEW_ADMIN_PASSWORD`; yoksa kümedeki değer | Yazılmaz; backend süper yönetici açmaz ([directory-login](../001-directory-login/PRD.md) Requirement 14) |

Boş veya tanımsız değişken ve çözülmemiş Azure `$(DEĞİŞKEN)` metni verilmemiş sayılır; kümedeki
mevcut değer korunur. Kümedeki Secret okunamazsa kanca hiçbir şeyi değiştirmeden durur; geçersiz
`JWT_PRIVATE_KEY` veya denetim karakteri içeren `MSSQL_USER` da dağıtımı Helm değişikliğinden önce
durdurur. Kanca Secret'taki başka anahtarlara dokunmaz. Değerler komut argümanına, Helm değerine ve
loga girmez, `kubectl`'e yalnız sahibine özel geçici dosyalardan geçer; logda yalnız anahtar adı
görünür. Secret değiştiğinde kümede aynı imaj etiketiyle çalışan backend varsa (Helm pod şablonunu
değiştirmeyeceği için) kanca onu yeniden başlatır. Anahtar adları
[SQL Server bağlantısı](../../../sql-review/PRDs/002-sql-server-connection/PRD.md) ve
[LLM bağlantısı](../../../sql-review/PRDs/006-llm-connection/PRD.md) PRD'lerindeki adlarla aynıdır.
Sır olmayan ayarlar `values-project.yaml` içindeki `backend.config` alanındadır: ortam
`DWHCODEREVIEW_ENVIRONMENT=staging` ([alan belgesindeki](../../DOMAIN.md) `nonprod` Ortamı), uygulamanın
genel adresi ve CORS kaynağı, güvenilen ingress pod ağı `10.42.0.0/16`, dizin ayarları
(directory-login PRD'sindeki KT Verim nonprod değerleri ve imajdaki CA dosyası), süper yönetici hesap
adı `DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_USERNAME=admin`, LLM biçimi, adresi ve modeli
(llm-connection Decision 3) ve boş OpenTelemetry adresi. SQL Server adresi, portu ve izinli
veritabanı listesi işletim ekibinden gelene kadar yazılmaz; bu sürede SQL Server alanı
"yapılandırılmamış" kalır (sql-server-connection Decision 11).

Requirement 6: Chart içi veritabanının sırları `deploy.sh`'ın ürettiği üç Secret'tadır:
`dwhcodereview-postgres` (sahip rolü), `dwhcodereview-migration` (sahip rolünün bağlantısı ve
uygulama rolünün adı ile parolası) ve `dwhcodereview-database` (uygulama rolünün
`DWHCODEREVIEW_DATABASE_URL` bağlantısı). Parolalar ilk kurulumda CSPRNG (tahmin edilemez rastgele
üreteç) ile üretilir ve Secret varken yeniden üretilmez (veritabanı ilk parolayı diskte tuttuğu için).
Backend yalnız `dwhcodereview-database`'i görür.

Requirement 7: Backend'e kural diski bağlanmaz; yazılabilir tek alanı boyutu sınırlı `/tmp`'dir.
Kurallar, inceleme sonuçları ve LLM çağrı özetleri PostgreSQL'dedir. Eski PVC
`dwhcodereview-backend-data` yeniden kullanılmaz; yeni sürüm nonprod'da sağlıklı açıldıktan sonra
2026-09-27'de silindi (Decision 13).

Requirement 8: Ağ kuralları (varsayılan: her şey kapalı):

| İş yükü | Giriş | Çıkış |
|---|---|---|
| backend | `kube-system` ingress denetleyicisi, TCP 8000 | DNS (`kube-system` `kube-dns`, 53); PostgreSQL 5432; SQL Server `10.0.0.0/8` TCP 1433 (Decision 11); LLM `10.14.3.99/32` 443; LDAPS `10.13.9.1/32` 636 |
| frontend | `kube-system` ingress denetleyicisi, TCP 8080 | Yok |
| PostgreSQL | Yalnız backend ve göç Job'u, TCP 5432 | Yok |
| göç Job'u | Yok | DNS; PostgreSQL 5432 |

Dış adresler `values-project.yaml`'dadır; `scripts/render-charts.sh` boş eşi ve `/8`'den geniş
adres bloğunu reddeder. Listede olmayan hedefe backend'den bağlantı kurulamaz.

Requirement 9: `.github/workflows/image-build.yml` `main` dalından yalnız backend ve frontend
imajlarını iskeletin release Dockerfile'larıyla üretir ve `ghcr.io/kt-vibecoding/dwhcodereview-backend`
ile `-frontend` adlarına `latest`, UTC tarih, kısa ve tam commit etiketiyle yayımlar. Küme onları
`cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/dwhcodereview-{backend,frontend}` yolundan çeker.
Dizin CA bundle'ı backend imajına herkese açık sertifika dosyası olarak
`/workspace/app/backend/certs/nonprod-directory-ca.crt` yolunda girer.

Requirement 10: Argümansız `deploy.sh` şu sırayı izler: girdileri doğrular; `values.yaml`'ın üstüne
`values-project.yaml`'ı katmanlar; Azure `latest` isteğini tam 40 karakterlik `BUILD_SOURCEVERSION`
etiketine çözer; her imajın yayımını `IMAGE_WAIT_SECONDS` (20 dakika) bekler ve yoksa kümeye
dokunmadan durur (düğüm aynasından çekilen PostgreSQL imajı için kayıt defteri yanıtı alınamaz; bu
`[IMAGE] UNKNOWN` olarak yazılır ve dağıtım sürer); namespace'i ve eksikse `ailab-tls`'i hazırlar;
`deploy-hooks.sh` ile runtime Secret'ı hazırlar; veritabanı Secret'larını hazırlar; `pending-*`
release'i çözer; `helm upgrade --install --atomic --wait --wait-for-jobs --timeout 30m` çalıştırır.
Ingress `nginx` sınıfıyla `dwhcodereview.ailab-test.kuveytturk.com.tr` adresini `ailab-tls` ile
sunar. `--render` kümeye erişmeden ve kancayı çalıştırmadan aynı değerlerle çıktı üretir.

Requirement 11: Yerel Compose iskeletin `scripts/stack.sh` akışıyla PostgreSQL 17, backend, frontend
ve nginx'i başlatır; göçler `scripts/db.sh apply` ile uygulanır; yerel sırlar Git dışında üretilir.
Varsayılan yerel ağ dışarı çıkmaz; SQL Server ve LLM'e yerel erişim yalnız açıkça seçilen ayrı bir
Compose profiliyle açılır (Decision 15).

Requirement 12: Kurallar PostgreSQL'e [kural yönetimi PRD'sinin](../../../sql-review/PRDs/001-rule-management/PRD.md)
Requirement 9'daki içe aktarım göçüyle, göç Job'u içinde girer; ayrı bir aktarım komutu ve
güncellemeden önce elle adım yoktur (Decision 12). Güncellemeden sonra kural sayısı ve kimlik+metin
içerik özeti depodaki `review_rules.json` kopyasıyla eşittir. Eski diskteki dosyalar aktarılmaz.

Requirement 13: Geri alma: başarısız güncelleme `--atomic` ile kendiliğinden önceki sürüme döner ve
şemayı geri indirmez. Elle geri alma için prova yapılmaz (Decision 18).

## API sözleşmesi

N/A — HTTP API yoktur. Dağıtım arayüzü: `helm/dwhcodereview/deploy.sh [--render|--apply]`;
argümansız çağrı `--apply`, kanonik `values.yaml` ve `values-project.yaml`, release ve namespace
`dwhcodereview` demektir. Girdiler ortam değişkenidir: `IMAGE_TAG`, `BUILD_SOURCEVERSION`, `TF_BUILD`,
Requirement 5'teki isteğe bağlı gizli değişkenler, `IMAGE_WAIT_SECONDS`, `PENDING_WAIT_SECONDS`,
`HELM_TIMEOUT`. Çıkış kodu 0 başarı, 1 dağıtım hatası, 2 geçersiz girdidir; log işaretleri
`[IMAGE]`, `[HOOK]`, `[RUNTIME]`, `[DATABASE]` ve `[RELEASE]` önekini taşır.

## Güvenlik ve yetkilendirme

- `deploy.sh` mevcut Azure `KUBECONFIG` bağlantısını kullanır; kubeconfig içeriği, Secret değeri ve
  registry belirteci loga yazılmaz; geçici dosyalar yalnız sahibine açıktır.
- Nonprod `admin` süper yöneticisini, sahibin rules/58 onayıyla ([directory-login](../001-directory-login/PRD.md)
  Decision 13), backend ilk açılışında runtime Secret'taki başlangıç parolasıyla bir kez açar;
  kanca ve `deploy.sh` hesap açmaz, parolayı yalnız Secret'a taşır.
- Eski geniş çıkış kuralı taşınmaz; SQL Server çıkışı yalnız TCP 1433'e açıktır ve adres gelince tek
  sunucuya daralır (Decision 11).

## Veri ve geçiş

- Kalıcı veri yalnız PostgreSQL PVC'sindedir. StatefulSet disk talebi release kaldırılsa da silinmez.
- Geçiş sırası: (1) Azure işi yeni chart'ı çalışan eski release'in yerine aynı release ve
  namespace'e `helm upgrade` ile kurar; aynı adlı Deployment, Service, NetworkPolicy ve Ingress
  yerinde güncellenir, eski ConfigMap kalkar; (2) göç Job'u (Requirement 4) uygulama rolünü
  hazırlar, şemayı kurar ve kuralları içe aktarır; (3) kural sayısı ve içerik özeti depodaki kopyayla
  karşılaştırılır.
- Eski PVC `dwhcodereview-backend-data` yeni sürüm sağlıklı açıldıktan sonra silindi; eski Secret
  anahtarları (`MSSQL_CONNECTION_STRING`, `API_ACCESS_TOKEN`,
  `API_ADMIN_TOKEN` ve öneksiz diğerleri) ve eski Azure değişkenleri elle silinir (Decision 13).
- Veritabanı yedeği ve yedekten geri dönüş bu teslimin kapsamında değildir (Decision 10).

## Gözlemlenebilirlik

`deploy.sh` ve kanca her adımı sabit işaretle yazar (imaj yayımı, kanca, Secret anahtar adları,
veritabanı Secret'ları, release durumu); hata iletisi girilen değeri yankılamaz. PostgreSQL ve
backend logları stdout'a gider; chart gözlemlenebilirlik iş yükü içermez (rules/25 ayrı PRD ister).
Yeni ölçüm tanımlanmaz.

## Dağıtım etkisi

Mevcut Azure işi aynı komutla çalışmaya devam eder ve yeni ayar veya gizli değişken istemez.
`MSSQL_USER` ve `MSSQL_PASSWORD` verilirse SQL Server hesabı olarak kullanılır; `JWT_PRIVATE_KEY` ve
`LLM_API_KEY` isteğe bağlıdır (Decision 14, 17). `DWHCODEREVIEW_ADMIN_PASSWORD` verilirse nonprod
`admin` süper yöneticisinin ilk parolası olur. Azure gizli değişkenleri betiğe kendiliğinden
geçmediği için her gizli değişken dağıtım adımının ortamına (`env:`) aynı adla açıkça eşlenir. `API_ACCESS_TOKEN` ve `API_ADMIN_TOKEN` artık
okunmaz. Namespace'te 10Gi `nfs-sc` PostgreSQL diski ve üç veritabanı Secret'ı oluşur. Azure işinin
kimliği namespace'te Secret okuyup yazabilmeli ve Deployment'ı yeniden başlatabilmelidir.

## Test stratejisi

- Chart: `scripts/render-charts.sh` proje katmanını `deploy.sh`'ın release ve namespace adıyla
  fabrikanın yapı denetimlerinden geçirir: her iş yükünde sıkılaştırma, yoklama ve kaynak denetimi;
  Secret üretilmemesi; kural diskinin olmaması; sır görünümlü anahtarın, boş eşin ve `/8`'den geniş
  bloğun reddi. `deploy.sh --render` aynı katmanla render eder.
- `deploy-hooks.sh`: `tests/helm/deploy-hooks.test.sh` sahte `kubectl` ile imza anahtarının ilk
  kurulumda bir kez üretilip sonraki çalıştırmalarda korunmasını, isteğe bağlı değişkenlerin varken
  yazılıp yokken kümedeki değerin korunmasını, çözülmemiş `$(...)` metninin verilmemiş sayılmasını,
  okunamayan Secret'ta ve geçersiz anahtarda durmayı, değerin argümana ve loga düşmemesini ve
  gereksiz yeniden başlatma olmamasını sınar; süper yönetici başlangıç parolası da aynı kurallarla
  sınanır. `deploy.sh`'ın kendi davranışının testleri fabrikadadır.
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

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: chart denetimi (proje katmanıyla), kanca testi,
  göç ve aktarım testleri Requirement 1–10, 12 ve 13 için geçer.
- [ ] Acceptance 2: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da PostgreSQL 17 çalışır,
  göç uygulanır, hazır olma yoklaması 200 döner, tarayıcıda giriş ve kural ekranı açılır; içe
  aktarılan kural sayısı ve içerik özeti depodaki `review_rules.json` kopyasıyla eşleşir
  (Requirement 11, 12).
- [ ] Acceptance 3: L2 — Canlı nonprod küme koşumu (yerel kanıttan ayrı): argümansız Azure işi, ek
  ayar veya gizli değişken olmadan çalışan eski release'in yerine yeni sürümü kurar; podlar hazır,
  PostgreSQL diski 10Gi `nfs-sc` bağlı, göç Job'u başarılı; HTTPS adresi `ailab-tls` ile açılır;
  backend LDAPS ve LLM'e ulaşır, listede olmayan adrese ulaşamaz; SQL Server gizli değişkenleri ve
  adresi yokken SQL Server alanı "yapılandırılmamış" görünür; PostgreSQL'deki kurallar depodaki
  kopyayla eşleşir (Requirement 1–10, 12).

## Kararlar

- Decision 7: Proje değer katmanı (`values-project.yaml`), proje kancası (`deploy-hooks.sh`) ve
  veritabanı Secret'larının üretimi fabrikanın rules/45 sözleşmesidir; bu proje onları fabrikanın
  `ce34a65` sürümünden almıştır. İskelet bu iki proje dosyasını oluşturmaz, güncellemez ve silmez.
- Decision 8: PostgreSQL imajı yerel Compose'daki `postgres:17.10` ile aynı özettedir. KT Verim'in
  çalışan PostgreSQL podu `postgres:17-alpine` adıyla düğümün Docker Hub aynasından çekilir (imaj
  kimliği `docker.io/library/postgres@sha256:…`, 2026-09-27 salt okunur gözlem); chart aynı yolu,
  `postgres` deposunu sabit özetle kullanır.
- Decision 9: PostgreSQL diski 10Gi'dir; depolama sınıfı KT Verim PostgreSQL diskininki ve kümenin
  varsayılanı olan `nfs-sc`'dir ve açıkça yazılır; kaynak isteği 100m CPU/256Mi, sınırı 1 CPU/1Gi'dir
  (Requirement 2).
- Decision 10: Proje sahibi veritabanı yedeğini (`pg_dump`) ve yedekten geri dönüşü gereksiz buldu;
  chart'ta yedek işi yoktur.
- Decision 11: SQL Server çıkışı yalnız TCP 1433'e açıktır. Nonprod SQL Server adresi henüz
  bilinmediği için kural fabrikanın izin verdiği en geniş blok olan `10.0.0.0/8`'dir; işletim ekibi
  adresi verince tek sunucuya (`/32`) daraltılır
  ([SQL Server bağlantısı PRD'si](../../../sql-review/PRDs/002-sql-server-connection/PRD.md)
  Decision 9); eski geniş kural ve 80 portu kaldırılır.
- Decision 12: Kural dosyası kümeye taşınmaz; kurallar kural yönetimi PRD'sinin içe aktarım göçüyle
  girer (Requirement 12). Nonprod'daki eski uygulama koddaki 25 varsayılan kuralla çalıştığı için
  eski diskte taşınacak kural verisi yoktur; güncelleme eski dosyanın parmak izini beklemez. Böylece
  elle dosya taşıma, `kubectl exec` ile veri verme ve geçici pod gerekmez.
- Decision 13: Eski disk `dwhcodereview-backend-data`, yeni sürüm nonprod'da sağlıklı açıldıktan
  sonra silinir. Sahibin küme hesabında silme yetkisi olmadığından disk 2026-09-27'de Azure
  koşumunun yetkisiyle, tek seferlik bir kanca adımıyla silindi; adım işini bitirince kancadan
  kaldırıldı. Eski Secret anahtarları ve eski Azure değişkenleri elle silinir; kanca hiçbir anahtar
  veya disk silmez.
- Decision 14: JWT imza anahtarı Azure değişkeninde taşınmaz; `deploy-hooks.sh` ilk kurulumda P-256
  anahtarını bir kez üretir ve sonraki çalıştırmalarda kümedekini kullanır; pipeline değişkeni
  verilirse o geçerlidir (Requirement 5).
- Decision 15: Yerel Compose varsayılan olarak SQL Server ve LLM'e çıkmaz; isteyen geliştirici için
  açıkça seçilen ayrı bir Compose profili vardır (Requirement 11).
- Decision 16: Yeni kod mevcut `kt-vibecoding/DWHCodeReview` deposunun `main` dalından yayımlanır; GHCR
  paket adları ve Azure işi bu depoya bağlıdır (Requirement 9).
- Decision 17: Proje sahibinin 2026-09-27 kararı: nonprod bir test ortamıdır ve dağıtımı işletim
  ekibinin ayar veya gizli değişken vermesini beklemez; bugün çalışan eski uygulama da özel ayarsız
  çalışır. PR #14 birleştikten sonra Azure'daki `deploy.sh` çalışması aynı release ve namespace'teki
  (`dwhcodereview`) eski release'in yerine `helm upgrade` ile yeni sürümü kurar ve sağlıklı açar.
  Azure `MSSQL_USER`/`MSSQL_PASSWORD` gizli değişkenlerini verirse SQL Server hesabı olarak kullanılır;
  vermezse uygulama yine açılır ve SQL Server alanı "yapılandırılmamış" görünür; değerler hiçbir
  zaman yazdırılmaz, loglanmaz veya Git'e girmez. PostgreSQL 10Gi `nfs-sc` diskle çalışır; eski 5Gi
  disk yeniden kullanılmaz (Decision 13).
- Decision 18: Proje sahibinin 2026-09-27 kararı: nonprod'da elle geri alma (`helm rollback`) provası
  gereksizdir ve yapılmaz. Başarısız güncellemede `--atomic` ile kendiliğinden geri dönüş geçerlidir.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- Tek kopya PostgreSQL'de disk arızası kuralları ve geçmişi kaybettirir; yedek olmadığı için (Decision
  10) bu risk sahip tarafından kabul edilmiştir.
- İlk güncelleme eski chart'tan yeni chart'a aynı release'te yapılır; beklenmeyen nesne çakışması
  `--atomic` ile eski sürüme döner ve geçiş ertelenir.
- Geri almada şema geri inmez; genişletici olmayan göç eski sürümü bozar.
- SQL Server çıkışı adres gelene kadar kurum ağının tamamında TCP 1433'e açıktır (Decision 11).
- Azure'da `MSSQL_USER` tanımlanmadan eski `MSSQL_PASSWORD` kalırsa yalnız parola yazılır; bağlantı
  sunucu, kullanıcı ve parola tamamlanana kadar "yapılandırılmamış" kalır.
- `DWHCODEREVIEW_ADMIN_PASSWORD` tanımlanıp dağıtım adımının ortamına eşlenmezse kanca onu görmez ve
  `admin` açılmaz; kanca logu `DWHCODEREVIEW_BOOTSTRAP_SUPER_ADMIN_PASSWORD not provided` der.
