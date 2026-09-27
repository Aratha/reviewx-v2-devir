# SQLAlchemy/Alembic profili

`app/backend/app/domain/models/` altındaki SQLAlchemy modelleri şema otoritesidir. Yalnız bu modelleri
değiştirdikten sonra revizyon üret:

```sh
cd app/backend
alembic revision --autogenerate -m "describe_change"
alembic upgrade head
alembic check
```

Üretilen her revizyonu uygulamadan önce oku. Alembic aday geçiş üretir; veri taşıma, yeniden adlandırma
ve yıkıcı değişiklikler yine açık inceleme gerektirir. `Base.metadata.create_all` değerini dağıtım
mekanizması olarak asla kullanma.
