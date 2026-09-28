<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - schema/**
  - app/backend/**
  - helm/**
  - app/infra/**
  - specs/**/PRDs/**
---

# Vektör aramasını ve gömme üretimini yönetilen sınırlar içinde tut

# Vektör araması ve gömme sınırı

`PGVector`, sabit `PostgreSQL` profilinin isteğe bağlı yeteneğidir; ikinci kalıcılık motoru değildir.
Yalnız kabul edilmiş `PRD` vektör araması veya gömme depolaması tanımladığında kullan. Ayrı vektör
veritabanı, çalışma zamanında seçilebilir vektör deposu ve veritabanları arası benzerlik sorgusu yasaktır.
Uzantı, sınırlı bağlamın `PostgreSQL` veritabanında kalır; kaynak kayıtlarla aynı sahiplik, kiracı
yalıtımı, göç, yedekleme, saklama ve kurtarma kontrollerini izler.

Kabul edilmiş `PRD`; onaylı gömme sağlayıcısını, değişmez model kimliğini/sürümünü, boyutu,
normalleştirme davranışını, uzaklık ölçütünü, kesin/yaklaşık dizin stratejisini, kalite/`recall`
hedefini, gecikme hedefini, kaynak veri sınıflandırmasını, saklamayı ve yeniden gömme planını kaydeder.
Yalnız onaylı iç hizmet veya kurum içi model kullan. Çalışma zamanı internet çıkışı ve model indirme
yasak kalır.

Uygulama hizmetleri tipli gömme bağlantı noktasını çağırır; model istemcisi ve sağlayıcı ayrıntılarının sahibi
altyapı uyarlayıcısıdır. Alan modeli, uç nokta ve depo gömme modelini çağırmaz. Göç asla gömme üretmez
veya ağ çağrısı yapmaz. Arka plan/toplu iş aynı bağlantı noktasını kullanabilir ve kiracı,
yetkilendirme, yeniden
deneme, aynı sonucu verme ve gözlemlenebilirlik sınırlarını korumalıdır.

Özete sabitlenmiş `PostgreSQL` imajı kabul edilmiş uzantı ikili dosyasını sağladıktan sonra `SQL` uzantısı
`vector` değerini incelenmiş `Alembic` göçüyle etkinleştir. Çalışma zamanında paket kurma, uygulama
veritabanı rolüne uzantı yönetimi ayrıcalığı verme veya uygulama başlarken `CREATE EXTENSION` çalıştırma.
Yetenek yürütülebilir olduğunda şema yetkisi, göç, platform imaj envanteri ve bağımlılık kabul kaydı
birlikte değişir.

Her gömme kaydı tek sınırlı bağlama aittir; kiracıyla nitelenmiş kaynak kimliği, sabit boyutlu
`vector(n)`, gömme modeli kimliği/sürümü, kaynak içerik özeti ve zorunlu yaşam döngüsü/denetim yapısı
taşır. Farklı model sürümü veya boyutlardaki gömmeleri ayrı tipli sütun, tablo veya bölümde tut; tek
karşılaştırılabilir küme olarak arama. Kabul edilmiş platform sınırlı bağlamı ve açık sahiplik olmadan
genel, alanlar arası gömme tablosu oluşturma.

Benzerlik `SQL`'i yalnız parametreli depo uygulamasında bulunur. Sorgu, kiracı ve yetkilendirmeyle nitelenmiş
kaynak süzgeçlerini içerir; uzaklık işleci ve boyut kodda sabittir. Çağıran, `SQL` işlecini, dizin
parametresini veya sınırsız aday sayısını seçemez. Kesin aramayla başla. `HNSW` veya `IVFFlat`'i yalnız
temsili `recall`/gecikme kanıtı, eşleşen işleç sınıfı, sınırlı sorgu parametresi ve testlerde kesin arama
karşılaştırmasıyla kabul et.

Kaynak metni ve vektörleri yönetilen veri olarak ele al. Gömme öncesi girdiyi en aza indir, sırları ve
yasak alanları dışla, kaynak kaydın erişim/saklama politikasını uygula; istemi, kaynak içeriği, vektörü
veya en yakın komşu yükünü asla günlükleme. Model değişikliği yeni sürümlü küme oluşturur:
tekrarlandığında aynı sonucu veren geçmiş veri doldurma yap, boyutu ve geri getirme kalitesini doğrula,
açık geçiş yap ve test edilmiş geri alma yolunu koru. Yıkıcı yeniden oluşturma, açık yetkilendirme ve
tam kapsam denetimi gerektirir.

Göç ettirilmiş uzantı sürümünü, sütun boyutunu, üst veri kısıtını, kiracı yalıtımlı geri getirmeyi,
model sürümü ayrımını, tekrarlandığında aynı sonucu veren geçmiş veri doldurmayı ve
sağlayıcı/uyarlayıcı hata davranışını doğrula. Yaklaşık dizin için yetenek tamamlandı iddiasından
önce temsili ilk `k` sonucunu kesin aramayla karşılaştır; `recall` değerini, gecikmeyi, dizin boyutunu,
oluşturma süresini ve süzülmüş sorgu davranışını kaydet.
