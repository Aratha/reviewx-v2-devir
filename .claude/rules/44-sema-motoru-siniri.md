<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - schema/**
  - app/backend/**
---

# PostgreSQL davranışını uyarlayıcılar ve depolarla sınırla

# Motor ve profil sınırı

Üretilmiş depo tek sabit kalıcılık profiline sahiptir: eşzamanlı olmayan `SQLAlchemy` ve `Alembic` ile
`PostgreSQL`. `PostgreSQL` ve göç aracı bilgisini `schema/`, profil uyarlayıcısı/veritabanı modülü ve
depo uygulamalarında tut. API katmanı ile uygulama/hizmet ve alan politikası kodu, profilden bağımsız
arayüz ve tip kullanır.

Genel tanımlayıcı, saat dilimini gözeten zaman damgası, yerel `JSON`, işlem yalıtımı, kısıt hatası
çevirisi ve bağlantı/oturum oluşturma eşlemelerini merkezileştir. Ham motor tipini, sürücü içe aktarımını,
lehçeye özgü `SQL`'i veya göç aracı komutlarını iş hizmetlerine dağıtma.

Ham `SQL` yalnız depo/uyarlayıcı sınırında veya incelenmiş göçte izinlidir, parametreli olmalı ve açık
olmayan gözcü/sıralı değer için adlandırılmış sabit kullanmalıdır. Çalışma zamanı kodu `DDL` çalıştırmaz.
Hizmetler veritabanları arası sorgu veya veritabanı bağlantısı çıkarmaz.

Başka `ORM`, göç sistemi, kalıcılık motoru veya çalışma zamanında seçilebilir uyarlayıcı yasaktır.
Önbellek uyarlayıcısı ancak tam kabul edilmiş yeteneğin parçası olarak eklenir; boş profil vaadi
değildir. Sabit profil tek kalite kapısı üzerinden proje iskeleti oluşturur, göç ettirir/test eder,
sözleşmeyi dışa aktarır ve sapmayı doğrular.
