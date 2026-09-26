---
id: "01-mimari-ilkeleri"
title: "Sınırlı bağlamları ve içe doğru bağımlılık yönünü koru"
scope: governance
priority: 10
trigger: always
applies_to: []
gate: "review"
---

# Mimari ilkeleri

İş davranışını sınırlı bağlama göre düzenle ve kabul edilmiş bir `PRD`'den türetilen dikey
dilim olarak teslim et. Bağımlılıklar içe doğru yönelir:

`api -> services -> infrastructure/repositories -> domain`

- `api`; taşıma, kimlik doğrulama bağımlılıkları, doğrulama ve yanıt eşlemesinin sahibidir.
- `services`; iş değişmezleri, kiracı kapsamı, yetkilendirmeyi gözeten yönlendirme ve işlem
  sınırlarının sahibidir.
- `infrastructure/repositories`; kalıcılık sorguları ve dış uyarlayıcıların sahibidir.
- `domain`; modellerin ve alan tiplerinin sahibidir; taşıma veya altyapı katmanından içe aktarma yapmaz.
- `core`, `db` ve ara yazılım, katmanları kesen bileşenlerdir; API veya hizmet modüllerini içe
  aktarmamalıdır.

Taşıma sınırında bağımlılık enjeksiyonu kullan. Uç nokta işleyicisi içinde depo, ayarlar,
oturum veya dış istemci oluşturma. Kalıtım veya genel durum yerine bileşimi, küçük ve uyumlu
modülleri ve açık, tipli sözleşmeleri tercih et.

Hizmetler yalnızca `HTTP` sözleşmeleri üzerinden iletişim kurar. Bir hizmet başka bir hizmetin
veritabanını okuyamaz, veritabanı bağlantısı oluşturamaz veya sınırlı bağlamlar arasında birleştirme
yapamaz. Sınırlar arası referanslar değerdir ve sahibi olan hizmet üzerinden doğrulanır. Kabul edilmiş
bir `PRD` başka bir yürütme modelini açıkça getirmedikçe arka plan işi, zamanlanmış veya istek üzerine
çalışan modüldür.

Motora özgü davranış, seçilen kalıcılık uyarlayıcısı ve depo sınırında kalır. Kimlik doğrulama
yetkisi uygulama seviyesindedir: `super_admin` uygulama izin kontrollerini atlar; ancak hiçbir zaman
işletim sisteminin kök kullanıcısı, veritabanı süper kullanıcısı veya küme yöneticisi olmaz.

Spekülatif soyutlamaları ve yer tutucu alanları reddet. Ortak bir soyutlamayı yalnızca en az iki
gerçek tüketici aynı kararlı sözleşmeyi gösterdikten sonra ekle.
