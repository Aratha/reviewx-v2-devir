# DWH Code Review — 2. sürüm yetenekleri: kod devir notu

Hazırlanma: 2026-10-07. Bu not ve yama, kodu **kurumsal ortama** alacak kişi ve onun yapay zekâ oturumu
içindir. Not deponun içinde değildir; depoya eklenmemelidir.

Bu klasör, `../DEVIR-NOTU.md` ve `../specs-degisiklikleri.patch` dosyalarının **yerini alır**: yeni yama
aynı belge değişikliklerini (sonradan kabul edilen revizyonlarla birlikte) ve bütün kodu içerir.

## 1. Pakette ne var

| Dosya | İçerik |
|---|---|
| `reviewx-v2.patch` | Deponun `main` dalındaki `5f51a70` kaydına göre bütün değişiklik: 141 dosya (81 değişen, 60 yeni) |
| `DOSYALAR.txt` | Yamadaki dosyaların listesi ve durumu (M = değişen, A = yeni) |
| `SHA256SUMS.txt` | Dosyaların SHA-256 özetleri |
| `DEVIR-NOTU.md` | Bu not |

Yamanın kapsadığı yetenekler (hepsi kabul edilmiş PRD'lere göre, plan ve görev listeleriyle):

| Yetenek | PRD | Göç |
|---|---|---|
| Kural grubu seçimi: grupları tanımla, incelemeyi bir veya birkaç grupla başlat, rapor ve dışa aktarımda grup | `specs/sql-review/PRDs/007-rule-group-selection` | `202610050001_rule_groups.py` |
| Zamanlanmış inceleme: periyotta arka planda çalış, özet e-postası gönder, alıcı raporu salt okunur açsın | `specs/sql-review/PRDs/008-scheduled-review-email` (+ 005 Decision 8–9) | `202610050002_scheduled_reviews.py` |
| Girişte AD grup üyeliğinin okunması | `specs/application-foundation/PRDs/001-directory-login` Task 17 | — |
| Ekipler: AD grubuna eşlenen ekipler, ekibe ait kural grubu ve zamanlanmış inceleme | `specs/application-foundation/PRDs/003-team-scoping` | `202610050003_teams.py` |

Göçler genişleticidir (mevcut veriyi değiştirmez) ve sırayla uygulanır; geri alma, ilgili veri varken
durur. Yeni bağımlılık **yoktur** (`smtplib`, `ssl`, `zoneinfo`, `asyncio` standart kütüphanedir);
`requirements*.txt`, `package.json` ve `package-lock.json` değişmedi. Chart'a yeni iş yükü eklenmedi
(zamanlayıcı arka uç sürecinin içindedir, `rules/45`).

Ürün adının "ReviewX" yapılması bu pakette **yoktur**; ad, `env_prefix`, API yolu ve chart adı
yönetişim yüzeyindedir (`.kt-scaffold/answers.yml`) ve yalnız kanonik iskelet güncellemesiyle değişir.

## 2. Nasıl üretildi — önce bunu okuyun

Kod, deponun kişisel bilgisayardaki kopyasında, **proje kökünde başlatılmamış** bir yapay zekâ
oturumunda yazıldı. Bu nedenle:

- Projenin kancaları (prompt veri güvenliği kapısı `rules/55`, yönetişim yüzeyi koruması, sapma
  denetimi) bu oturumda **çalışmadı**. AGENTS.md "Kanca etkinliği ve oturum kökü" bölümü böyle bir
  oturumda proje dosyası değiştirilmemesini ister; proje sahibi açık talimatıyla kodun burada
  yazılmasını istedi. Kurumsal oturumdaki denetimler bu açığı kapatmak içindir.
- `scripts/quality-gate.sh`, `governed-review`, `scripts/db.sh`, `scripts/export-openapi.sh`,
  `scripts/generate-types.sh`, `scripts/render-charts.sh` ve `scripts/e2e.sh` **çalıştırılmadı**
  (Docker ve Helm yoktu). Görev listelerindeki kanıt satırları yalnız yerelde gerçekten koşulanı yazar ve
  bu betikleri "kurumsal ortamda kalanlar" olarak bırakır.
- Yönetişim yüzeyine (rules/, AGENTS.md, CLAUDE.md, .kt-scaffold/, .claude/) yamada hiçbir değişiklik
  yoktur. (Oturum sırasında `.claude/` klasörü bir kez yanlışlıkla silinip `git checkout` ile birebir geri
  yüklendi; yamaya yansımaz.)

Yerelde (Windows, Python 3.14.8, PostgreSQL 17.10, Docker'sız) **yamanın uygulandığı temiz kopyada**
koşulan ve geçen denetimler:

- Arka uç `pytest -q`: 836 geçti, 1 kaldı. Kalan
  `test_config.py::test_otel_process_variables_stop_start_up[otel_sdk_disabled]` değişiklik öncesi tabanda
  da kalıyordu (Windows'a özgü). `test_llm_adapter.py` Windows'ta TLS vakalarında takıldığı için
  dışarıda bırakıldı; kurumda mutlaka koşulmalıdır.
- `ruff check app tests`, `black --check app tests`, `isort --check-only app tests`, `mypy app`: temiz.
- Göçler: `alembic upgrade head`, her yeni sürüm için geri alma ve yeniden uygulama, `alembic check`.
- OpenAPI: uygulamadan dışa aktarılan sözleşme `specs/openapi/dwhcodereview-api.yaml` ile, üretilen tipler
  `app/frontend/src/types/api.d.ts` ile birebir aynı.
- Ön yüz: `npm run typecheck`, `npm run lint`, `npm run build` temiz; `vitest` 177/177.
- Yeni tarayıcı senaryoları (`e2e/sql-review/04-rule-groups.mjs`, `05-scheduled-review.mjs`,
  `e2e/auth/02-teams.mjs`) yazıldı ve `QUALITY_MANIFEST.md`'ye işlendi; yalnız sözdizimi denetlendi,
  **koşulmadı**.
- Eklenen satırlarda sır, özel anahtar, CRLF ve iç IP taraması temiz.

Not: Bu Windows makinesinde sistem saat dilimi verisi olmadığı için `tzdata` yalnız depo dışındaki test
ortamına kuruldu. Kurumun Alpine tabanlı arka uç imajında `zoneinfo`'nun çalıştığı doğrulanmalıdır
(4. bölüm, 6. adım).

## 3. Yamayı kurumsal kopyaya almak

Kişisel bilgisayardaki çalışma kopyasından **commit veya push yapılmadı** ve yapılmamalıdır (commit
kancası orada kurulu değil). GitHub taşıma için kullanılacaksa yama **commit olarak değil dosya olarak**
taşınmalıdır; dosyanın kurumsal cihaza nasıl ulaşacağı proje sahibinin kararıdır ve kurum politikasına
uygun yolla yapılmalıdır. Önce özetleri karşılaştırın:

```sh
sha256sum -c SHA256SUMS.txt
```

Kurumsal ortamda, proje kökünde:

```sh
git checkout main && git pull
git switch -c feat/reviewx-v2
git apply --check /yol/reviewx-v2.patch
git apply /yol/reviewx-v2.patch
git status
```

`main` bu arada ilerlediyse ve `--check` çakışma gösterirse zorla uygulamayın:
`git apply --3way /yol/reviewx-v2.patch` ile deneyin; kalan çakışmaları güncel hâlle karşılaştırıp elle
uzlaştırın. Göç sürüm numaraları (`202610050001–3`) `main`'e başka göç eklendiyse zinciri bozmayacak
şekilde güncellenmelidir. Dal, commit ve PR proje sahibinindir.

## 4. Kurumsal oturumda yapılacaklar (sırayla)

1. **Ortam:** Oturumu proje kökünde açın; kök `.venv` hazır, kancalar etkin; Docker çalışıyor; Python 3.14
   (en az 3.14.7) ve Node 22 kurumsal katalogdan (`rules/05`).
2. **Yamayı uygulayın** (3. bölüm) ve `python3 scripts/check-governance-drift.py` çalıştırın.
3. **Veritabanı:** `scripts/db.sh apply`, `scripts/db.sh validate`, `scripts/db.sh status`.
4. **Sözleşme:** `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
5. **Kalite kapısı:** `scripts/quality-gate.sh all` (arka uç testleri `test_llm_adapter.py` dahil koşar).
6. **Saat dilimi:** arka uç imajında
   `python -c "import zoneinfo; zoneinfo.ZoneInfo('Europe/Istanbul'); zoneinfo.ZoneInfo('Europe/Berlin')"`
   hatasız çalışmalı. Çalışmazsa `tzdata` eklemek bağımlılık kabul sürecine girer; sahibe sorun.
7. **Chart:** `scripts/render-charts.sh` geçmeli (chart'a iş yükü eklenmedi; yalnız
   `values-project.yaml` ve `deploy-hooks.sh` değişti).
8. **Tarayıcı senaryoları:** `scripts/e2e.sh`. Tam kapsam için ortam değişkenleri:
   `APP_E2E_LLM_BASE_URL`, `APP_E2E_SQL_OBJECT` (ör. `DWH.dbo.usp_X:P`), backend'de
   `DWHCODEREVIEW_SCHEDULER_ENABLED=true` ve yerel hesapların e-posta alan adını içeren
   `DWHCODEREVIEW_MAIL_ALLOWED_DOMAINS`; nonprod AD için `APP_E2E_TEAM_GROUP_DN`,
   `APP_E2E_TEAM_MEMBER_USER`, `APP_E2E_TEAM_MEMBER_PASS`. Değişkenler yoksa senaryolar daraltılmış yolu
   doğrular ve bunu `NOTE` satırıyla yazar.
9. **Sonuçları anlatın:** `/kt-test-kosumu-raporu`, ardından `/kt-tamamla` ile iddia edilen kanıt seviyesini
   kontrol edin; görev listelerindeki "kurumsal ortamda kalanlar" maddelerini kanıtla kapatın.
10. **Commit öncesi** `governed-review`; `PASS` gelirse commit ve PR (sahip açar). İsterseniz commit'ler
    PRD sırasıyla bölünebilir: 007 → 008 (+005) → 001 Task 17 → 003.

## 5. Proje sahibinin onayını bekleyen uygulama seçimleri

PRD'lerin açık bıraktığı yerlerde verilen kararlar; onaylanmazsa küçük değişikliklerle döndürülebilir:

1. **Ekip seçenekleri:** `GET /teams` PRD gereği yalnız süper yöneticiye açık. Bu yüzden kural grubu ve
   zamanlanmış inceleme formlarında süper yönetici bütün ekipleri, diğer kullanıcılar yalnız üyesi olduğu
   ekipleri (`/me` → `teams`) seçebilir; mevcut atama listede olmasa da korunur. Kural yöneticisinin bütün
   ekipleri seçmesi istenirse sözleşmeye salt okunur bir ek gerekir (PRD revizyonu).
2. **AD grubu değişen ekip:** ekibin eski üyelikleri silinir; üyeler bir sonraki girişte yeniden eşleşir.
3. **Koşum türü:** zamanlanmış koşum `kind = "scheduled"` ile saklanır ve geçmişte "Zamanlanmış" rozetiyle
   görünür; mevcut ölçümler değişmesin diye ölçümlerde nesne koşumu sayılır (008 Decision 10).
4. **Serbest cron:** kapalı değer listesi dışındaki periyot sözleşme düzeyinde `422 invalid_request` alır;
   diğer periyot hataları `422 schedule_invalid`.
5. **İzinli alıcı alan adı:** `values-project.yaml` içinde `kuveytturk.com.tr` yazıldı; doğrulanmalıdır.
6. **Ekip üyesinin raporu:** PRD gereği ekip üyesi zamanlanmış tanımı ve çalışma geçmişini görür; raporun
   kendisini yalnız sahibi, kural yöneticisi ve e-posta alıcıları açar (005 Decision 8).
7. **Yerel sahte SMTP:** 008 Task 10'daki Compose sahte SMTP'si yeni bir konteyner imajı gerektirdiği için
   eklenmedi (imaj kabulü kurum sürecidir); yerelde e-posta "yapılandırılmadı" olarak işaretlenir. SMTP
   istemcisinin kendisi gerçek TCP üzerinde test SMTP sunucusuyla sınandı.
8. **Ekip senaryosu yeri:** plan `e2e/application-foundation/` diyor; mevcut `e2e/auth/` klasörü bu alanın
   senaryolarını taşıdığı için `e2e/auth/02-teams.mjs` olarak eklendi.

## 6. Nonprod hazırlığı (işletim ekibi)

- `values-project.yaml`: `DWHCODEREVIEW_SCHEDULER_ENABLED: true` ve izinli alan adı hazır.
  `DWHCODEREVIEW_SMTP_HOST`, `DWHCODEREVIEW_SMTP_PORT`, `DWHCODEREVIEW_SMTP_SENDER` doldurulmalı ve
  dosyadaki yorumlu çıkış eşi, SMTP sunucusunun tek adresiyle açılmalıdır. SMTP doldurulana kadar raporlar
  saklanır, e-posta "yapılandırılmadı" görünür.
- Röle oturum açma istiyorsa Azure gizli değişkenleri `SMTP_USER` ve `SMTP_PASSWORD` verilir;
  `deploy-hooks.sh` bunları runtime `Secret`'ına eşler. Bağlantı yalnız doğrulanmış TLS ile kurulur
  (STARTTLS veya örtük TLS); kurum CA'sı imajın güven deposundadır.
- Ekip AD grupları **doğrudan üyeli** olmalıdır (iç içe gruplar çözülmez).

## 7. Kurumda elle deneme (kısa)

1. **DWH: Uygulamayı başlat**; inceleyici, kural yöneticisi ve süper yönetici hesapları açın.
2. **Kural grupları:** Kurallar sayfasında iki grup açın, kurallara atayın, yayımlayın. Nesne/SQL
   incelemesinde bir grup seçin: sonuçlar grup başlıklarıyla bölünür, yalnız o grubun kuralları çalışır;
   geçmişte "Kural grupları: …" ve CSV'nin son `rule_group` sütunu görünür.
3. **Zamanlanmış inceleme:** menüde "Zamanlanmış incelemeler"; tanım oluşturun, süper yönetici "Şimdi
   çalıştır" desin. Zamanlayıcı en geç bir dakikada koşumu başlatır; sonuç geçmişte "Zamanlanmış" olarak
   görünür. Süper yönetici "Zamanlama ayarı"ndan eşzamanlı sınırı (1–10) değiştirebilir.
4. **Ekipler:** süper yönetici "Ekipler"de ekip açıp bir AD grubu DN'si girer; o gruptaki kullanıcı giriş
   yapınca ekibe düşer. Kural grubuna ekip atayın: üye olmayan inceleyici o grubu inceleme ekranında
   görmez, API'den denerse `403 rule_group_forbidden` alır.

## 8. Bilinen sınırlar

- Her dağıtım süren zamanlanmış koşumu "yarıda kesildi" yapar; süper yönetici "Şimdi çalıştır" ile yeniden
  başlatır. Uygulama kapalıyken kaçırılan çalışmalar telafi edilmez, "kaçırıldı" görünür.
- AD'den çıkarılan kullanıcı bir sonraki girişine kadar eski ekibinde kalır.
- Çok sayıda gruba üye kullanıcıda AD `memberOf` değerini aralıklı döndürürse üyelik değiştirilmez ve
  `team_membership_sync_failed` logu yazılır.
- Ekip silme reddi (`409 team_in_use`) bağlı varlık sayılarını iletide taşır; arayüz kurala uygun olarak
  sunucu metnini değil sabit Türkçe iletiyi gösterir.

## 9. Geri dönüş noktası

Değişiklik öncesi depo durumu `../geri-donus-2026-10-06/DWHCodeReview-5f51a70.bundle` dosyasındadır
(bkz. oradaki `BENIOKU.md`). Yama yalnız `5f51a70`'a göre uygulanır; geri dönmek için dalı silmek
yeterlidir.
