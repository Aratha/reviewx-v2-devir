---
id: "31-frontend-api-butunlesmesi"
title: "Yalnız kaydedilmiş OpenAPI sözleşmesini paylaşılan istemci üzerinden tüket"
scope: frontend
authority: mandatory
priority: 40
trigger: path-match
applies_to:
  - "app/frontend/src/services/**"
  - "app/frontend/src/lib/apiClient.*"
  - "app/frontend/src/types/api.d.ts"
  - "specs/openapi/**"
gate: "type-drift"
application_modes:
  - separated-web
---

# Ön yüz API entegrasyonu

Sözleşme işlem hattı sıralı ve çevrimdışıdır:

1. arka uç `OpenAPI` belgesini dışa aktar;
2. belgeyi karşılaştır ve `commit` et;
3. kaydedilmiş belgeden `src/types/api.d.ts` dosyasını yeniden üret;
4. üretilmiş tipleri karşılaştır ve `commit` et.

Gelişigüzel çalışan sunucudan asla üretme ve kaydedilmiş sözleşmede bulunan istek/yanıt tipini elle
yineleme. Yeni dikeyin tek geçişli üretiminde sayfa üreticisi, arka uç `OpenAPI` dışa aktarımı
oluşmadan önce hizmet yanında aynı en küçük yanıt projeksiyonunu çıkarabilir; zorunlu dışa
aktarma/tip sapması kapısı bu projeksiyonu kabul eder. Üretilmiş sözleşme tipi oluşunca ondan takma
ad/projeksiyon türetmeyi tercih et. `src/services/` altındaki tek alan hizmeti, odaklı ön yüz işlemlerini
sunar. Sayfalar ve bileşenler ham `fetch` yerine hizmeti çağırır.

Tüm istekler paylaşılan istemci üzerinden geçer. Aynı kökenli `URL` çözümleme, `JSON` başlığı, taşıyıcı
erişim belirteci, yapılandırılmış kiracı başlığı, gerektiğinde istek tanımlayıcısı, yanıt ayrıştırma ve
tipli hata zarfı onun sorumluluğundadır. Kayıtları dışarıdan `public_id` ile adresle; iç sayısal kimliği
asla gönderme.

Yerel oturumu yalnız yanıt, eşleşen `WWW-Authenticate` istemi gibi uygulamanın kendi taşıyıcı kimlik
bilgisinin süresinin dolduğunu veya geçersiz olduğunu kanıtladığında sonlandır. Yukarı akış hatasında,
vekil hatasında, ilgisiz `401`, `5xx`, zaman aşımı veya ayrıştırma hatasında oturumu kapatma.

Hizmet çağrıları arayüze tipli yükleme, boş, başarılı, doğrulama, yasak, bulunamadı ve beklenmeyen
hata davranışı sunar. Uygulama ayrıntısı içerebilecek ham arka uç iletisini gösterme; kararlı hata
kodlarını yerelleştirilmiş iletilere eşle ve yapılandırılmış günlükleme için tanı bağlamını koru.
