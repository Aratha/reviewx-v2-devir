# sql-review alanı

## Amaç ve sonuçlar

Veri ambarı geliştiricileri, SQL Server'daki nesnelerini (saklı yordam, görünüm, fonksiyon) ve
yapıştırdıkları SQL metnini kurumun yayımlanmış inceleme kurallarına göre kurum içi LLM ile inceler.
Sonuç, her kural için satır referanslı bulgular ve düzeltme notlarıdır; CSV ve düzeltme yorumlu SQL
olarak dışa aktarılır. Bu alan, `~/codes/dwhcodereview` uygulamasının davranışını fabrika yapısına
taşır; mevcut davranış kaynak kabul edilir, farklılıklar PRD'lerde açıkça yazılır.

## Aktörler

- **İnceleyici:** Veri ambarı geliştiricisi. Nesne veya metin inceletir, sonuçları görür, dışa aktarır.
- **Kural yöneticisi:** İnceleyicinin yapabildiklerine ek olarak kuralları düzenler ve yayımlar,
  LLM çağrı özetlerini görür.
- **İşletim ekibi:** Ortam ayarlarını, sırları ve dağıtımı yönetir; uygulama içinde bir rol değildir.

## Ortak dil

- **Kural:** Kimliği (`Kural01` biçiminde), metni ve "nesne meta verisi gerekir" işaretini taşıyan
  tek inceleme ölçütü. Kurallar **kritik** ve **normal** olmak üzere iki öncelik grubundadır.
- **Kural kümesi:** Kuralların tamamı. Bir **taslak** ve yayımlanmış **sürümler** vardır; inceleme
  yalnız en son yayımlanmış sürümü kullanır.
- **Nesne:** SQL Server'daki kullanıcı nesnesi: saklı yordam, görünüm, skaler/satır içi/tablo
  fonksiyonu. Veritabanı, şema, ad ve türle tanımlanır.
- **Nesne meta verisi:** Nesnenin bağımlı olduğu nesneler ve sütun özetleri; yalnız işaretli
  kurallarda LLM isteğine eklenir.
- **İnceleme koşumu:** Bir veya daha çok nesnenin ya da bir SQL metninin, belirli bir kural sürümüyle
  incelenmesi. Canlı ilerleme olayları üretir.
- **Kural sonucu:** Bir nesne ve bir kural için LLM değerlendirmesi: uyumlu, ihlal var veya
  değerlendirilemedi.
- **Bulgu (ihlal):** Kural sonucundaki tek ihlal; satır referansı, kod parçası ve açıklama taşır.
  Açıklama düzeltme notu olarak kullanılır; ayrı bir düzeltme önerisi alanı yoktur.
- **İki parçalı analiz:** Eşik uzunluğu aşan SQL'in iki parçada incelenip sonuçların birleştirilmesi.
- **LLM çağrı özeti:** Bir LLM çağrısının zaman, model, süre, durum ve belirteç sayısı gibi meta
  verisi. Ham SQL veya ham yanıt değildir.

## Değişmezler

- İnceleme yalnız yayımlanmış kural sürümünü kullanır; her koşum hangi sürümle yapıldığını saklar.
- SQL Server'a yalnız salt okunur katalog ve tanım sorguları gider; uygulama SQL Server'da yazma
  yapmaz ve incelenen kodu çalıştırmaz.
- Ham SQL metni ve ham LLM yanıtı günlüklere yazılmaz; yalnız LLM çağrı özeti saklanır.
- LLM isteği yalnız onaylı kurum içi LLM ucuna gider; ağ politikası dışındaki hedef reddedilir.
- Sırlar (SQL Server parolası, LLM anahtarı, LDAP ve oturum anahtarları) yalnız sunucu sınırındadır;
  arayüze, Git'e ve loga girmez.
- Nonprod'da SQL Server ve LLM bağlantı ayarları arayüzden değiştirilemez.

## Sahip olunan veri

PostgreSQL'de: kural kümesi taslağı ve yayımlanmış sürümleri, inceleme koşumları, kural sonuçları ve
bulgular, LLM çağrı özetleri. İncelenen SQL metni (nesne tanımı veya yapıştırılan metin) koşumla
birlikte saklama süresi boyunca (varsayılan 90 gün) tutulur; yalnız koşumu başlatan kullanıcı ve
`kural-yoneticisi` görür. Günlüklere yazılmaz.

## Harici sınırlar

- **SQL Server veri ambarı:** ODBC ile, ortama göre yapılandırılan salt okunur hesapla.
- **Kurum içi LLM sunucusu:** OpenAI uyumlu veya LM Studio tarzı sohbet ucu, kurum CA'sıyla TLS.
- Kimlik ve dağıtım `application-foundation` alanındadır.

## İş yetkinliği yol haritası

[Yol haritası](roadmap.md).
