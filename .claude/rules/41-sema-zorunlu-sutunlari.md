<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - schema/**
  - app/backend/**/domain/**
---

# Alan tablolarına tek zorunlu yaşam döngüsü ve denetim yapısı uygula

# Zorunlu tablo yapısı

Zorunlu bloğu `SQLAlchemy` profilinde paylaşılan karışım veya temel tip olarak bir kez kodla. Her alana
biraz farklı sürüm kopyalama. Veritabanının yetkiyle uyumunu yalnız kaynak metin değil, göç ettirilmiş
şema testleri kanıtlar.

Geçerli her alan tablosu şunları taşır:

| Öğe | Sözleşme |
|---|---|
| İç kimlik | `<table>_id`, veritabanınca üretilir, API üzerinden asla sunulmaz |
| Genel kimlik | Dışarıdan adreslenebilir kaynak için boş olmayan ve benzersiz `public_id` metni |
| Taşma alanı | Varsayılanı boş nesne olan, boş olmayan yerel ikili `JSON` `props` |
| Denetim | `created_at`, `updated_at`, `created_by`, `updated_by` |
| Yazılımsal silme | `is_deleted`, `deleted_at`, `deleted_by` |
| Etkin arama | `is_deleted` değeri `false` olan satırlarla sınırlı kısmi dizin |
| Zaman | `UTC` saklanan/karşılaştırılan, saat dilimini gözeten zaman damgası; yalın değer reddedilir |
| Anlam | Tablo açıklamasıyla önemli sıralı değer, bağlantı ve taşma alanı anahtarı açıklamaları |

Birleşim, eşlem, yerel ayar yan tablosu ve yalnız eklenen akış; kimliği zaten sağlayan kararlı
doğal/bileşik anahtar kullanır; anlamsız `public_id` ekleme. Bloğun kalanından sapma kabul edilmiş `PRD`'de
belirtilmeli ve sessizce getirilmek yerine göç ettirilmiş şema kapısı tarafından doğrulanmalıdır.

Hizmetler bayrak, zaman damgası ve aktörü birlikte ayarlayarak yazılımsal silme yapar. Varsayılan okuma
silinmiş satırları dışlar; açık denetim/kurtarma yolu dahil edebilir. Kaydedilmiş profil güncelleme zaman
damgalarının sahibiyse `updated_at` tetikleyicisini uygulama.

Şema yetkisini, üretilmiş göçü, kalıcılık tipini ve API serileştirmesini aynı değişiklikte uyumlu tut.
