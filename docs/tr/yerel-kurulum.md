# Yerel kurulum

Bu kılavuz DWH Code Review'u kendi bilgisayarınızda çalıştırmayı anlatır. Uygulama bilgisayarınızda,
Docker Desktop'ın (uygulamaları birbirinden ayrı kutularda, yani kapsayıcılarda çalıştıran araç)
içinde çalışır ve tarayıcıda `http://localhost:8080` adresinden açılır. Verileriniz (hesaplar,
kurallar, geçmiş) yalnız bilgisayarınızda durur.

Bütün adımlar VS Code içinden, hazır görevlerle (tek tıkla çalışan komutlar) yapılır; komut yazmanız
gerekmez. Uygulamanın kullanımı [kullanım kılavuzunda](kullanim-kilavuzu.md), yetki ve ayarlar
[yönetici kılavuzunda](yonetici-kilavuzu.md) anlatılır.

## Hangi bilgisayarda çalışır

| İşletim sistemi | Durum |
|---|---|
| macOS | Desteklenir. Bu kılavuzdaki adımlar macOS içindir. |
| Windows | Bugün desteklenmez. Nedeni [Windows bölümündedir](#windows). |

## Gerekenler

Aşağıdaki araçları **kurumsal uygulama kataloğundan** (macOS'ta Self Service) kurun. Üreticinin
sitesinden, Homebrew'dan (macOS paket yöneticisi) veya başka bir yoldan kurmayın. Bir araç katalogda
yoksa kurumsal BT talep kanalına başvurun.

| Araç | Ne için |
|---|---|
| Docker Desktop | Uygulamayı çalıştırır. Uygulamayı kullanırken açık olmalıdır (menü çubuğunda balina simgesi). |
| Git | Projenin kodunu indirir ve güncel tutar. |
| Python 3.13 | İlk kurulumdaki denetimleri çalıştırır. |
| VS Code | Görevleri çalıştırdığınız ve kodlama asistanınızla çalıştığınız düzenleyici. |

İlk kurulum görevi eksik aracı iletisiyle söyler; neyin eksik olduğunu önceden bilmeniz gerekmez.

## İlk kurulum (bir kez)

1. **Projeyi indirin.** VS Code'da `Cmd+Shift+P` ile komut paletini açın, **Git: Clone** yazın ve
   GitHub'daki `kt-vibecoding/DWHCodeReview` deposunu seçin. VS Code GitHub hesabınızla oturum açmanızı
   isteyebilir. Ardından projenin indirileceği klasörü gösterin.
2. **Projeyi açın.** **File → Open Workspace from File…** ile proje klasöründeki
   `app.code-workspace` dosyasını açın. VS Code "Do you trust the authors of the files in this
   folder?" diye sorarsa **Yes, I trust the authors** seçin; aksi hâlde görevler çalışmaz.
3. **Docker Desktop'ı başlatın** ve açılmasını bekleyin.
4. **İlk kurulum görevini çalıştırın.** **Terminal → Run Task…** menüsünü açın (ya da `Cmd+Shift+P`
   ile komut paletini açıp **Tasks: Run Task** yazın) ve **DWH: İlk kurulum** görevini seçin. Görev
   araçları ve projenin kurallarını denetler, sonra yerel ayar dosyasını (`app/infra/.env`) hazırlar.
   Sonunda `bootstrap ok` ve `app/infra/.env oluşturuldu.` satırlarını görürsünüz.
5. **Uygulamayı başlatın.** Aynı yoldan **DWH: Uygulamayı başlat** görevini seçin. İlk seferde
   kapsayıcılar hazırlandığı için biraz sürer. Sonunda `Uygulama hazır: http://localhost:8080` yazar.
6. **Kendinize hesap açın** ([aşağıdaki bölüm](#hesap-açmak)).
7. Tarayıcıda `http://localhost:8080` adresini açıp açtığınız hesapla giriş yapın.

## VS Code görevleri

Görevler **Terminal → Run Task…** menüsündedir. Görevin çıktısı VS Code'un alt kısmındaki terminal
panelinde görünür.

| Görev | Ne yapar |
|---|---|
| DWH: İlk kurulum | Araçları denetler, yerel ayar dosyasını hazırlar. Bir kez çalıştırılır; tekrar çalıştırmak ayar dosyasına dokunmaz. |
| DWH: Uygulamayı başlat | Uygulamayı kurar veya günceller, veritabanını en son yapısına getirir. |
| DWH: Uygulamayı durdur | Uygulamayı durdurur. Hesaplar, kurallar ve geçmiş silinmez. |
| DWH: Uygulamanın durumunu göster | Uygulamanın hangi parçasının çalıştığını listeler. |
| DWH: Arka uç günlüğünü izle | Uygulamanın sunucu tarafının (arka uç) yaptığı işlerin kaydını (günlük) canlı gösterir. Kapatmak için terminal panelindeki çöp kutusu simgesine basın. |
| DWH: Yerel test hesabı aç (inceleyici) | İnceleyici rolünde hesap açar ya da parolasını sıfırlar. |
| DWH: Yerel test hesabı aç (kural yöneticisi) | Kural yöneticisi rolünde hesap açar ya da parolasını sıfırlar. |
| DWH: Yerel süper yönetici aç | Kullanıcıları yöneten süper yönetici hesabını açar ya da parolasını sıfırlar. |

Görevler projedeki `.vscode/tasks.json` dosyasında tanımlıdır ve `scripts/` klasöründeki hazır
betikleri (komut dosyalarını) çalıştırır.

## Hesap açmak

Yerelde kurum dizini kapalıdır; kurum hesabınızla giremezsiniz. Uygulamayı denemek için yerel test
hesapları açarsınız. Bu hesaplar yalnız sizin bilgisayarınızdaki uygulamada vardır.

1. Uygulama çalışırken **DWH: Yerel test hesabı aç (inceleyici)** ya da **DWH: Yerel test hesabı aç
   (kural yöneticisi)** görevini çalıştırın.
2. Terminal panelinde `Yerel test kullanıcı adı:` sorusuna bir ad yazıp Enter'a basın (örneğin
   `deneme.inceleyici`; boşluk içeremez).
3. `Parola (en az 15 karakter):` sorusuna parolayı yazıp Enter'a basın. Güvenlik için yazdığınız
   karakterler ekranda görünmez.
4. `yerel test hesabı oluşturuldu` satırını görünce hesap hazırdır.

Parola kuralı: en az 15 karakter; yaygın bir parola olamaz; kullanıcı adını içeremez. Aynı adla görevi
yeniden çalıştırmak parolayı ve rolü yeniler.

Kullanıcıları yönetmek isterseniz **DWH: Yerel süper yönetici aç** görevini çalıştırın. Bu görev
soruları İngilizce sorar: önce `Super-admin username:` (kullanıcı adı), sonra `Super-admin password:`
(parola). Parola kuralı aynıdır.

## Günlük kullanım

- Çalışmaya başlarken Docker Desktop'ı açın ve **DWH: Uygulamayı başlat** görevini çalıştırın.
- İşiniz bitince **DWH: Uygulamayı durdur** görevini çalıştırın.
- Projenin güncel kodunu aldıktan sonra (VS Code **Source Control** panelindeki **Pull** ya da **Sync
  Changes**) **DWH: Uygulamayı başlat** görevini yeniden çalıştırın. Görev değişen parçaları yeniden
  hazırlar ve veritabanını yeni yapıya getirir.
- Bir şey ters giderse önce **DWH: Uygulamanın durumunu göster**, sonra **DWH: Arka uç günlüğünü izle**
  görevine bakın.

## Yerel ayar dosyası

Yerel ayarlar `app/infra/.env` dosyasındadır. İlk kurulum görevi bu dosyayı yalnız sizin
okuyabileceğiniz biçimde oluşturur.

- Dosya Git'e girmez (projenin değişiklik geçmişine kaydedilmez). İçinde parola olduğu için kimseyle
  paylaşmayın.
- İlk hâlinde tek satır vardır: `GRAFANA_ADMIN_PASSWORD`. Bu, bilgisayarınızdaki izleme panosunun
  (Grafana) parolasıdır. Pano `http://localhost:3001` adresindedir, kullanıcı adı `admin`'dir.
- 8080 portunu (uygulamanın açıldığı kapı numarası) başka bir uygulama kullanıyorsa dosyaya
  `APP_HTTP_PORT=8081` satırını ekleyin; uygulama `http://localhost:8081` adresinden açılır. Pano için aynı iş `GRAFANA_PORT` ile yapılır.
- Dosyayı değiştirdikten sonra **DWH: Uygulamayı başlat** görevini yeniden çalıştırın.

## SQL Server ve yapay zekâ modeline bağlanmak

Nesne incelemesi için bir SQL Server'a, her iki inceleme türü için de bir yapay zekâ modeline (LLM)
bağlanmak gerekir. Ayarı iki yoldan verebilirsiniz:

- **Kalıcı:** `app/infra/.env` dosyasına aşağıdaki satırları ekleyip **DWH: Uygulamayı başlat**
  görevini çalıştırın.
- **Geçici:** Kural yöneticisi hesabıyla girip **Yönetim → SQL bağlantısı** ya da **Yönetim → LLM
  bağlantısı** sayfasından girin. Bu değerler uygulama yeniden başlayınca kaybolur.

SQL Server satırları:

```sh
DWHCODEREVIEW_MSSQL_SERVER=<sunucu adı>
DWHCODEREVIEW_MSSQL_PORT=1433
DWHCODEREVIEW_MSSQL_USER=<okuma hesabı>
DWHCODEREVIEW_MSSQL_PASSWORD=<parola>
DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES=<veritabanı1,veritabanı2>
```

- `DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES` incelemeye açılacak veritabanlarının virgülle ayrılmış
  listesidir; yerelde boş bırakılırsa bütün veritabanları listelenir.
- Kendi bilgisayarınızdaki, kendinden imzalı sertifikalı bir geliştirici SQL Server'ı için
  `DWHCODEREVIEW_MSSQL_TRUST_SERVER_CERTIFICATE=true` satırını da ekleyin. Bu ayar yalnız yerelde kabul
  edilir.
- Okuma hesabı yalnız okuma yetkili olmalıdır; uygulama SQL Server'da hiçbir şey yazmaz.

Yapay zekâ modeli satırları, bilgisayarınızda çalışan Ollama (katalogda varsa kurulan, modeli
bilgisayarda çalıştıran araç) örneğiyle:

```sh
DWHCODEREVIEW_LLM_CHAT_API=openai
DWHCODEREVIEW_LLM_BASE_URL=http://host.docker.internal:11434/v1
DWHCODEREVIEW_LLM_MODEL=<Ollama'da yüklü modelin adı>
```

- `host.docker.internal`, uygulamanın kendi kapsayıcısından sizin bilgisayarınıza ulaşmak için
  kullandığı addır.
- LM Studio gibi `/api/v1/chat` biçimini kullanan bir araçta `DWHCODEREVIEW_LLM_CHAT_API=api_v1_chat`
  yazın.
- Anahtar isteyen bir uç için `DWHCODEREVIEW_LLM_API_KEY` satırını ekleyin.
- Uygulama yalnız kurum içi (özel) ağdaki adreslere istek gönderir; internetteki bir adres kabul
  edilmez.

> **Bugünkü sınır:** Yerel uygulamanın iç ağı güvenlik gereği dışarıya kapalıdır. Bu yüzden uygulama
> bugün ne bilgisayarınızdaki modele ne de ağdaki bir SQL Server'a ulaşabilir. **SQL bağlantısı**
> sayfasındaki test "SQL Server'a ulaşılamadı." der; **LLM bağlantısı** sayfası
> `host.docker.internal` adresini kaydetmez; `app/infra/.env` ile verilen modelde kurallar
> "Değerlendirilemedi" olur. Kabul edilmiş
> [Kubernetes dağıtımı PRD'si](../../specs/application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
> (PRD: bir özelliğin ne yapacağını yazan belge; Decision 15) bu erişimin ayrıca seçilen bir yerel ayarla açılmasını istiyor; o ayar projeye henüz
> eklenmedi. Eklenene kadar yerelde giriş, kurallar, yayımlanmış kurallar, kullanıcılar ve geçmiş
> ekranları çalışır, gerçek inceleme yapılamaz.

## Windows

Bugün Windows bilgisayarda uygulamayı yerelde çalıştırmanın desteklenen bir yolu yoktur:

- Başlatma ve hesap açma adımları macOS ve Linux komut kabuğu için yazılmış betiklerdir
  (`scripts/*.sh`). Windows'un kendi komut ekranı (PowerShell) bunları çalıştıramaz. Linux alt sistemi
  (WSL) kurulu bilgisayarda `bash` komutu da Git'in kabuğunu değil WSL'i açar.
- Git ile gelen Git Bash kabuğu bu betiklerin bir kısmını çalıştırabilir, ama projeyi üreten fabrika
  (kt-scaffold) Windows'ta yalnız kodlama asistanının denetimleri için Git Bash kullanır; uygulamayı
  başlatma betikleri için bu yolu desteklemez. İlk kurulum denetimi (`scripts/bootstrap.sh`) de
  Windows'ta `python3` adıyla gerçek Python yerine Microsoft Store kısayoluna ulaştığı için durur.
- Bu yüzden VS Code görevleri Windows'ta yalnız bu bölüme yönlendiren bir ileti gösterir.

Windows'ta şimdilik test ortamını tarayıcıdan kullanın. Windows desteği fabrikada bir değişiklik
gerektirir; o gelene kadar bu bölüm geçerlidir.

## Sorun giderme

| Gördüğünüz | Ne yapmalı |
|---|---|
| `Cannot connect to the Docker daemon` ya da ilk kurulum Docker adımında duruyor | Docker Desktop'ı açın, açılmasını bekleyip görevi yeniden çalıştırın. |
| İlk kurulum `python3` adımında duruyor ya da geliştirici araçlarını kurmayı öneren bir pencere açılıyor | Python 3.13'ü kurumsal uygulama kataloğundan kurun. |
| `required variable GRAFANA_ADMIN_PASSWORD is missing a value` | **DWH: İlk kurulum** görevini çalıştırın. |
| `port is already allocated` | 8080 portu dolu. [Yerel ayar dosyasına](#yerel-ayar-dosyası) `APP_HTTP_PORT=8081` ekleyin. |
| `service "backend" is not running` | Önce **DWH: Uygulamayı başlat** görevini çalıştırın. |
| `yerel test hesabı oluşturulmadı: password must contain at least 15 characters` | Parola en az 15 karakter olmalı. |
| `yerel test hesabı oluşturulmadı: password is too common` | Daha az tahmin edilebilir bir parola seçin. |
| `yerel test hesabı oluşturulmadı: password must not contain the account name` | Parola kullanıcı adını içermemeli. |
| Girişte "Kullanıcı adı veya parola geçersiz." | Hesap açma görevini aynı adla yeniden çalıştırıp parolayı sıfırlayın. |
| Tarayıcıda sayfa açılmıyor | **DWH: Uygulamanın durumunu göster** ile bütün parçaların çalıştığına bakın; gerekirse uygulamayı yeniden başlatın. |

Kaynak: [Kubernetes dağıtımı PRD'si](../../specs/application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Requirement 11 (yerel çalışma), [dizin girişi PRD'si](../../specs/application-foundation/PRDs/001-directory-login/PRD.md)
Requirement 11 (yerel test hesapları).
