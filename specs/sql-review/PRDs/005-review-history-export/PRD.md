# PRD — review-history-export

Status: Accepted

Version: 1.1.0

Acceptance date: 2026-09-27

Domain: [sql-review](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-09-27'de, açık sorulardaki önerileri ve sahip kararlarını
benimseyerek kabul etti.

## Amaç

Biten her inceleme koşumu sunucuda saklanır. İnceleyici geçmiş koşumlarını hangi bilgisayardan
girerse girsin görür, yanlış pozitif işaretlerini kaydeder ve sonucu CSV (Excel'in açabildiği virgülle
ayrılmış tablo dosyası) ile düzeltme yorumlu SQL dosyası olarak indirir. Kayıtlar belirli bir süre
sonra kendiliğinden silinir.

## Aktörler ve sonuçlar

- **İnceleyici** (`inceleyici`): Kendi koşumlarını listeler, ayrıntısını açar, yanlış pozitif işaretler,
  CSV ve SQL indirir, kendi koşumlarını siler. Sonuç: tarayıcı değişse de geçmiş kaybolmaz.
- **Kural yöneticisi** (`kural-yoneticisi`): İnceleyicinin yapabildiklerine ek olarak herkesin
  koşumlarını salt okunur görür ve indirir (Decision 1). Sonuç: kuralların hangi nesnelerde
  yanlış pozitif ürettiğini görebilir.
- **İşletim ekibi**: Saklama süresini ortam ayarıyla belirler.

## Değişmezler ve sınırlar

- Geçmiş yalnız sunucuda, PostgreSQL'de (uygulamanın veritabanı) tutulur; tarayıcı depolaması
  kullanılmaz.
- Bir koşumu ve onun saklanan SQL metnini yalnız sahibi (koşumu başlatan kullanıcı) ve kural yöneticisi
  görür (Decision 1). Başkasının koşumu için yanıt, koşum yokmuş gibi 404'tür.
- Yanlış pozitif işaretini ve silmeyi yalnız koşumun sahibi yapar.
- Dışa aktarım SQL Server'a bağlanmaz ve LLM (büyük dil modeli) çağırmaz; yalnız saklanan koşumu
  kullanır.
- SQL metni, bulgu açıklaması ve kod parçası günlüklere (log) yazılmaz.
- Sahip olunan veri: yanlış pozitif işaretleri, saklama ve silme kuralı, dışa aktarım biçimleri.
  Koşumu, kural sonuçlarını, bulguları ve incelenen SQL metnini yazmak
  [nesne incelemesi](../003-object-review/PRD.md) ile [SQL metni incelemesi](../004-script-review/PRD.md)
  PRD'lerinindir; bu PRD onları okur. Koşumun kural sürümü
  [kural yönetimi PRD'sinden](../001-rule-management/PRD.md) gelir.

## Mevcut davranış

Kaynak: `~/codes/dwhcodereview`.

- Geçmiş tarayıcının yerel deposunda (`localStorage`, anahtar `dwh-code-review-analysis-history-v1`)
  en çok 50 kayıt olarak tutulur (`frontend/src/analysisHistoryStorage.ts`); başka tarayıcıda
  görünmez. **Hedefte değişir:** sunucuda, kullanıcıya ve süreye bağlı saklama.
- Kayıt inceleme bitince ekrandan eklenir (`frontend/src/contexts/ReviewAnalysisContext.tsx`): tür
  (`db`/`script`), zaman, başlık (`<veritabanı> · N nesne` ya da etiket, yoksa "Yapıştırılan SQL"),
  alt başlık (ilk 3 nesne ve `+N`), sonuçlar, hata. Hatalı koşum eklenir, durdurulan eklenmez.
- Yanlış pozitif işaretleri yalnız geçmiş sayfasında yapılırsa saklanır; canlı sonuç ekranındakiler
  kaybolur. İşaretler `veritabanı|şema|ad|sıra` metin anahtarlarıyla tutulur
  (`frontend/src/components/ReviewResults.tsx`). **Hedefte değişir:** Requirement 4.
- Geçmiş sayfası (`frontend/src/pages/AnalysisHistoryPage.tsx`): solda liste (tür rozeti, zaman,
  başlık, alt başlık, hata), sağda sonuçlar, "Yenile", "Tümünü sil", satır silme, onay soruları.
  Bu sayfada dışa aktarım yoktur. **Hedefte değişir:** geçmişten de CSV ve SQL indirilir.
- Dışa aktarım tarayıcıda üretilir (`frontend/src/components/ExportMenu.tsx`): sonuç penceresinde
  SQL, CSV, JSON, HTML; canlı panelde (`GlobalReviewProgress.tsx`) SQL ve CSV. SQL metni yoksa nesne
  tanımları SQL Server'dan yeniden çekilir; bu, incelenen değil güncel tanımı indirebilir. **Hedefte
  değişir:** yalnız CSV ve SQL, sunucuda üretilir, yeniden çekme yok (Decision 2 ve 3).
- SQL yorumundaki satır numaraları dosyadaki satıra kaydırıldıktan sonra "SSMS ile hizalama" diye
  hepsinden 1 çıkarılır (`buildSqlReviewCommentHeader`); hangi durumda doğru olduğu belirsizdir.
  **Hedefte değişir:** Requirement 8'deki ölçülebilir kural.

## İşlevsel gereksinimler

Requirement 1: Son durumu tamamlandı, hata, iptal edildi veya yarıda kesildi olan her koşum, ekran açık
kalmasa da geçmişte görünür. Liste satırı tür, başlangıç zamanı, başlık, alt başlık, durum, hata iletisi,
kural sürümü numarası, nesne sayısı ve bulgu sayısını gösterir; başlık ve alt başlık kaynaktaki biçimle
üretilir. **Yeni davranış:** sürüm numarası ve sayılar eklenir; iptal edilen koşum da "Durduruldu"
etiketiyle listelenir. İnceleme PRD'leri iptal edilen koşumun kısmi sonucunu saklamadığı için bu satırın
sonucu yoktur (Decision 4).

Requirement 2: Liste sayfalıdır (varsayılan 50, en çok 200 satır), en yeni koşum en üsttedir; aynı
zamanlı koşumlar kimliğe göre sıralanır. İnceleyici yalnız kendi koşumlarını görür. Kural
yöneticisi "Benim koşumlarım" ile "Tüm koşumlar" arasında seçim yapar; tüm koşumlarda sahibin görünen
adı da yazar.

Requirement 3: Koşum ayrıntısı, canlı sonuç ekranıyla aynı sonuç görünümünü (nesneler, kural
sonuçları, bulgular, nesne hatası ve ayrıştırma uyarısı) yanlış pozitif işaretleriyle birlikte
gösterir. Ayrıntı yanıtı SQL metnini içermez.

Requirement 4: Koşumun sahibi bir bulguyu veya bulgusu olmayan başarısız kural sonucunu yanlış pozitif
olarak işaretler veya işareti kaldırır; işaret hem canlı sonuç ekranında hem geçmişte aynı kayda
yazılır ve sayfa yenilense de korunur. Aynı değeri yeniden göndermek sonucu değiştirmez. Sahibi
olmayan kullanıcı işaret değiştiremez.

Requirement 5: Koşumun sahibi tek bir koşumu veya kendi bitmiş koşumlarının tümünü siler; silmeden
önce onay sorulur. Silme; koşumu, kural sonuçlarını, bulguları, işaretleri ve saklanan SQL metnini
kalıcı olarak kaldırır. Süren koşum silinemez. "Tümünü sil" başkasının koşumuna dokunmaz.

Requirement 6: Saklama süresini aşan koşumlar, süre koşumun bitiş zamanından sayılarak, günde en az
bir kez kendiliğinden ve Requirement 5'teki kapsamla silinir. Süre
`DWHCODEREVIEW_REVIEW_HISTORY_RETENTION_DAYS` ayarıyla 1–365 gün arasında verilir, varsayılanı 90
gündür (Decision 5). **Yeni davranış:** kaynaktaki "en çok 50 kayıt" sınırı kalkar.

Requirement 7: CSV dışa aktarımı kaynaktaki dosyayla aynı yapıdadır: UTF-8 BOM (Excel'in Türkçe
karakterleri doğru okuması için dosya başı işareti), satır sonu CRLF, sütunlar sırasıyla
`generated_at, database, schema, name, object_type, rule_id, tier, status, severity, description,
line_reference, code_snippet, false_positive`, tırnak kuralı ve satır düzleştirme kuralı
`buildReviewResultsCsv` ile aynıdır (başarısız kuralın bulguları varsa her bulgu bir satır, yoksa
kural sonucu bir satır, sonuçsuz nesne tek satır, sonuçsuz hatalı koşum tek hata satırı). Dosya adı
`sql-review-` ile başlar. **Yeni davranış:** `=`, `+`, `-`, `@`, sekme veya satır başı karakteriyle
başlayan hücrelerin önüne `'` eklenir; böylece Excel hücreyi formül olarak çalıştırmaz.

Requirement 8: SQL dışa aktarımı, kaynaktaki yorum bloğunu (`/*` … `*/`, başlık
"SQL Review - Duzeltilmesi Gereken Yerler", nesne başına `- <kural> — <Satir …> — <açıklama>`,
açıklamada `|` yerine `¦`, madde yoksa "Tespit edilen duzeltme maddesi yok.") ve altında incelenen
SQL metnini içerir. Nesne koşumunda her nesne `-- [veritabanı] şema.ad (tür)` başlığıyla ve aralarında
`GO` ile yazılır; metin koşumunda yapıştırılan metin olduğu gibi yazılır. Yorumdaki her "Satir N"
değeri, indirilen dosyada bulgunun gösterdiği kaynak satırının gerçek satır numarasıdır. Dosya adı
`sql-review-source-` ile başlar.

Requirement 9: Yanlış pozitif işaretli bulgular CSV'de `false_positive` sütununda `true` olarak
kalır; SQL yorum bloğuna yazılmaz (Decision 6). **Yeni davranış:** kaynak SQL yorumunda
işaretleri dikkate almıyordu.

Requirement 10: Koşumda saklanmış SQL metni yoksa (nesne tanımı alınamadan hata ile bitmiş, iptal
edilmiş veya yarıda kesilmiş koşum) SQL indirme düğmesi pasiftir ve API 409 döner. **Yeni davranış:** kaynak bu durumda sessizce hiçbir şey
yapmıyordu.

Requirement 11: Tarayıcıdaki eski geçmiş taşınmaz ve yeni uygulama `localStorage` geçmişini okumaz.
Tüm ekran metinleri Türkçedir.

## API sözleşmesi

Tüm uçlar `/api/dwhcodereview/v1` altındadır, geçerli oturum ister ve hatayı
`{"detail":{"code":"...","message":"..."}}` biçiminde döner. `{run_id}`, `{finding_id}` ve
`{rule_result_id}` dışa açık `public_id` değerleridir.

| Yöntem ve yol | Rol | İstek → yanıt |
|---|---|---|
| `GET /review-runs` | inceleyici, kural-yoneticisi | `scope=mine\|all`, `page`, `page_size` → satırlar ve sayfa bilgisi |
| `GET /review-runs/{run_id}` | sahip; kural-yoneticisi | → koşum ayrıntısı (Requirement 3) |
| `PUT /review-runs/{run_id}/findings/{finding_id}/false-positive` | sahip | `{false_positive: bool}` → güncel işaret |
| `PUT /review-runs/{run_id}/rule-results/{rule_result_id}/false-positive` | sahip | `{false_positive: bool}` → güncel işaret |
| `DELETE /review-runs/{run_id}` | sahip | → 204 |
| `DELETE /review-runs?scope=mine` | sahip | → `{deleted_count}` |
| `GET /review-runs/{run_id}/exports/csv` | sahip; kural-yoneticisi | → `text/csv; charset=utf-8`, indirme dosyası |
| `GET /review-runs/{run_id}/exports/sql` | sahip; kural-yoneticisi | → `application/sql; charset=utf-8`, indirme dosyası |

Hata kodları: 401 `not_authenticated`; 403 `review_scope_forbidden` (`scope=all` isteyen inceleyici)
ve `review_run_not_owner` (görebildiği ama sahibi olmadığı koşumu değiştirme); 404
`review_run_not_found` (yok, süresi dolmuş veya görme yetkisi olmayan koşum); 409
`review_run_in_progress` (Requirement 5), 409 `sql_text_unavailable` (Requirement 10); 422
geçersiz sayfa değeri. Oturum anahtarı adrese (URL) konmaz; indirme, oturum başlığıyla yapılan
istekten dosya olarak kaydedilir.

## Güvenlik ve yetkilendirme

- Görme, işaretleme, silme ve indirme yetkisi her istekte arka uçta, sahiplik ve role göre
  denetlenir; sorgular etkin kiracı (kurum) kapsamındadır. Görme yetkisi olmayan koşum 404 alır.
- Saklanan SQL metni kurum içi kaynak kodudur; yalnız koşumun sahibine ve kural yöneticisine dışa
  aktarım ucundan döner, ayrıntı ve liste yanıtlarında yer almaz, loga yazılmaz.
- LLM'den gelen açıklama ve kod parçaları dosyaya yazılırken CSV'de formül koruması (Requirement 7)
  uygulanır; SQL dosyası yalnız metin olarak indirilir, sunucuda çalıştırılmaz.

## Veri ve geçiş

- Bu PRD'nin eklediği veri yalnız bulgu ve kural sonucu üzerindeki yanlış pozitif işaretidir (değer,
  değiştiren, zaman). Koşum, koşum nesnesi, kural sonucu ve bulgu tablolarının ve sütunlarının sahibi
  [nesne incelemesi PRD'sidir](../003-object-review/PRD.md) (Requirement 16); nesne koşumunu o PRD,
  metin koşumunu [SQL metni incelemesi PRD'si](../004-script-review/PRD.md) (Requirement 9) yazar. Bu
  PRD şu alanları okur: `public_id`, başlatan kullanıcı, tür, metin koşumunun etiketi, koşum
  nesnelerinin veritabanı, şema, ad ve türü, durum, başlangıç ve bitiş zamanı, hata kodu ve iletisi,
  kural sürümü numarası ve koşum nesnesinin incelenen SQL metni. Başlık ve alt başlık bu alanlardan
  okunurken üretilir. Tarayıcıdaki eski kayıtlar taşınmaz (Decision 7).
- Silme, koşuma bağlı tüm satırları (incelenen SQL metni dahil) tek işlemde (transaction) kaldırır.
  LLM çağrı özetleri koşum silinince silinmez, yalnız koşum bağları boşalır; saklamaları
  [LLM bağlantısı PRD'sinindir](../006-llm-connection/PRD.md).
- Şemanın sahibi SQLAlchemy modelleridir; değişiklik Alembic göçüyle (veritabanı yapısını sürüm
  sürüm kuran betik) gelir. Koşumun bitiş zamanı üzerinde silme işi için dizin bulunur.

## Gözlemlenebilirlik

- Yapılandırılmış log olayları: `review_history.deleted` (koşum `public_id`, sayı, kullanıcı
  `public_id`), `review_history.exported` (koşum `public_id`, biçim, satır veya nesne sayısı),
  `review_history.retention_run` (silinen koşum sayısı, süre, sonuç). SQL metni, açıklama ve kod
  parçası yer almaz.
- Ölçümler (metrik): biçime göre dışa aktarım sayısı `dwhcodereview_review_exports_total{format}`
  (`format` `csv` veya `sql`), saklama işinin sildiği koşum sayısı
  `dwhcodereview_review_history_retention_deleted_runs_total` ve saklama işinin son başarılı çalışma
  zamanı `dwhcodereview_review_history_retention_last_success_timestamp_seconds` (Unix saniyesi);
  bu zaman 48 saatten eskiyse iş durmuş demektir. Koşum ve kullanıcı ölçüme girmez. Ortak kurallar
  ve saklama süresi [application-foundation alanında](../../../application-foundation/DOMAIN.md)
  tanımlıdır. Tüketen test: `app/backend/tests/integration/test_telemetry_signals.py`.

## Dağıtım etkisi

- Yeni tablolar ve sütunlar dağıtımdaki göç adımıyla uygulanır
  ([Kubernetes dağıtımı PRD'si](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)).
- Saklama işi arka uç sürecinin içinde çalışır; birden çok kopya varsa PostgreSQL kilidiyle
  (advisory lock) yalnız biri siler. Yeni chart nesnesi, sır veya ağ çıkışı yoktur; yalnız yeni ortam
  ayarı `DWHCODEREVIEW_REVIEW_HISTORY_RETENTION_DAYS` values dosyasına eklenir.
- Saklanan SQL metni veritabanı boyutunu büyütür; kalıcı disk boyutu plan aşamasında 90 günlük tahmini
  hacme göre doğrulanır.

## Test stratejisi

- Arka uç birim testleri: CSV'nin kaynaktaki `buildReviewResultsCsv` ile aynı girdide aynı baytları
  vermesi, formül koruması, SQL yorum bloğu ve satır eşlemesi (nesne ve metin koşumu), işaretli
  bulgunun yorumdan çıkması.
- Gerçek PostgreSQL testleri: sahiplik ve rol başına 401/403/404, sayfalama, işaret tekrarı, silme
  kapsamı, süren koşumda 409, saklama işinin yalnız süresi dolanı ve iki kopyada tek kez silmesi.
- Ön yüz testleri (Vitest): liste, ayrıntı, onaylar, indirme düğmeleri, pasif SQL düğmesi,
  `localStorage` geçmişinin yazılmaması.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: arka uç testleri Requirement 1–6 ve 10'u gerçek
  PostgreSQL ile doğrular; OpenAPI (API tanım dosyası) kayıtlı yapıtla aynıdır.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: dışa aktarım testleri Requirement 7–9'u sabit
  örnek koşumlarla bayt düzeyinde doğrular.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: ön yüz testleri Requirement 3, 4, 5, 10 ve 11'i
  doğrular.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel PostgreSQL ve tarayıcıyla inceleyici
  bir metin koşumu tamamlar, canlı ekranda bir bulguyu yanlış pozitif işaretler, başka bir tarayıcıdan
  girip koşumu geçmişte işaretiyle görür, CSV ve SQL indirir; CSV Excel'de Türkçe karakterlerle
  açılır, SQL dosyasındaki "Satir N" değerleri dosyadaki satırlarla örtüşür (Requirement 1, 3, 4,
  7, 8).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: ikinci bir inceleyici ilk kullanıcının
  koşumunu ve SQL dışa aktarımını göremez (404); kural yöneticisi "Tüm koşumlar"da görür ve SQL
  dosyasını indirir ama işaret değiştiremez ve silemez;
  saklama süresi 1 güne ayarlanıp bitiş zamanı geçmişe çekilen koşum saklama işiyle silinir
  (Requirement 2, 4, 5, 6).

## Kararlar

- Decision 1: İnceleyici yalnız kendi koşumlarını görür; kural yöneticisi herkesin koşumlarını salt
  okunur görür ve indirir. Kural yöneticisi yanlış pozitifleri görerek kuralları iyileştirir;
  inceleyicinin çalışması diğer inceleyicilere açılmaz.
- Decision 2: İncelenen SQL metni koşumla birlikte saklama süresi boyunca saklanır; metni inceleme
  PRD'leri yazar, bu PRD dışa aktarımda okur. SQL indirme nesnenin güncel tanımını çekmez; satır
  numaraları incelenen metinle uyuşur. Metin yalnız dışa aktarımda döner, loga girmez.
- Decision 3: JSON ve HTML dışa aktarımı kaldırılır; alan tanımı ve kullanıcıların iş akışı CSV ve SQL
  üzerinedir. Gerekirse ayrı gereksinim olarak geri eklenir.
- Decision 4: Durdurulan (iptal edilen) koşum geçmişte "Durduruldu" etiketiyle görünür. Kısmi sonuç
  saklanmadığı için ([nesne incelemesi](../003-object-review/PRD.md) Requirement 15) satırın sonucu ve
  SQL metni yoktur.
- Decision 5: Saklama süresi varsayılan 90 gündür; ayar 1–365 gün arasındadır (Requirement 6).
- Decision 6: Yanlış pozitif işaretli bulgular SQL yorum bloğundan çıkarılır (Requirement 9); kullanıcı
  kılavuzu "rapor buna göre güncellenir" diyor, ancak kaynak SQL dosyasında bunu yapmıyordu.
- Decision 7: Tarayıcıdaki eski geçmiş taşınmaz; kayıtların sahibi ve kural sürümü bilinmiyor, en çok 50
  kayıtlık geçici bir depo.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama ([Plan](plan.md), [Görevler](tasks.md)).

## Riskler

- SQL metninin sunucuda saklanması, tarayıcıda dağınık duran kaynak kodu merkezi bir veritabanında
  toplar; erişim denetimi veya saklama işi bozulursa kod gereğinden uzun veya geniş kitleye açık
  kalır.
- Satır numarası eşlemesi LLM'in yazdığı "Satır N" metnine dayanır; LLM yanlış satır verirse dosya
  da yanlış yeri gösterir. Bu PRD yalnız eşlemenin doğruluğunu garanti eder.
- CSV formül koruması, `-` ile başlayan kod parçalarının (örneğin `-- yorum`) önüne `'` ekler; bu
  hücre içeriğini görünür biçimde değiştirir.
- Eski tarayıcı geçmişi kaybolur; geçişte kullanıcılara duyurulmalıdır.
