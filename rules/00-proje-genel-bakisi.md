---
id: "00-proje-genel-bakisi"
title: "Çözümlenmiş proje amacını ve profilleri depo bağlamı olarak kullan"
scope: governance
priority: 0
trigger: always
applies_to: []
gate: "governance-drift.yml"
---

# Proje bağlamı

Bu depo, üretilmiş ve alan öncelikli tek depodur. Önce `technology-profile.yml` dosyasını oku: izin
verilen uygulama kiplerini, sabit teknolojileri, istisnaları ve yasak alternatifleri belirleyen,
makinece okunabilir yetkili kaynaktır. Projenin kipi `.kt-scaffold/answers.yml#application_mode`
alanındadır; aynı dosya proje amacını, birincil alanı, ürün kısa adını (`slug`) ve isteğe bağlı
yetenekleri taşır. Sabit yığını veya kipi tercih edilen başka bir çatıyla değiştirme.

- `separated-web` kipinde yığın `React`/`Vite` ön yüzü, `Python`/`FastAPI` arka ucu ve
  `SQLAlchemy`/`Alembic` kalıcılığıdır; yalnız sohbet amaçlı `Streamlit` istisnası profilde tanımlıdır.
  API ön eki, kiracı başlığı ve yerel ayarlar da yanıtlardadır; kalıcılığı değiştirmeden önce
  `schema/profile.yml` dosyasını oku. İskelet yalnız platform tabanını içerir: sağlık denetimi, oturum
  açma, `JWT` erişim belirteci, `/me`, kiracı bağlamı, rol tabanlı erişim denetimi, uygulama
  seviyesinde `super_admin`, `OpenAPI` dışa aktarımı, üretilmiş istemci tipleri, yerelleştirilmiş
  oturum açma/ana sayfa yüzeyleri, testler ve kimlik doğrulama tarayıcı senaryosu.
- `desktop` kipinde uygulama `Python` ve `Tkinter` ile kullanıcının bilgisayarında çalışan bir
  penceredir; iskelet boş bir pencere, pencereden ayrı bir mantık modülü, kullanıcı veri dizini
  yardımcısı ve testleri içerir. Kipin kuralı masaüstü yapısı kuralıdır.

İki kipte de iskelet bilerek hiçbir yer tutucu iş varlığı içermez. İş davranışı `specs/<domain>/`
altında başlar:

- `DOMAIN.md` sınırlı bağlamı, aktörleri, dili, değişmezleri ve sınırları tanımlar.
- `roadmap.md` alanı bağımsız teslim edilebilir yeteneklere ayırır.
- `PRDs/<nnn>-<capability>/PRD.md` bir iş dikeyi için kabul edilmiş kaynaktır.

Tamamlanma katmanlar arası bir iş birimi olduğu için depo, kipin gerektirdiği bütün katmanları
birlikte tutar. Ürüne özgü söz varlığını kabul edilmiş alan spesifikasyonlarında ve onların
yetkilendirdiği kodda tut; genel platform tabanına veya bu külliyata asla ekleme.

Bağlama duyarlı çalışmayı, değişiklik notlarında proje kipini ve sabit teknoloji profilini
belirterek ve ilgili kalite kapısını çalıştırarak doğrula.
