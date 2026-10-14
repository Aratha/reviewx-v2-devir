# DWH Code Review — 2. sürüm yetenekleri: kod devir notu (v4)

Hazırlanma: 2026-10-14. Bu not ve yama, kodu **kurumsal ortama** alacak kişi ve onun yapay zekâ oturumu
içindir. Not deponun içinde değildir; depoya eklenmemelidir.

Bu klasör v2 ve v3 paketlerinin **yerini alır**. v4, kurumun güncel `main`'i olan **`fe83459`**
("generation 51": Python alt sınırı 3.12, yeni bağımlılık seti) üzerine kuruldu; v3 ise eski `5f51a70`
tabanındaydı. İçerik v3 ile aynıdır, ek olarak kod yeni `rules/20` şartına (Python 3.12'de olmayan dil
özelliği kullanılmaz) uyarlandı: parantezsiz `except A, B:` yerine `except (A, B):` ve sınıfın kendisine
tırnaksız ileri referans yerine tırnaklı referans (kurumun `fe83459`'da kendi kodunda yaptığı düzeltmenin
aynısı). Ekip özelliği (003) ve AD grup üyeliği okuma (001 Task 17) yoktur.

## 1. Pakette ne var

| Dosya | İçerik |
|---|---|
| `reviewx-v4.patch` | Deponun `main` dalındaki `fe83459` kaydına göre bütün değişiklik: 145 dosya (76 değişen, 69 yeni) |
| `DOSYALAR.txt` | Yamadaki dosyaların listesi ve durumu (M = değişen, A = yeni) |
| `SHA256SUMS.txt` | Dosyaların SHA-256 özetleri |
| `DEVIR-NOTU.md` | Bu not |

