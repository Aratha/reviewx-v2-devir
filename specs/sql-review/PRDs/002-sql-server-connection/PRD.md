# PRD — sql-server-connection

Status: Accepted

Version: 1.2.0

Acceptance date: 2026-09-27

Domain: [sql-review](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-09-27'de, açık sorulardaki önerileri ve sahip kararlarını
(Decision 11 dahil) benimseyerek kabul etti.

## Amaç

Uygulama, SQL Server veri ambarına ortama göre yapılandırılan salt okunur hesapla bağlanır; veritabanı listesini, **Nesne** listesini, Nesnenin SQL tanımını ve **Nesne meta verisini** yalnız okuma sorgularıyla getirir. Bağlantı ayarı **Ortam** `local` iken arayüzden düzenlenebilir; `nonprod` iken yalnız dağıtımdan gelir (hesap **Runtime Secret** `dwhcodereview-runtime`'tan) ve arayüzden değiştirilemez; hesap veya adres verilmemişse uygulama yine açılır ve SQL Server alanı "yapılandırılmamış" görünür. SQL Server çağrıları uygulamanın diğer isteklerini bekletmez; hatalar kullanıcıya sabit, iç ayrıntı içermeyen iletilerle döner.

## Aktörler ve sonuçlar

- `inceleyici`: İnceleme sayfasında izinli veritabanlarını ve seçtiği veritabanındaki Nesneleri görür; incelediği Nesnenin tanımı ve Nesne meta verisi bu PRD'nin portundan okunur. SQL Server yavaşken bile uygulamanın diğer ekranları yanıt verir.
- `kural-yoneticisi`: `local` Ortamda SQL bağlantısı sayfasında sunucu, port, kullanıcı, parola ve şifreleme ayarını düzenler ve kaydetmeden bağlantıyı test eder. `nonprod` Ortamda bu sayfayı görmez.
- **İşletim ekibi** (uygulama rolü değildir): `nonprod` için ortak salt okunur hesabı isteğe bağlı Azure gizli değişkenleri `MSSQL_USER` ve `MSSQL_PASSWORD` olarak tanımlar; `helm/dwhcodereview/deploy-hooks.sh` bunları Runtime Secret'a yazar. Tanımlamazsa uygulama açılır ve SQL Server alanı "yapılandırılmamış" kalır (Decision 11).
- [Nesne incelemesi PRD'si](../003-object-review/PRD.md): Veritabanı ve Nesne listeleme uçlarının ve filtrelerinin sahibidir; veritabanı listesini, Nesne listesini, Nesne tanımını ve Nesne meta verisini bu PRD'nin tanımladığı katalog sınırından (Decision 2 portu) alır.

## Değişmezler ve sınırlar

- SQL Server'a yalnız bu PRD'de sayılan salt okunur katalog ve tanım sorguları gider. Uygulama SQL Server'da yazma yapmaz, incelenen kodu çalıştırmaz, kullanıcı metnini SQL olarak birleştirmez; her değer parametreyle gönderilir.
- SQL Server parolası yalnız sunucu sınırındadır: API yanıtına, arayüze, Git'e, Helm değer dosyasına, loga ve diske yazılmaz.
- `nonprod` Ortamda bağlantı ayarı çalışma sırasında değiştirilemez; ayar yazma ve bağlantı testi uçları hiç yayımlanmaz.
- Ortam `DWHCODEREVIEW_ENVIRONMENT` ayarından okunur: `development` → `local`, `staging` → `nonprod`; başka, tanınmayan veya okunamayan değerde uygulama `nonprod` gibi davranır (kapalı taraf; [application-foundation alanı](../../../application-foundation/DOMAIN.md), Decision 10).

Decision 1: Bağlantı yalnız yapılandırılmış alanlarla tanımlanır: sunucu, port, kullanıcı, parola, şifreleme (`Encrypt`) ve sunucu sertifikasına güven (`TrustServerCertificate`). Serbest ODBC bağlantı dizesi (SQL Server sürücüsüne verilen `Anahtar=Değer;` biçimli tek satır) girdi olarak kabul edilmez; dize sunucuda bu alanlardan tek yardımcıyla ve değerleri kaçışlanarak üretilir. Kaynaktaki `MSSQL_CONNECTION_STRING` ayarı ve onu çözümleyen yol kaldırılır.

Decision 2: SQL Server erişimi bir uygulama portu (iş katmanının çağırdığı arayüz) ile altyapı uyarlayıcısı arasında ayrılır. Port dört işlem sunar: veritabanı listesi, Nesne listesi, Nesne tanımı ve Nesne meta verisi. Uç noktalar ve Nesne incelemesi yalnız bu portu kullanır.

Decision 3: `local` Ortamda arayüzden yapılan değişiklik yalnız çalışan süreçte tutulur ve `app/backend/.env` dahil hiçbir dosyaya yazılmaz; yeniden başlatmada `.env`'deki değerlere dönülür (Decision 8).

## Mevcut davranış

Kaynak uygulama `~/codes/dwhcodereview` bugün şöyle çalışır; hedefteki değişiklik her maddede belirtilmiştir.

- **Ayar okuma:** `backend/config.py` `MSSQL_SERVER`, `MSSQL_PORT` (1433), `MSSQL_USER`, `MSSQL_PASSWORD`, `MSSQL_TRUSTED_CONNECTION` (false), `MSSQL_ENCRYPT` (true), `MSSQL_TRUST_SERVER_CERTIFICATE` (true) ve `MSSQL_CONNECTION_STRING` alanlarını okur. `services/sql_env.py` önce yapılandırılmış alanları, sunucu boşsa eski bağlantı dizesini çözümler. **Hedefte:** yalnız yapılandırılmış alanlar, `DWHCODEREVIEW_` önekiyle (Decision 1).
- **Ayar yazma:** `PUT /api/sql-config` (`backend/main.py`) `merge_sql_into_dotenv` ile değerleri, parola ve parolayı içeren bağlantı dizesi dahil, çalışma sırasında `backend/.env` dosyasına ve süreç ortamına yazar. Boş parola kayıtlı parolayı siler. Arayüz metni de "Değerler `backend/.env` dosyasına yazılır" der (`frontend/src/pages/SqlConfigPage.tsx`). **Hedefte:** dosyaya yazma tamamen kalkar; `local`'de yalnız süreç içi değişiklik, `nonprod`'da uç yok.
- **Bağlantı testi:** `POST /api/sql-config/test` formdaki değerlerle `master` veritabanına 15 saniyelik giriş süresiyle bağlanır, çevrimiçi veritabanlarını sayar. Hata olursa sürücünün ham hata metnini (`str(exc)`) kullanıcıya döndürür. Formda sunucu değiştirilip parola boş bırakılırsa **kayıtlı parola yeni sunucuya gönderilir**. **Hedefte:** ham metin yerine sabit hata sınıfı; sunucu, port veya kullanıcı değiştiyse kayıtlı parola kullanılmaz (Requirement 4).
- **Windows kimlik doğrulaması:** `Trusted_Connection=yes` seçilebilir. Linux konteynerinde Kerberos kurulmadan çalışmaz. **Hedefte:** kaldırılır (Decision 7).
- **Sertifika doğrulaması:** Varsayılan `TrustServerCertificate=yes`; yani bağlantı şifreli olsa da sunucu sertifikası doğrulanmaz. **Hedefte:** `nonprod`'da şifreleme ve sertifika doğrulaması zorunludur (Decision 6).
- **Bağlantı dizesi üretimi:** `build_connection_string` `UID` ve `PWD` değerlerini süslü parantezle kaçışlamaz; `;` içeren bir parola dizeye yeni sürücü ayarı ekleyebilir. `db/connection.py` veritabanı adını kaçışlar. **Hedefte:** bütün değerler kaçışlanır.
- **Sorgular:** `db/connection.py` her çağrıda `pyodbc.connect(..., timeout=30)` ile yeni bağlantı açar (30 sn yalnız giriş süresidir; sorgu süresi sınırı yoktur). `services/database_catalog.py` `sys.databases` içinden `state = 0` olanları; `services/object_catalog.py` `db/queries.py` `LIST_OBJECTS_SQL` ile `P`, `V`, `FN`, `IF`, `TF`, `SF` türündeki ve `is_ms_shipped = 0` olan Nesneleri getirir, ad/tür süzmesini ve tarih süzmesini (oluşturma veya değişiklik tarihi seçilen günden sonra) Python'da yapar. `services/sql_fetcher.py` `OBJECT_DEFINITION` ile tanımı alır. **Hedefte:** sorgular aynı kalır; giriş ve sorgu süre sınırı eklenir.
- **Nesne meta verisi:** `services/dependency_metadata.py` `sys.dm_sql_referenced_entities` ile bağımlılıkları en fazla 4 derinlik ve 48 Nesneye kadar izler; iki parçalı ad bulunamazsa sunucudaki 48 veritabanına kadar tarar; sütun özetini `sys.columns` ve `sys.types` ile alır; metni 95.000 karakterde keser; hata olursa boş döner. **Hedefte:** sınırlar korunur; taranan veritabanları izin listesiyle sınırlanır (Decision 5).
- **Olay döngüsünü bekletme:** `services/review_orchestrator.py` `fetch_definition` ve `fetch_dependency_metadata_context` işlevlerini eşzamanlı olmayan (`async`) kod içinden doğrudan çağırır; `pyodbc` beklerken uygulamanın bütün istekleri (olay döngüsü: uygulamanın çok sayıda isteği tek iş parçacığında sırayla işleyen düzeni) durur. **Hedefte:** her SQL Server çağrısı ayrı iş parçacığında ve sınırlı sayıda koşar (Requirement 6).
- **Hata eşleme:** Katalog uçları yapılandırma eksikse 503, diğer hatalarda 500 ve genel ileti döndürür; Nesne inceleme sonucu ise `Database error: <ham hata>` metnini taşır. **Hedefte:** Requirement 8 hata sınıfları.
- **Yetki:** Uçlar yalnız isteğe bağlı paylaşılan `X-API-Key` / `X-Admin-Key` ile korunur; `GET /api/health` `sql_configured` bilgisini herkese verir. **Hedefte:** dizin girişi ve rol (Güvenlik bölümü); sağlık ucu SQL durumu taşımaz.

## İşlevsel gereksinimler

Requirement 1: Tipli ayarlar `DWHCODEREVIEW_MSSQL_SERVER`, `DWHCODEREVIEW_MSSQL_PORT` (varsayılan 1433, 1–65535), `DWHCODEREVIEW_MSSQL_USER`, `DWHCODEREVIEW_MSSQL_PASSWORD`, `DWHCODEREVIEW_MSSQL_ENCRYPT`, `DWHCODEREVIEW_MSSQL_TRUST_SERVER_CERTIFICATE`, `DWHCODEREVIEW_MSSQL_ALLOWED_DATABASES`, `DWHCODEREVIEW_MSSQL_LOGIN_TIMEOUT_SECONDS` (varsayılan 15, 1–60), `DWHCODEREVIEW_MSSQL_QUERY_TIMEOUT_SECONDS` (varsayılan 60, 1–300) ve `DWHCODEREVIEW_MSSQL_MAX_CONCURRENCY` (varsayılan 4, 1–16) olarak tanımlanır. `nonprod` Ortamda sunucu, kullanıcı ve parolanın üçü de doluyken izin listesi boşsa, izin listesinde sistem veritabanı (`master`, `tempdb`, `model`, `msdb`) varsa, `ENCRYPT` `true` değilse ya da `TRUST_SERVER_CERTIFICATE` `false` değilse süreç başlangıçta hata verip durur (Decision 5 ve 6). Sunucu, kullanıcı veya paroladan biri boşsa bağlantı "yapılandırılmamış" olur ve süreç başlar; katalog uçları 503 `sql_connection_not_configured` döner (Decision 11). `local`'de de boş bırakılabilir ve durum "yapılandırılmamış" olur.

Requirement 2: Bağlantı dizesi yalnız sunucu tarafındaki tek yardımcıyla `Driver={ODBC Driver 18 for SQL Server}` sürücüsü için üretilir. Kullanıcı, parola ve veritabanı adı süslü parantezle kaçışlanır; `;`, `=`, `{` veya `}` içeren değerler dizeye yeni ayar ekleyemez. Denetim karakteri içeren sunucu adı veya kullanıcı adı 422 ile reddedilir.

Requirement 3: `local` Ortamda `kural-yoneticisi` ayarı `PUT` ile değiştirir; değişiklik aynı süreçteki sonraki SQL Server çağrılarında hemen kullanılır, hiçbir dosyaya veya süreç ortamına yazılmaz. `password` alanı gönderilmezse kayıtlı parola korunur, boş dize gönderilirse silinir. Yanıt parolayı değil yalnız `password_set` bilgisini taşır.

Requirement 4: `local` Ortamda bağlantı testi değerleri kaydetmeden 15 saniyelik giriş süresiyle `master` veritabanına bağlanır ve çevrimiçi veritabanlarını izin listesine göre süzerek döndürür. Formdaki sunucu, port veya kullanıcı kayıtlı değerden farklıysa ve formda parola yoksa kayıtlı parola gönderilmez; test `password_required` sonucuyla biter.

Requirement 5: `nonprod` Ortamda ayar yazma ve bağlantı testi uçları yönlendiriciye eklenmez (istek 404 alır); okuma ucu `editable: false` döndürür ve sunucu ile kullanıcı adını göstermez. Arayüz `editable: false` iken SQL bağlantısı menü öğesini ve sayfasını göstermez; sayfa adresine doğrudan gidilirse "Bu ortamda bağlantı ayarları dağıtımla yönetilir" iletisi görünür.

Requirement 6: Her SQL Server çağrısı olay döngüsü dışında, `DWHCODEREVIEW_MSSQL_MAX_CONCURRENCY` ile sınırlı ayrı iş parçacıklarında koşar. Giriş süresi ve sorgu süresi (sürücünün sorgu zaman aşımı) ayardan uygulanır. Bir katalog sorgusu 5 saniye beklerken sağlık ucu ve başka bir API isteği 200 milisaniyenin altında yanıt verir.

Requirement 7: Veritabanı listesi `sys.databases` içinden `state = 0` olanların izin listesiyle kesişimidir (izin listesi büyük/küçük harf duyarsız karşılaştırılır; `local`'de boşsa bütün çevrimiçi veritabanları). Nesne listesi, Nesne tanımı ve Nesne meta verisi izin listesi dışındaki veritabanı için SQL Server'a gitmeden 403 `database_not_allowed` döner. Nesne meta verisinin çapraz veritabanı çözümü de yalnız izinli veritabanlarında arar; üç parçalı başvuru (`veritabanı.şema.nesne`) yalnız adını taşıdığı veritabanında çözülür, o veritabanı izinli değilse atlanır. Kaynaktaki sınırlar korunur: derinlik 4, 48 Nesne, taranan en fazla 48 veritabanı, 95.000 karakter; Nesne listesi `LIST_OBJECTS_SQL` türlerini ve `q` ile `from_date` süzmesini aynı anlamla uygular.

Requirement 8: Sürücü hataları SQLSTATE koduna (sürücünün hata sınıfını gösteren beş karakterli kod) göre sabit sınıflara eşlenir: `08001`/`08S01` → `sql_server_unreachable`, `28000` → `sql_login_failed`, `HYT00`/`HYT01` → `sql_timeout`, TLS/sertifika hatası → `sql_tls_failed`, diğerleri → `sql_query_failed`. Bağlantı kurulurken dolan giriş süresi (`HYT00`) `sql_server_unreachable` sayılır: ODBC Driver 18 kapalı port ve çözülemeyen sunucu adı için yalnız bu kodu verir; sorgu sırasındaki `HYT00`/`HYT01` `sql_timeout` kalır. Kullanıcıya yalnız sınıf, sabit Türkçe ileti ve istek kimliği (`x-request-id`) döner; ham sürücü metni, sunucu adı, kullanıcı adı veya SQL gösterilmez. Nesne incelemesine giden hata da aynı sınıfı taşır.

Requirement 9: Arayüz SQL bağlantısı sayfası (`local`) sunucu, port, kullanıcı, parola (maskeli; "kayıtlı" bilgisi ve "parolayı kaldır" seçeneğiyle), şifreleme ve sertifikaya güven alanlarını, "Kaydet", "Bağlantıyı test et" ve "Yenile" düğmelerini sunar. Test başarılıysa bulunan veritabanı sayısı ve ilk 8 adı gösterilir. Sayfa metni değerlerin yalnız çalışan sürece uygulandığını ve yeniden başlatmada `.env` değerlerine dönüldüğünü söyler; `backend/.env` dosyasına yazıldığını söyleyen metin kalkar.

## API sözleşmesi

Bütün uçlar `/api/dwhcodereview/v1` altındadır, geçerli oturum ister ve OpenAPI dosyası `specs/openapi/dwhcodereview-api.yaml` ile üretilmiş ön yüz tipleri aynı değişiklikte güncellenir. Hata gövdesi tek hata zarfıdır: `{"detail":{"code":"...","message":"..."}}`; istek kimliği `x-request-id` başlığıyla döner.

| Yöntem ve yol | Rol | İstek özü | Yanıt özü | Hatalar |
|---|---|---|---|---|
| `GET /sql-connection` | `kural-yoneticisi` | — | `environment`, `editable`, `configured`; `local`'de ayrıca `server`, `port`, `user`, `encrypt`, `trust_server_certificate`, `password_set`, `allowed_databases` | 401, 403 |
| `PUT /sql-connection` (yalnız `local`) | `kural-yoneticisi` | kısmi alanlar; `password` yok = koru, `""` = sil | `GET` ile aynı | 404 (`nonprod`), 422 |
| `POST /sql-connection/test` (yalnız `local`) | `kural-yoneticisi` | kısmi alanlar, kaydedilmez | `ok`, `code` (başarısızsa Requirement 8 sınıfı veya `password_required`), `message`, `databases[]` | 404 (`nonprod`), 422; bağlantı hatası 200 + `ok: false` |
`kural-yoneticisi` rolü `inceleyici` yetkilerini de taşır. Veritabanı ve Nesne listeleme uçları [Nesne incelemesi PRD'sinindir](../003-object-review/PRD.md) (o PRD'nin Decision 6); bu PRD onlara Decision 2 portunu, Requirement 7 süzmesini ve Requirement 8 hata sınıflarını verir. Katalog uçlarında bağlantı yapılandırılmamışsa 503 `sql_connection_not_configured`, zaman aşımında 504 `sql_timeout`, diğer Requirement 8 sınıflarında 503 döner. Nesne tanımı ve Nesne meta verisinin HTTP ucu yoktur; yalnız Decision 2 portu üzerinden Nesne incelemesine verilir. Kaynaktaki tanım ucu dışa aktarımda tanımı yeniden çekmek içindi; hedefte dışa aktarım koşumla saklanan metni kullandığı için ([review-history-export](../005-review-history-export/PRD.md)) bu uç yoktur.

## Güvenlik ve yetkilendirme

- Kimlik ve rol [dizin girişi PRD'si](../../../application-foundation/PRDs/001-directory-login/PRD.md) ile gelir; kaynaktaki paylaşılan `X-API-Key` / `X-Admin-Key` başlıkları kaldırılır.
- `nonprod` bağlantısı ortak salt okunur hesapla kurulur; hesap yalnız katalog görünümlerini, `OBJECT_DEFINITION` ve `sys.dm_sql_referenced_entities` için gereken okuma yetkisini taşımalıdır. Hesabın yazma yetkisi olmadığını işletim ekibi doğrular; uygulama bunu kanıtlamaz.
- Hız sınırı IP adresine değil oturumdaki kullanıcıya göre sayılır; sahibi [Nesne incelemesi PRD'sidir](../003-object-review/PRD.md) (Requirement 18). Kaynaktaki IP sınırı `X-Forwarded-For` başlığıyla atlatılabiliyordu.
- Bağlantı testi `local` dışında olmadığı için uygulama, rastgele sunuculara bağlantı denemek (ağ taraması) için kullanılamaz. `local`'de de kayıtlı parola başka sunucuya gönderilmez (Requirement 4).
- Parola, oluşturulan bağlantı dizesi ve sürücü hata metni loga yazılmaz; istisna kaydı sınıf ve SQLSTATE ile sınırlıdır.

## Veri ve geçiş

Bu PRD PostgreSQL'e tablo, şema veya göç eklemez. Port Nesne tanımını yalnız çağıran hizmete verir; incelenen metnin koşumla saklanması [Nesne incelemesi PRD'sinindir](../003-object-review/PRD.md) (Requirement 16). Kaynaktaki `backend/.env` değerleri taşınmaz: yerelde geliştirici kendi `app/backend/.env` dosyasını yeni anahtarlarla doldurur; `nonprod`'da değerler Azure değişkenlerinden gelir. Kaynağın Runtime Secret'taki `MSSQL_CONNECTION_STRING` anahtarı artık okunmaz; Secret'tan kaldırılması, [Kubernetes teslim PRD'sindeki](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) geri alma süresinden sonra işletim ekibinin elle yaptığı adımdır.

## Gözlemlenebilirlik

- Her SQL Server çağrısı için yapılandırılmış JSON log olayı `sql_server.call`: `request_id`, `operation` (`list_databases`, `list_objects`, `fetch_definition`, `dependency_metadata`, `connection_test`), `database`, `outcome` (`ok` veya Requirement 8 sınıfı), varsa `sqlstate`, `duration_ms`, dönen satır sayısı. Sunucu adı, kullanıcı, parola, SQL tanımı ve sürücü metni yazılmaz.
- Ölçümler: `dwhcodereview_sql_server_calls_total{operation,outcome}`, `dwhcodereview_sql_server_call_duration_seconds{operation}` ve bekleyen iş parçacığı sayısı `dwhcodereview_sql_server_inflight`. `operation` yukarıdaki beş işlemden, `outcome` `ok` ile Requirement 8 sınıflarından biridir; veritabanı adı ölçüme girmez.
- İz (trace): her çağrı için içerik taşımayan `sql_server <operation>` aralığı; öznitelikleri işlem ve sonuç sınıfıdır. Ortak kurallar ve saklama süresi [application-foundation alanında](../../../application-foundation/DOMAIN.md) tanımlıdır. Tüketen test: `app/backend/tests/unit/test_sql_server_adapter.py`.
- `local` Ortamda ayar değişikliği `sql_connection.updated` olayıyla değişen alan adlarını (değerleri değil) ve kullanıcıyı yazar.

## Dağıtım etkisi

- **Ayarlar:** Requirement 1 anahtarları `app/backend/.env.example` dosyasına yer tutucuyla, yerel Compose ortam bloğuna ve dağıtıma eklenir (hesap Runtime Secret'a, sır olmayan değerler `helm/dwhcodereview/values-project.yaml`'a); `python3 scripts/check-config-sync.py` geçer.
- **Secret anahtarları:** `helm/dwhcodereview/deploy-hooks.sh`, verilmişse Azure gizli değişkenleri `MSSQL_USER` ve `MSSQL_PASSWORD` değerlerini `dwhcodereview-runtime` Secret'ına `DWHCODEREVIEW_MSSQL_USER` ve `DWHCODEREVIEW_MSSQL_PASSWORD` anahtarlarıyla yazar; verilmemişse kümedeki değeri korur. Değerler komut argümanına, Helm değer dosyasına, betik çıktısına ve Git'e girmez. Sır olmayan sunucu, port ve izin listesi değerlerinin dağıtım yolu [Kubernetes teslim PRD'si](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) sahipliğindedir.
- **İmaj:** Backend imajına Microsoft ODBC sürücüsü `msodbcsql18` (`ACCEPT_EULA=Y` ile) ve `unixodbc` kurulur; Python tarafında `pyodbc` eklenir. Üçü de diğer bağımlılıklar gibi bağımlılık kabul kaydına (`dependency-admission.json`) girer; `msodbcsql18` lisansı (Microsoft EULA) kayıtta sahip tarafından 2026-09-26'da kabul edilmiş olarak yazılır (Decision 4). SQL Server sertifikasını imzalayan kurum kök CA'sı imajın sistem güven deposunda bulunur (Decision 6).
- **Ağ çıkışı:** Backend SQL Server'a yalnız TCP 1433 üzerinden çıkabilir. Kaynaktaki `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` genişliğindeki kural ve 80/443 portları kalkar; adres gelene kadar kural `10.0.0.0/8` TCP 1433'tür ve işletim ekibinin verdiği tek sunucu adresine (`/32`) daraltılır (Decision 9); kural [Kubernetes teslim PRD'sinin](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) Requirement 8'indedir.

## Test stratejisi

- **Birim:** bağlantı dizesi kaçışlama (`;`, `}` ve `=` içeren parola ve kullanıcı adı), Ortam değerine göre uç kaydı (`staging` ve tanınmayan değerde 404), başlangıç doğrulaması (`nonprod`'da şifreleme kapalı, sertifikaya güven açık, izin listesinde sistem veritabanı varken veya tam bağlantıda izin listesi boşken durma; eksik bağlantıda "yapılandırılmamış" olarak başlama), izin listesi süzmesi, SQLSTATE eşleme tablosu, değişen sunucuda kayıtlı parolanın kullanılmaması, parola alanının hiçbir yanıtta ve log kaydında bulunmaması.
- **Uyarlayıcı sözleşmesi:** sahte port ile Nesne listesi süzmesi (`q`, `from_date`) ve Nesne meta verisi sınırları (derinlik, Nesne sayısı, karakter kesme).
- **Olay döngüsü:** 5 saniye bekleyen sahte sürücü çağrısı sürerken sağlık ucunun 200 milisaniyenin altında yanıt verdiği ve eşzamanlı çağrı sayısının `MAX_CONCURRENCY`'yi aşmadığı ölçülür.
- **Tümleşik (`local`):** geliştirici makinesindeki SQL Server Developer sürümüne karşı veritabanı listesi, Nesne listesi, tanım ve meta veri; yanlış parolada `sql_login_failed`, erişilemeyen portta `sql_server_unreachable`.
- **Ön yüz:** Vitest ile `editable: false` iken menü ve sayfanın gizlendiği, test sonucunun ilk 8 veritabanını gösterdiği; tarayıcı testiyle kaydet ve test akışı.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 1, 2, 3, 4, 5, 7 ve 8 birim ve uyarlayıcı testleri geçer; parolanın yanıt, log ve dosya sisteminde bulunmadığı testle sabitlenir; `scripts/check-config-sync.py` ve tam kalite kapısı geçer.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 6 olay döngüsü testi 5 saniyelik SQL Server beklemesi sırasında sağlık ucunun 200 milisaniyenin altında yanıt verdiğini ve eşzamanlılık sınırını doğrular.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Requirement 5 ve 9 ön yüz testleri ile OpenAPI ve üretilmiş tiplerin güncelliği doğrulanır.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: `local` Ortamda yerel PostgreSQL ve geliştirici SQL Server'ı ile tarayıcıdan ayar kaydedilir, bağlantı test edilir, İnceleme sayfasında veritabanı ve Nesne listelenir, bir Nesnenin tanımı port üzerinden okunup incelemeye verilir; `app/backend/.env` dosyasının değişmediği gözlenir (Requirement 3, 4, 7, 9).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: `nonprod` ayarlarıyla yerelde çalışan sürümde yazma ve test uçları 404 döner, arayüzde SQL bağlantısı sayfası görünmez, hesap verilmeden açılan sürümde katalog uçları 503 `sql_connection_not_configured` döner, Runtime Secret'tan gelen salt okunur hesapla izinli veritabanları listelenir ve izin dışı veritabanı 403 alır (Requirement 1, 5, 7). Küme dağıtımı bu kanıtın parçası değildir ve ayrı kullanıcı talimatı ister.

## Kararlar

Decision 4: Microsoft ODBC sürücüsü `msodbcsql18` (Microsoft EULA, kurulumda `ACCEPT_EULA=Y`), `unixodbc` ve `pyodbc` kullanılır. Sahip lisansı 2026-09-26'da kabul etti; üç paket diğer bağımlılıklar gibi `dependency-admission.json` kaydına bu kabulle girer.

Decision 5: `nonprod`'da izinli veritabanı listesi zorunludur (Requirement 1) ve ürün sahibi ile veri ambarı ekibinin belirlediği iş veritabanlarını içerir. Gerekçe: sistem veritabanları (`master`, `tempdb`, `model`, `msdb`) inceleme konusu değildir ve listeye alınmaz; ortak salt okunur hesabın okuduğu ve Nesne meta verisinin çapraz veritabanı taramasının yük oluşturduğu alan bu iş veritabanlarıyla sınırlı kalır. LLM'e gönderilen verinin hassasiyeti izin listesinin gerekçesi değildir ([LLM bağlantısı PRD'si](../006-llm-connection/PRD.md) Decision 8). Bu, kaynaktaki "bütün çevrimiçi veritabanları" davranışından bilinçli bir sapmadır.

Decision 6: `nonprod`'da `Encrypt=yes` ve `TrustServerCertificate=no` zorunludur; SQL Server sertifikasını imzalayan kurum kök CA'sı imajda bulunur. Sunucu sertifikası kurum CA'sıyla imzalı değilse bağlantı kurulmaz; istisna gerekirse sahibi ve bitiş tarihiyle bu PRD'nin revizyonunda kaydedilir.

Decision 7: Windows kimlik doğrulaması (`Trusted_Connection`) kaldırılır. Linux konteynerinde Kerberos kurulumu gerekir ve `nonprod` ortak SQL hesabı kullanır; alan ve arayüz kutusu silinir.

Decision 8: `local`'de arayüzden yapılan değişiklik yeniden başlatmadan sonra korunmaz (Decision 3). Kalıcı değer isteyen geliştirici kendi `.env` dosyasını elle düzenler; uygulama parolayı diske yazmaz.

Decision 9: `nonprod` SQL Server adresini ve IP'sini işletim ekibi tek sunucu olarak verir; ağ çıkış kuralı yalnız o adrese ve yapılandırılan porta açılır. Adres gelene kadar kural `10.0.0.0/8` TCP 1433'tür (proje sahibi, 2026-09-27).

Decision 10: Ortam değeri tek ayar `DWHCODEREVIEW_ENVIRONMENT`'tan okunur: `development` `local`, `staging` `nonprod` demektir; başka ya da okunamayan değer `nonprod` sayılır ([application-foundation alanı](../../../application-foundation/DOMAIN.md)). Ayarın `nonprod` değerini [Kubernetes teslim PRD'si](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) verir; bu PRD yalnız okur.

Decision 11: Proje sahibinin 2026-09-27 kararı: `nonprod` dağıtımı SQL Server hesabını veya adresini beklemez. Sunucu, kullanıcı veya paroladan biri verilmemişse uygulama başlar ve SQL Server alanı "yapılandırılmamış" görünür; üçü de verildiğinde izin listesi ve Decision 5–6 güvenceleri başlangıçta zorunludur.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Ortak hesap:** `nonprod`'da bütün kullanıcılar aynı SQL hesabıyla okur; SQL Server tarafındaki denetim kaydı kişiyi göstermez. Kişi bilgisi yalnız uygulama logundaki `request_id` ve kullanıcıyla eşleştirilebilir.
- **Yük:** Nesne meta verisi tek Nesne için onlarca bağlantı açabilir; eşzamanlılık sınırı düşük tutulmazsa veri ambarında yük oluşur. Bağlantı havuzu bu PRD'nin kapsamı değildir.
- **Sertifika:** `nonprod` SQL Server sertifikası kurum CA'sıyla imzalı değilse veya sunucu adıyla eşleşmiyorsa bağlantı kurulamaz ve Nesne incelemesi durur (Decision 6).
- **Davranış farkı:** İzin listesi ve kaldırılan bağlantı dizesi, kaynakta çalışan bazı yerel kurulumların yeniden yapılandırılmasını gerektirir.
