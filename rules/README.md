# Kanonik Kural Külliyatı

Bu dizin, ajana dönük proje kuralları için yazılan tek kaynaktır. İstemciye özgü talimat, beceri,
düzenleyici kuralı ve spesifikasyon aracı anayasası bu külliyattan oluşturulur. Üretilmiş kopyalar
çıktıdır: kaynak kuralı burada değiştir ve yeniden üret; üretilmiş kopyayı düzenleyerek sapmayı asla
onarma.

## Dosya sözleşmesi

- Her kural tek `<priority>-<slug>.md` dosyasında bulunur.
- Her kural `corpus.schema.json` ile doğrulanan `YAML` `frontmatter` alanıyla başlar.
- `id` kararlı ve benzersizdir; `.md` olmadan dosya adına eşittir.
- `title` tek satırlık emir veya değişmezdir.
- `scope`; `governance`, `process`, `backend`, `frontend`, `schema`, `deployment`, `quality` veya
  `desktop` değeridir.
- `authority` varsayılan olarak `recommended` değeridir; zorunlu davranış açıkça
  `authority: mandatory` bildirmelidir. Kanonik kural, yerel envanter için ayrılan `project-owned`
  değerini kullanmaz.
- `priority` kuralları kapsam içinde sıralar; düşük değer önce oluşturulur.
- `trigger`; `always`, `path-match` veya `on-demand` değeridir.
- `applies_to` depoya göreli genel arama kalıbı içerir; yalnız depo geneli kural için boştur.
- `gate`, kuralı uygulayan denetimi adlandırır; uygulama yalnız incelemeyse `none` değerini kullanır.
- `application_modes` isteğe bağlıdır; kuralı yalnız listelenen uygulama kiplerindeki
  (`separated-web`, `desktop`) projelere taşır. Alan yoksa kural her kipe gider.
- `Markdown` gövdesi gözlemlenebilir davranışı, etkilenen yolu ve doğrulama yöntemini belirtmelidir.

Örnek:

```markdown
---
id: "20-example"
title: "Örnek sınırı açık tut"
scope: backend
priority: 20
trigger: path-match
applies_to:
  - "app/backend/**"
gate: "backend-test.yml"
---
```

## Yazım kuralları

1. Ürün niyetini ve alan söz varlığını `.kt-scaffold/answers.yml` ve `specs/` içinde tut; bu külliyata
   ürün, kurum, ticari ortak veya sektörü doğrudan kodlama.
2. Profilden bağımsız değişmezleri burada belirt. Davranış arka uç/kalıcılık profiline göre
   değişiyorsa okuyucuyu `.kt-scaffold/answers.yml` ve `schema/profile.yml` kaynaklarına yönlendir ve
   desteklenen dalları açıkça tanımla.
3. Külliyat dosyaları arasında anlatıyı yineleme. Başka bir konuya bağımlıysa sahibi olan kurala
   bağlantı ver.
4. Kalıcı kurala olay, tarih, göç geçmişi veya geçici istisna koyma.
5. Davranış mekanik olarak denetlenebiliyorsa kurala kapı ekle. Gerçek denetimi olmayan kapı adı,
   uygulama değildir.
6. Kural gövdelerini Türkçe tut. Kodu, tanımlayıcıyı, şema anahtarını, sıralı değeri, yolu,
   komutu ve sağlayıcı `frontmatter` alanlarını İngilizce kanonik biçimde koru.

## Değişiklik iş akışı

1. Sahibi olan en küçük külliyat dosyasını düzenle veya ekle.
2. Tüm `frontmatter` alanlarını `corpus.schema.json` ile doğrula; yinelenen `id` veya `priority` değerini
   reddet.
3. Desteklenen her istemciyi oluştur.
4. `scripts/render-clients.sh --check` komutunu ve değişen kuralın adlandırdığı kapıyı çalıştır.
5. Külliyat değişikliğiyle yeniden üretilmiş çıktıları birlikte `commit` et.