Yamanın kapsadığı yetenekler (hepsi kabul edilmiş PRD'lere göre, plan ve görev listeleriyle):

| Yetenek | PRD | Göç |
|---|---|---|
| Kural grupları: bir kural birden çok grupta; incelemede grupla hızlı seçim ve tek tek kural seçimi; raporda kuralın bütün grupları, grup süzgeci; CSV'de `; `, SQL yorumunda virgülle gruplar | `specs/sql-review/PRDs/007-rule-group-selection` (2.0.0) + 005 (1.5.0) | `202610050001_rule_groups.py` |
| Zamanlanmış inceleme: periyotta arka planda çalış, özet e-postası, alıcı raporu salt okunur açar; tanımı yalnız sahibi ve süper yönetici görür | `specs/sql-review/PRDs/008-scheduled-review-email` (1.1.0) + 005 Decision 8–9 | `202610050002_scheduled_reviews.py` |
| Kural özeti: her kurala tek cümlelik özet; süper yönetici dışındakiler kuralları özetle görür | `specs/sql-review/PRDs/001-rule-management` (1.1.0) | `202610140001_rule_proposals.py` |
| Kural önerileri ve onay: yetki verilen kullanıcı kural/grup önerir; kural yöneticisi taslağı onaya gönderir; yayını yalnız süper yönetici yapar ("Kural onayları" sayfası, fark görünümü, gerekçeli ret) | `specs/sql-review/PRDs/009-rule-proposals` (1.0.0, yeni) | `202610140001_rule_proposals.py` |

Göçler genişleticidir ve sırayla uygulanır; geri alma, ilgili veri varken durur. `202610050001` v2'dekinden
farklıdır (tekli grup sütunları yerine üyelik tabloları); hiçbir ortama dağıtılmadığı için yerinde yeniden
yazıldı. Yeni bağımlılık **yoktur**; `requirements*.txt`, `package.json` ve `package-lock.json` değişmedi.
Chart'a yeni iş yükü eklenmedi (zamanlayıcı arka uç sürecinin içindedir, `rules/45`).

Ürün adının "ReviewX" yapılması bu pakette **yoktur**; ad yönetişim yüzeyindedir (`.kt-scaffold/answers.yml`)
ve yalnız kanonik iskelet güncellemesiyle değişir.

**Davranış değişikliği:** Dağıtımdan sonra kural yöneticileri doğrudan yayımlayamaz ("Yayınla" yerine
"Onaya gönder"); `POST /rule-set/versions` süper yönetici dışındakilere `403 publish_requires_approval` döner.
Süper yöneticinin dağıtımdan sonra "Kural onayları → Öneri yetkisi" sekmesinden öneri yetkisi vermesi
gerekir.

## 2. Nasıl üretildi — önce bunu okuyun

Kod, deponun kişisel bilgisayardaki kopyasında, **proje kökünde başlatılmamış** bir yapay zekâ
oturumunda yazıldı. Bu nedenle:

- Projenin kancaları (prompt veri güvenliği kapısı `rules/55`, yönetişim yüzeyi koruması, sapma
  denetimi) bu oturumda **çalışmadı**; proje sahibi açık talimatıyla kodun burada yazılmasını istedi.
- `scripts/quality-gate.sh`, `governed-review`, `scripts/db.sh`, `scripts/render-charts.sh` ve
  `scripts/e2e.sh` **çalıştırılmadı** (Docker ve Helm yoktu). Eşdeğer adımlar aşağıdaki gibi doğrudan
  araçlarla koşuldu.
- Yönetişim yüzeyine (rules/, AGENTS.md, CLAUDE.md, .kt-scaffold/, .claude/, agent-platform) yamada
  hiçbir değişiklik yoktur.

**Kurumun `fe83459` kopyasında, yama uygulanmış hâlde** (Windows, **Python 3.12.10**, kurumun gen51
`requirements-dev.txt`'i hash'leriyle — Windows'ta tekerleği olmayan `uvloop` hariç —, PostgreSQL 17.10,
Docker'sız) koşulan ve geçen denetimler:

- Yama `fe83459`'un temiz bir kopyasına `git apply --check` ile uygulanıyor; 145 dosya bayt bayt aynı.
  Tabandan beri değişen iki ortak dosya (`app/core/config.py`,
  `tests/integration/test_sql_connection_storage.py`) üç yollu birleşmeyle çakışmasız birleşti.
- Bütün `app.*` modülleri Python 3.12'de içe aktarılıyor.
- `scripts/check-governance-drift.py` ve `scripts/check-dependency-admission.py`: güncel.
- Arka uç `pytest -q` (gerçek PostgreSQL, boş veritabanından): 848 geçti, 1 kaldı. Kalan
  `test_config.py::test_otel_process_variables_stop_start_up[otel_sdk_disabled]` tabanda da kalıyordu
  (Windows'a özgü). `test_llm_adapter.py` Windows'ta TLS vakalarında takıldığı için dışarıda bırakıldı;
  kurumda mutlaka koşulmalıdır.
- `ruff check`, `black --check` (hedef `py312`), `isort --check-only` (app, tests), `mypy app`
  (`python_version = 3.12`): temiz.
- Göçler: `alembic upgrade head`, yeni sürümler için geri alma ve yeniden uygulama, `alembic check` temiz.
- OpenAPI: uygulamadan dışa aktarılan sözleşme `specs/openapi/dwhcodereview-api.yaml` ile birebir aynı;
  `app/frontend/src/types/api.d.ts` bundan üretildi.
- Ön yüz (gen51 kilit dosyasıyla `npm ci`): `npm run typecheck`, `eslint`, `vite build` temiz; Vitest
  201/201; üretilen tipler sözleşmeyle aynı.
- Yamada CRLF, sır/özel anahtar ve iç IP taraması temiz.

Aynı `fe83459` + yama ağacından, Python 3.12 ile çalışan yerel önizlemeye (Vite + uvicorn +
PostgreSQL, Chromium) karşı **tarayıcı senaryoları** da koşuldu: `e2e/sql-review/run-all.mjs` 6/6 ve `e2e/auth/run-all.mjs` 1/1 geçti. Sınırlar:
LLM adımlarında kurumun onaylı ucu yerine yerel, OpenAI uyumlu bir sahte uç kullanıldı (yavaş akış,
Kural01 için NOLOCK bulgusu); SQL Server yoktu, bu yüzden 05 senaryosu daraltılmış dalını koştu. Kurum
ortamında gerçek LLM ve test SQL Server ile yeniden koşulmalıdır.

Not: Windows'ta sistem saat dilimi verisi olmadığından `tzdata` yalnız depo dışındaki test ortamına kuruldu.
Kurumun arka uç imajında `zoneinfo`'nun çalıştığı doğrulanmalıdır (4. bölüm, 6. adım).

## 3. Yamayı kurumsal kopyaya almak

Kişisel bilgisayardaki çalışma kopyasından **commit veya push yapılmadı** ve yapılmamalıdır. Yama
**commit olarak değil dosya olarak** taşınmalıdır; dosyanın kurumsal cihaza nasıl ulaşacağı proje sahibinin
kararıdır ve kurum politikasına uygun yolla yapılmalıdır. Önce özetleri karşılaştırın:

```sh
sha256sum -c SHA256SUMS.txt
```

Kurumsal ortamda, proje kökünde:

```sh
git checkout main && git pull
git switch -c feat/reviewx-v2
git apply --check /yol/reviewx-v4.patch
git apply /yol/reviewx-v4.patch
git status
```

`main` bu arada ilerlediyse ve `--check` çakışma gösterirse zorla uygulamayın:
`git apply --3way /yol/reviewx-v4.patch` ile deneyin; kalanları güncel hâlle karşılaştırıp elle uzlaştırın.
Göç numaraları (`202610050001`, `202610050002`, `202610140001`) `main`'e başka göç eklendiyse zinciri
bozmayacak şekilde güncellenmelidir. Dal, commit ve PR proje sahibinindir.

## 4. Kurumsal oturumda yapılacaklar (sırayla)

1. **Ortam:** Oturumu proje kökünde açın; kök `.venv` hazır, kancalar etkin; Docker çalışıyor; Python 3.12
   veya daha yenisi (`technology-profile.yml`) ve Node 22 kurumsal katalogdan (`rules/05`).
2. **Yamayı uygulayın** (3. bölüm) ve `python3 scripts/check-governance-drift.py` çalıştırın.
3. **Veritabanı:** `scripts/db.sh apply`, `scripts/db.sh validate`, `scripts/db.sh status`.
4. **Sözleşme:** `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
5. **Kalite kapısı:** `scripts/quality-gate.sh all` (arka uç testleri `test_llm_adapter.py` dahil koşar).
6. **Saat dilimi:** arka uç imajında
   `python -c "import zoneinfo; zoneinfo.ZoneInfo('Europe/Istanbul'); zoneinfo.ZoneInfo('Europe/Berlin')"`
   hatasız çalışmalı. Çalışmazsa `tzdata` eklemek bağımlılık kabul sürecine girer; sahibe sorun.
7. **Chart:** `scripts/render-charts.sh` geçmeli (yalnız `values-project.yaml` ve `deploy-hooks.sh` değişti).
8. **Tarayıcı senaryoları:** `scripts/e2e.sh`. Tam kapsam için: `APP_E2E_LLM_BASE_URL`,
   `APP_E2E_SQL_OBJECT` (ör. `DWH.dbo.usp_X:P`), backend'de `DWHCODEREVIEW_SCHEDULER_ENABLED=true` ve yerel
   hesapların e-posta alan adını içeren `DWHCODEREVIEW_MAIL_ALLOWED_DOMAINS`. Yeni senaryo
   `e2e/sql-review/06-rule-proposals.mjs` süper yönetici hesabını (`APP_E2E_SUPER_ADMIN_*`) kullanır ve
   inceleyiciye yetkiyi kendisi verip geri alır. Değişkenler yoksa senaryolar daraltılmış yolu doğrular ve
   bunu `NOTE` satırıyla yazar.
9. **Sonuçları anlatın:** `/kt-test-kosumu-raporu`, ardından `/kt-tamamla`; görev listelerindeki "kurumsal
   ortamda" maddelerini (007 Task 10, 009 Task 9 ve önceki açıklar) kanıtla kapatın.
10. **Commit öncesi** `governed-review`; `PASS` gelirse commit ve PR (sahip açar). İsterseniz commit'ler
    PRD sırasıyla bölünebilir: 007 → 008 (+005) → 001 özet + 009.

## 5. Proje sahibinin onayını bekleyen uygulama seçimleri

1. **İnceleme ekranında grup seçimi:** grup kutusu o grubun kurallarını işaretler; istek tek tek kural
   kodlarıyla (`rule_codes`) gider, geçmişte "Seçilen kurallar: …" görünür. API grup kimliğini de kabul eder
   (zamanlanmış inceleme yalnız grup seçer — 008 PRD'si böyle).
2. **Özet yedeği:** özet girilmemiş kuralda metnin ilk cümlesi gösterilir; içe aktarılan kurallar
   "KURAL ADI: … AÇIKLAMA: …" biçiminde olduğundan ilk cümle "AÇIKLAMA:" bölümünden alınır.
3. **Sade görünüm bir görünüm kararıdır, yetki sınırı değildir:** sürüm uçları ayrıntılı metni tüm rollere
   döner (metin zaten LLM'e giden kural metnidir); yalnız arayüz özet gösterir.
4. **Menüdeki bekleyen sayı:** süper yöneticide bekleyen öneri + yayın isteği sayısı; gezinmede ve her
   kararda yenilenir.
5. **Onaylanan öneri bekleyen yayın isteğini bayatlatır:** onay taslağa da yazdığı için kural yöneticisinin
   bekleyen isteği onaylanamaz (`409 publish_request_stale`) ve yeniden gönderilmesi gerekir (PRD Riskler).
6. **İzinli alıcı alan adı:** `values-project.yaml` içinde `kuveytturk.com.tr`; doğrulanmalıdır.
7. **Zamanlanmış koşum türü** `kind = "scheduled"`; ölçümlerde nesne koşumu sayılır (008 Decision 10).
8. **Yerel sahte SMTP** eklenmedi (yeni imaj kabul süreci ister); yerelde e-posta "yapılandırılmadı".

## 6. Nonprod hazırlığı (işletim ekibi)

- `values-project.yaml`: `DWHCODEREVIEW_SCHEDULER_ENABLED: true` ve izinli alan adı hazır.
  `DWHCODEREVIEW_SMTP_HOST`, `DWHCODEREVIEW_SMTP_PORT`, `DWHCODEREVIEW_SMTP_SENDER` doldurulmalı ve
  dosyadaki yorumlu çıkış eşi SMTP sunucusunun tek adresiyle açılmalıdır.
- Röle oturum açma istiyorsa Azure gizli değişkenleri `SMTP_USER` ve `SMTP_PASSWORD` verilir;
  `deploy-hooks.sh` bunları runtime `Secret`'ına eşler. Bağlantı yalnız doğrulanmış TLS ile kurulur.

## 7. Kurumda elle deneme (kısa)

1. **DWH: Uygulamayı başlat**; inceleyici, kural yöneticisi ve süper yönetici hesapları açın.
2. **Onaylı yayın:** kural yöneticisi Kurallar sayfasında iki grup açar, bir kuralı iki gruba koyar, özet
   yazar, "Onaya gönder" der. Süper yönetici "Kural onayları → Yayın istekleri"nde farkı görüp onaylar.
3. **Sade görünüm ve seçim:** inceleyici "Yayımlanmış kurallar"da her kuralı tek cümleyle görür; SQL
   incelemesinde bir grubu işaretleyip ayrıca tek bir kural ekler; sonuçta kuralın bütün grupları etiket
   olarak görünür, grup süzgeci çalışır; CSV'de gruplar `; ` ile birleşir.
4. **Öneri:** süper yönetici "Öneri yetkisi"nden bir inceleyiciye yetki verir; inceleyici "Kural
   önerilerim"de özet ve ayrıntıyla kural önerir; süper yönetici onaylar → yeni sürüm. Reddedilen öneride
   gerekçe öneri sahibine görünür.
5. **Zamanlanmış inceleme:** "Zamanlanmış incelemeler"de tanım oluşturun, süper yönetici "Şimdi çalıştır"
   desin; sonuç geçmişte "Zamanlanmış" rozetiyle görünür.

## 8. Bilinen sınırlar

- Her dağıtım süren zamanlanmış koşumu "yarıda kesildi" yapar; kaçırılan çalışmalar telafi edilmez.
- Süper yönetici tek onay noktasıdır; yoğun dönemde yayın onay bekler (menüdeki sayı bunu gösterir).
- Öneri kayıtları silinmez; geçmiş olarak kalır (rules/41 yazılımsal silme).

## 9. Geri dönüş noktası

Yama kurumun `fe83459` kaydına göre üretildi ve yeni bir dala uygulanır; `main` değişmez. Geri dönmek
için dalı silmek yeterlidir.
