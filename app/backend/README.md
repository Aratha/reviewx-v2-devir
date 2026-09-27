# dwhcodereview Python arka ucu

Bu profil sağlayıcıdan bağımsız FastAPI platform temel çizgisidir. Kiracı bağlamı, JWT oturum açma,
`/auth/me`, RBAC koruması, uygulama düzeyi `super_admin`, PostgreSQL hazır olma, Alembic ve OpenAPI
dışa aktarımı içerir. Bilinçli olarak iş varlığı içermez.

İlk CLI, yerel MCP veya çevrimdışı `paketi-uygula` oluşturması, iskelet kökünde profile uygun
Python 3.13 ile `.venv` ve pip hazırlar. HTTP MCP akışında bu hazırlığı yerel kodlama istemcisi,
prompt kancası ayarları gelmeden önce yapar; `.venv` makbuzu olmadan kurulum tamamlanmaz. Makinede
güvenilen Python 3.13 yoksa açık hata bildirilir; Python indirilmez veya sistem politikası
değiştirilmez. Uygulama bağımlılıkları otomatik kurulmaz ve çağıran terminal otomatik
etkinleştirilmez.

Hazırlığın tek komutu iskelet kökünde çalışır; `.venv` eksikken prompt kancasının durdurduğu
oturumu da bu komut açar:

```sh
python3.13 .kt-scaffold/hooks/python_environment.py hazirla
```

Windows'ta `py -3.13 .kt-scaffold/hooks/python_environment.py hazirla` kullanın. Komut yalnız eksik
ortamı oluşturur; var olan ortamı önce doğrular, üzerine yazmaz ve bozuk ya da kısmi ortamı silmez.
`dogrula` yalnız doğrular.

Ortam hazırlığı başarılıysa, POSIX terminalinde iskelet kökünden:

```sh
. .venv/bin/activate
pip install -r app/backend/requirements.txt -r app/backend/requirements-dev.txt
cp app/backend/.env.example app/backend/.env
export DWHCODEREVIEW_JWT_PRIVATE_KEY="$(sh scripts/dev-secrets.sh jwt-private-key)"
cd app/backend
alembic upgrade head
python -m app.scripts.create_super_admin
uvicorn app.main:app --reload
```

`DWHCODEREVIEW_DATABASE_URL` zorunludur ve varsayılanı yoktur. Yerel Compose yığınının PostgreSQL
servisi ana makineye port yayımlamaz; bu yüzden ana makinede çalıştırmadan önce `app/backend/.env`
içindeki adresi makineden erişebildiğiniz bir PostgreSQL'e yöneltin ve yer tutucu parolayı kendi
yerel parolanızla değiştirin. Compose içindeki arka uç ise bu adresi `scripts/stack.sh` üzerinden,
`scripts/dev-secrets.sh` ile üretilen yerel parolayla alır.

Windows PowerShell etkinleştirme yolu `.\.venv\Scripts\Activate.ps1`, komut istemi yolu
`.venv\Scripts\activate.bat` olur. Kurum politikası etkinleştirmeyi engelliyorsa politikayı
gevşetmeyin; doğrudan `.venv\Scripts\python.exe -m pip` gibi ortam yorumlayıcısını kullanın.
POSIX'te de `.venv/bin/python -m pip` etkinleştirme gerektirmez.

Doğrulama, gerçek yorumlayıcının Python 3.13.x sürümünü, nihai `.venv` yolundaki `sys.prefix`
değerini, farklı `sys.base_prefix` değerini, `include-system-site-packages=false` ayarını ve pip
erişimini kapsar. İskelet güncellemesi mevcut ortamı korur; eksik ortam oluşturmaz. `.venv` yerel çalışma zamanı çıktısıdır, güvenlik sandbox'ı değildir.

Oturum açma, `/api/dwhcodereview/v1/auth/login` adresinde JSON `{ "username": "...", "password": "..." }`
kullanır. Dönen bearer belirteciyle `x-tenant-id` üstbilgisini `/api/dwhcodereview/v1/auth/me` adresine
gönderin. Oturum açma yanıtı, ana kiracının genel tanımlayıcısını içerir.

Erişim belirteci `rules/58` kurumsal profiline göre asimetrik imzalanır: varsayılan `ES256` (P-256),
seçenek olarak en az 2048 bit anahtarla `RS256`. `DWHCODEREVIEW_JWT_PRIVATE_KEY` şifresiz PEM özel
anahtarı taşır; doğrulama bu anahtarın açık anahtarıyla, yalnız seçilen algoritmayla yapılır. Anahtar
her süreçte zorunludur; yoksa ya da algoritmayla uyuşmuyorsa uygulama açılmaz. Yerel yığın ve ana
makine çalıştırması `scripts/dev-secrets.sh` ile Git'in yok saydığı `app/infra/.data/` altında
oluşturulan tek kullanımlık geliştirme anahtarını kullanır. Dağıtılmış ortamın anahtarı yalnız
`backend.existingSecret` ile adı verilen `Secret` içinden gelir. Üretim dışı test kümesinde bu
`Secret`'ı projenin `helm/dwhcodereview/deploy-hooks.sh` kancası hazırlar (anahtarı bir kez üretir,
sonra kümedekini kullanır). Üretim ortamında anahtarın üretimi, dönüşümü ve iptali kurum anahtar
yönetimine ve insan onayına aittir.

