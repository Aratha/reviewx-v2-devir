---
id: "30-frontend-yapisi"
title: "Ön yüzü sıkı tipli tek sayfalı uygulama olarak tut"
scope: frontend
priority: 30
trigger: path-match
applies_to:
  - "app/frontend/**"
gate: "frontend-test.yml"
application_modes:
  - separated-web
---

# Ön yüz yapısı

Varsayılan ön yüz, `FastAPI` arka ucundan ayrılmış, `Vite` ile derlenen `React` tek sayfalı
uygulamasıdır. Sunucu tarafında oluşturma ve `Next.js` yasaktır. Sunucu çatısı yönlendirmesi veya ikinci
API katmanı ekleme. Bağlantı, gezinme, konum, gecikmeli rota yükleme ve bulunamadı davranışı için
yapılandırılmış istemci yönlendiricisini kullan.

Bağımlılıklar aşağı doğru akar:

`pages -> components -> services -> lib`

- Sayfalar rota ve veri yönlendirmesini birleştirir.
- Bileşenler yeniden kullanılabilir sunum ve etkileşimin sahibidir; temel bileşenler `components/ui/`
  altındadır.
- Hizmetler tipli API çağrılarının sahibidir.
- `lib`; paylaşılan istemci, depolama, yapılandırma, biçimlendirme ve saf yardımcıların sahibidir.
- Bağlamlar rotalar arası oturum ve yerel ayar durumunu sağlar; kancalar yeniden kullanılabilir
  etkileşim mantığı içerir.

Sayfalar doğrudan `fetch` çağırmaz ve bileşenler arka uç uygulama modüllerini içe aktarmaz. `any`
olmadan sıkı `TypeScript` kullan; API tiplerini üretilmiş sözleşmeden türet. Özelliklerin katmanlar
boyunca aktarılması veya her şeyi kapsayan genel durum yerine işlevsel bileşen, bileşim, yerel konu için
yerel durum ve küçük özel kancaları tercih et.

`PascalCase` bileşen dosyaları ve `<Capability>Page.tsx` rota sayfaları kullan. İlk ana sayfa yüzeyi proje
amacını ve birincil alanı gösterebilir; ancak kabul edilmiş `PRD`'si ve uygulaması olmayan iş eylemi
sunmamalıdır.

Rota modüllerini ve gerçekten ağır bileşenleri gecikmeli yükle. Sonuç ezberlemeyi (`memoization`)
varsayılan tören olarak değil,
yalnız ölçülmüş pahalı iş veya kararlı bağlam değeri için ekle.

Tek uçtan uca arayüz istisnası, kabul edilmiş `PRD`'si tüm arayüzü istem girdisi, sohbet yanıtı ve
konuşma geçmişiyle sınırlayan `Streamlit` uygulamasıdır. Bu istisnayı form, gösterge panosu, yönetim veya
genel amaçlı iş arayüzü için kullanma ve `Streamlit`'i `React`/`FastAPI` ağacına karıştırma. Böyle bir
iş `technology-profile.yml` içindeki ayrı `chat-only-fullstack` kipinden başlar. `Chainlit` ve diğer
uçtan uca arayüz çatıları taban bağımlılıkları değildir.
