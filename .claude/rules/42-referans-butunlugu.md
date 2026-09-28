<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - schema/**
  - app/backend/**/domain/**
  - app/backend/**/infrastructure/**
  - app/backend/**/services/**
---

# Hizmet içinde fiziksel bütünlüğü, sınırlar arasında değer referansını uygula

# Referans bütünlüğü

İki kayıt aynı hizmete ve `PostgreSQL` veritabanına aitse varsayılan olarak fiziksel dış anahtar kullan.
Şema yetkisiyle üretilmiş göç; referans verilen sütun, boş olabilirlik, benzersizlik, güncelleme/silme
eylemi ve destekleyici dizinlerde anlaşmalıdır. Yazılımsal silmeyle kısıtlayıcı eylemi tercih et;
kabul edilmiş gereksinim ve veri hacmi incelemesi olmadan yıkıcı basamaklama getirme.

Hizmet, bağımsız sahipli sınırlı bağlam veya veritabanı sınırı boyunca fiziksel dış anahtar oluşturmaz.
Diğer tarafın genel tanımlayıcısını değer olarak taşı, sahibini belgele ve iş işlemi sınırında sahip
hizmet üzerinden doğrula. Bu kontrolü veritabanları arası sorgu, veritabanı bağlantısı veya çoğaltılmış
gölge tabloyla asla değiştirme.

Her referans için:

- hedefin kanonik tipini ve açık `<target>_id` veya `<target>_public_id` adını kullan;
- alan birleştirme, arama veya kiracı süzgecine katılıyorsa dizin ekle;
- ilişkiyi ve sahipliği profile özgü şema üst verisinde veya incelenmiş göçte belirt;
- oluşturma/güncelleme hatasını, yazılımsal silinmiş üst kayıt davranışını ve eşzamanlı değişikliği
  testlerde kapsa;
- bir kiracı diğer kiracının satırına bağlanamasın diye arama/benzersizlik kurallarına kiracı kapsamı ekle.

Uygulama `super_admin`'i yalnız yetkilendirmeyi atlar; referans bütünlüğünü veya kiracıyla nitelenmiş
veri değişmezlerini atlamaz.
