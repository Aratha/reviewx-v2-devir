<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - app/backend/**
---

# Arka uç alanlarını sabit Python/FastAPI yığını ve temiz katmanları kullanarak uygula

# Arka uç yapısı

Arka uç kodunu değiştirmeden önce `technology-profile.yml` ve `.kt-scaffold/answers.yml` dosyalarını
oku. Tek arka uç yığını `Python 3.13`, `FastAPI`, `Pydantic`, eşzamanlı olmayan `SQLAlchemy`/`asyncpg`,
`Alembic` ve `pytest` oluşturur. `Node.js`, `NestJS`, `Prisma`, başka bir `Python` web çatısı ve elle
yazılmış yerel `Python` `HTTP` yığı desteklenmez. Bunları `PRD` veya ajan tercihiyle getirme.
Bağımlılıklar şu yönü korur:

`api -> application/services -> infrastructure/repositories -> domain`

- `HTTP` paketleri `app/api/<domain>/` altında bulunur; bağımlılık sağlayıcıları uç noktalarının
  yanında kalır.
- İş mantığı `app/services/`, kalıcılık sorguları `app/infrastructure/repositories/`, istek/yanıt
  modelleri `app/schemas/`, şema yetkisi modelleri `app/domain/models/`
  altında bulunur.
- Girdi/çıktı için `Annotated[..., Depends(...)]`, eşzamanlı olmayan oturum, `async def` ve `await` kullan.
- Her `Python` paketi `__init__.py` içerir. `ORM` kullanan her işçi veya betik, kayıt defterinin tam
  olması için ilk model işleminden önce `app.db.base` modülünü içe aktarır.

Hizmetler kiracı kapsamını uygular ve genel tanımlayıcıları o kiracı içinde çözümler. Uç nokta kodu
kalıcılığı doğrudan sorgulamaz. Yapılandırma, önbellek, gözlemlenebilirlik, istek bağlamı, kimlik
doğrulama ve veritabanı uyarlayıcıları katmanları kesen modüllerdir; iş API'si paketine bağımlı
olmamalıdır.

Alan paketi yalnız kabul edilmiş bir `spec_path` üzerinden eklenebilir ve testleri onunla birlikte
üretilir veya yazılır. Gelecekteki yapıya yer ayırmak için boş alan, yer tutucu denetleyici veya genel
`CRUD` modülü oluşturma.

`SSE` uç noktalarına, `LLM` belirteci teslimi gibi tek yönlü sunucu akışı için izin verilir. Bunlar
`FastAPI` uç noktası olarak kalır; akış başlamadan önce aynı `JWT`/`RBAC` ve kiracı kontrollerini
uygulamalı, bağlantı koptuktan sonra işi durdurmalı ve `URL` içine kimlik bilgisi veya hassas içerik
koymamalıdır.
