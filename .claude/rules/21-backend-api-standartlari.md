<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - app/backend/**/api/**
  - app/backend/**/schemas/**
  - specs/openapi/**
---

# API sözleşmelerini tipli, kiracıyı gözeten ve profilden bağımsız tut

# Arka uç API standartları

Yapılandırılmış API ön ekini birleşik yönlendirici veya uygulama başlatıcısı üzerinde tam bir kez
uygula. Alan yönlendiricileri ve uç nokta bezeyicileri göreli yol kullanır; fiziksel sürüm klasörü oluşturma
veya ön eki tekrarlama. Kaynak koleksiyonları çoğul adlar ve standart `HTTP` anlamı kullanır.

Her girdi ve çıktı, profile özgü doğrulama tipine sahiptir. Taşıma tiplerini kalıcılık modellerinden
ayrı tut. İç sayısal kimlikler API sınırını asla geçmez; dışarıdan adreslenebilir kayıtlar `public_id`
kullanır ve hizmet bunu etkin kiracı altında çözümler.

Korumalı uç noktalar doğrulanmış `JWT` erişim belirteci ve arka uç yetkilendirme koruması gerektirir.
Olağan aktörler kiracı, rol ve izin iddialarına karşı kontrol edilir. `super_admin` atlaması açık ve
merkezidir; anlık uç nokta mantığı olarak yeniden üretme. Ön yüz kapısı yalnız kullanılabilirlik
yardımcısıdır; arka uç yetkilendirmeyi her zaman uygular.

Taban kimlik doğrulama yüzeyi bilerek küçüktür: parola özeti doğrulama, imzalı `JWT` erişim belirteci
üretimi, tipli ayarlar üzerinden imza/süre dolumu/yayımcı/hedef kitle doğrulaması, `/me`, `RBAC` ve
istemci tarafında belirteç kaldırmayla oturumu kapatma. Kabul edilmiş `PRD` olmadan yenileme belirteci,
sunucu oturum deposu veya dış kimlik sağlayıcı ekleme. Ara yazılım doğrulanmış iddiaları veritabanına
gidip gelmeden ayrıştırabilir; güncel ve değişebilir yetki gereken uç nokta bunları açıkça yeniden
okumalıdır.

Profiller arasında tek tipli hata zarfı kullan:

```json
{"detail":{"code":"stable_code","message":"localized-safe explanation"}}
```

Doğrulama, kimliği doğrulanmamış, yasak, bulunamadı, çakışma ve beklenmeyen hata durumlarını kararlı
`HTTP` durumlarına ve kodlarına eşle. Yığın izini, veritabanı tanımlayıcısını, belirteç içeriğini veya
gizli değeri sızdırma. Liste uç noktaları açık sayfalama üst verisi ve belirlenimci sıralama döndürür.

Yazma işlemleri, tekrarlandığında aynı sonucu verme ve eşzamanlılık davranışını kabul edilmiş `PRD`
içinde tanımlar. İşlemleri hizmet sınırında ve parametreli kalıcılık API'leriyle kullan. `SQL` veya
dize birleştirerek `URL` oluşturma; seçilen profilin güvenli yardımcılarını kullan.

API yüzeyi değiştiğinde `OpenAPI`'yi çevrimdışı dışa aktar, kaydedilmiş yapıtla karşılaştır ve ardından
ön yüz tiplerini yeniden üret. Bayat sözleşme veya elle yazılmış yinelenen istemci tipi kapıyı
başarısız kılar.
