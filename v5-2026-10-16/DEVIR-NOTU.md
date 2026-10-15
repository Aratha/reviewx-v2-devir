# ReviewX — devir notu v5 (2026-10-16)

Kod artık özel depoda: `github.com/Aratha/reviewx-v2-devir`.

- `main` ve `feat/reviewx-v2` dalları aynı commit'te; tabanları kurumun `fe83459` commit'idir.
- `kurum-main` dalı kurumun tabanını, `devir-paketleri` dalı eski yama paketlerini tutar.
- Yama dosyası gerekmez: dal kurum tabanının üstüne commit'lerle oturur.

## Bu sürümde neler var

- **Arayüz**
  - Tek ekranlı arayüz: üst menü, sayfa kaydırması yok, paneller içte kayar.
  - Yönetim tek sayfa (`/yonetim/:bölüm`); eski adresler yönlenir.
  - Ctrl+K hızlı geçiş.
- **İnceleme**
  - Nesne ve SQL betiği incelemesinde kurallar sağ panelde, gruplar alt alta (akordeon).
  - "Analizi durdur" açık bir istekle çalışır (`POST /review-runs/{id}/cancel`).
  - Arka planda sürdür: sağ altta ilerleme kutusu.
  - Sonuçlarda ve geçmişte SQL kod görünümü (ihlal satırları vurgulu, satıra git).
- **Kural kitaplığı:** Gruplar solda, seçilen grubun kuralları sağda. Grup yoksa tek panel.
- **Zamanlanmış incelemeler**
  - Kart görünümü.
  - "Durdur" (`POST /scheduled-reviews/{id}/stop`).
  - Yönetim → Zamanlama ve e-posta: SMTP durumu ve deneme e-postası.
- **Roller:** Yalnız "Kullanıcı" (`inceleyici`) ve süper yönetici.
  - Kural yöneticisi rolü göçle emekliye ayrıldı.
  - Kural taslağı, bağlantılar, LLM çağrıları ve kullanıcılar süper yöneticide.
  - Herkes kural ve grup önerir; süper yönetici onaylar. Yayın isteği akışı kaldırıldı.
- **Ana sayfa:** "Kalite nabzı" ve son incelemeler.

## Kurum ortamında yapılacaklar (sırayla)

1. Depoyu kurum ortamına alın; oturumu proje kökünde açın ki kancalar ve kapılar çalışsın.
2. Göçleri uygulayın: yeni göç `202610150001_single_application_role`.
   - Göç, `kural-yoneticisi` atamalarını `inceleyici` yapar ve rolü yumuşak siler.
   - Geri alındığında rol tanımı döner ama kişilerin eski rolleri dönmez.
3. Kalite kapısını ve governed-review'u çalıştırın; commit ve PR kurumsal akışla.
4. **E-posta ("mail atmıyor"):** Kod sağlam. `helm/dwhcodereview/values-project.yaml` içinde şunlar boş:
   - `DWHCODEREVIEW_SMTP_HOST`
   - `DWHCODEREVIEW_SMTP_SENDER`
   - SMTP çıkış (egress) satırı yorumda.

   İşletim ekibinden alınacaklar:
   - Relay adresi, portu ve gönderen adresi.
   - Gerekiyorsa `SMTP_USER` / `SMTP_PASSWORD` (deploy-hooks).
   - Relay STARTTLS (veya doğrudan TLS) sunmalı ve sertifikası kurum CA'sıyla doğrulanmalı.

   Kurulumdan sonra **Yönetim → Zamanlama ve e-posta → Deneme gönder** sonucu ve hata kodunu gösterir.
5. Önceden kural yöneticisi olan kişiler artık normal kullanıcıdır; kural işleri süper yöneticidedir.

## Onay bekleyen belge revizyonları

- `sql-review/PRDs/005-review-history-export` 1.6.0 — Requirement 13, Decision 10 (geçmişte kod görünümü).

Diğer revizyonlar sahibin açık onayıyla işlendi:
- directory-login 1.3.0 Decision 14 (tek rol)
- 003 1.3.0 (durdurma)
- 008 1.3.0 (e-posta durumu, zamanlanmış durdurma)
- 009 1.2.0 (herkes önerir, yayın isteği kalkar)

## Yerel kanıt (Windows, Python 3.12, PostgreSQL 17)

- **pytest:** 850 geçti, 1 kaldı.
  - Kalan `test_otel_process_variables_stop_start_up[otel_sdk_disabled]` yalnız Windows'ta kalır.
  - Sebep: Windows ortam değişkeni adlarını büyük harfe çevirir. Linux'ta beklenen geçer.
- **Ön yüz:** Vitest 210/210; typecheck ve eslint temiz.
- **e2e:** sql-review 01–06 ve auth/01, yerel önizlemede sahte LLM ile geçti.
  - Kural yöneticisi hesabı (`APP_E2E_RULE_MANAGER_*`) artık kullanılmaz; senaryolar süper yönetici hesabını kullanır.
- **Diğer denetimler:** OpenAPI yapıtı ve ön yüz tipleri senkron; yönetişim izdüşümleri ve bağımlılık kabulü güncel.

## Gerçek ortamda doğrulanamayanlar (L2)

- Gerçek SQL Server ve kurum LLM'i ile nesne incelemesi.
- Gerçek SMTP ile özet e-posta.
- Kurumsal ingress arkasında "Analizi durdur": açık durdurma isteği bu durum için eklendi.