Parola politikası `app/core/security.py` içindedir: yalnız parolayla girilen bu akışta en az 15, en
çok 128 karakter; büyük/küçük harf, rakam veya özel karakter zorunluluğu yoktur, boşluk ve Unicode
karakterler olduğu gibi korunur. Çok kullanılan parolalar, `aaaa…` ya da `abcabc…` gibi tekrarlar ve
kullanıcı adını içeren parolalar reddedilir. Olmayan kullanıcı için de bir parola doğrulaması yapılır;
yanıt süresi kullanıcı adının var olup olmadığını ele vermez.

Aynı kullanıcı adıyla aynı adresten 15 dakikada 5 hatalı girişten sonra oturum açma `429` ve
`Retry-After` döner; başarılı giriş sayacı sıfırlar (`app/core/login_throttle.py`). Sayaç her süreçte
ayrıdır ve ters vekil arkasında vekilin adresini görür; birden çok kopya için ortak sınır giriş
katmanında (ingress/WAF) kurulur ve bu bir işletim kararıdır.

Yararlı kontroller:

```sh
black --check app tests
isort --check-only app tests
mypy app
pytest
alembic check
python -m app.scripts.export_openapi
```

PostgreSQL entegrasyon testleri yalnız `RUN_POSTGRES_INTEGRATION=1` iken çalışır;
`DWHCODEREVIEW_DATABASE_URL` değerini adı `_test` ile biten tek kullanımlık veritabanına yöneltin.

## İsteğe bağlı LangChain

`technology-profile.yml#llm_orchestration`, LangChain'i tek LLM orkestrasyon çatısı olarak yalnız
kabul edilmiş bir PRD ile açar. `requirements-llm.in` kabul edilmiş `langchain`, `langchain-core` ve
`langgraph` sürümlerini sabitler; `requirements-llm.txt` bu kümeyle birlikte uygulamanın kabul
edilmiş kilididir. Varsayılan kurulumda LangChain yoktur.

Kabul edilmiş PRD'den sonra etkinleştirmek için `requirements.in` sonuna `-r requirements-llm.in`
satırını ekleyin, `scripts/compile-dependency-locks.sh` ile kilitleri yeniden üretin,
`dependency-admission.json` kaydını güncelleyin ve kapıları çalıştırın. Uygulama kilidi LangChain
kilidindeki sürümleri korur; LangChain'in bağımlılığı nedeniyle websockets 16.x serisine iner.

`langchain-community`, `langsmith` ve `langgraph-sdk` hiçbir bağımlılık girdisinde doğrudan
bildirilmez. Ücretli LangSmith ve LangGraph servisleri kullanılmaz: `LANGSMITH_*`/`LANGCHAIN_*`
anahtar, uç nokta veya izleme değişkeni ya da `LANGGRAPH_API_KEY` tanımlıysa uygulama açılışta
durur. Her sağlayıcı paketi (`langchain-openai`, `langchain-ollama` gibi) kendi kabul edilmiş PRD'sini
ve bağımlılık kabulünü ister; model kurum içi veya yerinde çalışan onaylı bir sağlayıcıdan gelir ve
LangChain bir uygulama portunun arkasında kalır.

## Kontrollü kapsayıcı derlemeleri

`Dockerfile.dev`, `PYTHON_BASE_IMAGE` kabul eder; banka iş hatları bunu değişmez özet içeren onaylı iç
kayıt deposu imajına ayarlamalıdır. Kimlik bilgisi ve kayıt deposu yapılandırması BuildKit `pip_conf`
gizli bilgisinde bulunur; derleme argümanında veya imaj katmanında asla bulunmaz. Varsayılan
`connected` bağımlılık kipi onaylı bağlı yapıt üretim altyapısını destekler:

```sh
docker buildx build --load \
  --build-arg PYTHON_BASE_IMAGE='<internal-registry>/platform/python:3.13-alpine3.23@sha256:<digest>' \
  --secret id=pip_conf,src=/approved/build-secrets/pip.conf \
  -f app/backend/Dockerfile.dev .
```

Kapalı ağ derlemesi için önce sağlanan paketin `SHA256SUMS` dosyasını doğrulayın, temel imajları içe
aktarıp terfi ettirin ve profilin wheel deposunu adlandırılmış derleme bağlamı olarak verin:

```sh
docker buildx build --load --network=none \
  --build-arg PYTHON_BASE_IMAGE='<internal-registry>/platform/python:3.13-alpine3.23@sha256:<digest>' \
  --build-arg DEPENDENCY_MODE=offline \
  --build-context python_wheelhouse=/approved/bundle/wheelhouse/python-fastapi \
  -f app/backend/Dockerfile.dev .
```

Çevrimdışı kip `pip --no-index` zorlar ve bütün pip yapılandırma dosyalarını yok sayar; eksik wheel
paketi başka kayıt deposuna erişmek yerine derlemeyi başarısız kılar. Süreç varsayılan UID/GID `10001` ile
çalışır; kontrollü geliştirici imajları bağlama sahipliğini `APP_UID` ve `APP_GID` ile eşleyebilir.
