<!-- kt-scaffold tarafından ÜRETİLDİ. rules/ dizinini düzenleyip yeniden üretin. -->
---
paths:
  - app/backend/**
  - schema/**
---

# FastAPI arka uç sözleşmelerini gerçek sınırlarda pytest ile test et

# Arka uç testleri

`pytest` ve sabit `Python`/`FastAPI` profilinin kaydettiği komutları kullan; yerel ve sürekli tümleştirme
davranışı uyumlu kalsın diye bunları `scripts/quality-gate.sh` üzerinden çağır. Testler uygulama yapısını
yansıtır: API, hizmetler/uygulama, alan, altyapı/depolar, çekirdek, ara yazılım, işçi, tümleştirme
ve paylaşılan test verileri.

Güven açısından kritik davranış için gerçek sınırları tercih et:

- gerçek `PostgreSQL` test veritabanını `Alembic` ile göç ettir;
- yönlendirme, doğrulama, `JWT`, `RBAC`, kiracı bağlamı ve hata zarfı için gerçek `HTTP` uygulamasını
  çalıştır;
- sözleşme testleri için gerçek serileştirme ve üretilmiş `OpenAPI` kullan;
- işçi giriş noktalarını gerçek kayıt defteri/başlatma bağlantılarıyla test et.

Birim testleri iş kurallarını yalıtır. Sınır sahteleri imza kısıtlı olmalı ve yanıt/hata yapısı üretici
sözleşmesinden gelmelidir. Önemli anahtar sözcük bağımsız değişkenlerini ve yasak alanları doğrula.
Yalnız “çağrıldı” kaydeden yalın sahte, doğru yönlendirme kanıtı değildir.

Her davranış; başarılı yol, bozuk girdi, uygunsa kimliği doğrulanmamış/yasak yol, kiracı yalıtımı,
bulunamadı/çakışma davranışı, tekrarlandığında aynı sonucu veren yeniden deneme, işlem geri alma
ve yazılımsal silme görünürlüğünü kapsar. Gerileme düzeltmesi, düzeltme olmadan başarısız olan
testi içerir.

Test verisi kimlik bilgileri ve başlatma parolaları kaydedilmiş dosyadan değil test süreci ortamından
gelir. Test verilerini belirlenimci tut ve genel sınırlar üzerinden temizle. Kapsama yüzdeleri tanı
amaçlıdır; sayıyı yönlendirmek yerine kritik değişmezlere ve test edilmemiş dallara öncelik ver.
