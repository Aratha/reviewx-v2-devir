---
id: "11-plan-odakli"
title: "Uygulama planını ve görevlerini kabul edilmiş spesifikasyonlardan türet"
scope: process
priority: 20
trigger: always
applies_to: []
gate: "done_report"
---

# Plan odaklı teslimat

Üst düzey `plans/` dizinini henüz kabul edilmiş bir yeteneğe dönüşmemiş karar öncesi keşif,
denetim ve mimari işleri için kullan. Burası ikinci bir gereksinim deposu değildir.

`PRD` kabul edildikten sonra yanına `plan.md` ve `tasks.md` türet. Plan; etkilenen her katmanı, dosya
sınıfını, göç/dağıtım bağımlılığını ve doğrulama komutunu exact `Requirement <n>` veya
`Acceptance <n>` kimliğine geri eşler. Görevler sıralı ve bağımsız doğrulanabilir adımlardır; her görev
çıktısını ve koşum/kanıt makbuzunu adlandırır. Uygulama kararlarını yalnızca sohbette bırakma.

Mevcut kabul edilmiş PRD kapsamındaki küçük uygulama, davranışsız yeniden düzenleme veya mevcut kabul
ölçütüne geri döndüren hata düzeltmesi için yeni plan/PRD ağacı üretme; ilgili mevcut `tasks.md`
görevini ve exact kimlik başvurularını güncelle. Gereksinim veya kabul ölçütü değiştiğinde aynı PRD,
plan ve görevleri revize et ve yeniden insan kabulünü bekle. Ancak bağımsız aktör/sonuç/yetenek,
değişmez veya yeni sözleşme/risk sınırı ayrı yol haritası satırı ve PRD gerektirir.

Keşif aynı yeteneğin gereksinim veya kabul kapsamını değiştirdiğinde önce mevcut `PRD`'yi güncelle.
Yetenek bölündüğünde kendi tamamlanma
tanımı olan ayrı yol haritası satırı ve `PRD` ekle. Sahip bu kararı açıkça vermedikçe ve yol haritasına
kaydetmedikçe sahipsiz işi “ikinci aşama”, “gelecek”, “bayat” veya “kapsam dışı” diye etiketleme.

Tamamlanmış plan sessizce atlanmış görev içermez. `done_report` her eksik görevi veya desteklenmeyen
kanıt seviyesini adlandırmalıdır. Planı ve eksik görevleri kişiye `02-iletisim-tarzi` kuralındaki
sade dil sözleşmesiyle anlat. Üst düzey keşif planı kabul edilmiş spesifikasyonlara alındığında,
gereksinimlerin iki yerde sapmaması için yinelenen içeriği kullanıcının yetkilendirdiği değişiklikle
kaldır veya açıkça işaretle.
