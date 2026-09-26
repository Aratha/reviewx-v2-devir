# Belirtimler

İş geliştirme alan öncelikli ve belirtim güdümlü yürür.

1. Sınırlı bağlamı `specs/<domain>/DOMAIN.md` içinde tanımla.
2. Yalnız yeni bağımsız aktör/sonuç/yetenek veya sözleşme-risk sınırı için `kt-iskelet
   spesifikasyon` ile tek iş yetkinliği oluştur.
3. PRD'yi incele ve `Status: Accepted` yap.
4. `plan.md`, ardından `tasks.md` türet.
5. Bu PRD yolundan şema, arka uç, ön yüz ve tarayıcı kanıtını üretip uygula.

Teslim sırası Belirtim → Plan → Görevler → Uygulama biçimindedir. Yalnız kaynak adı kod yetkisi vermez.

Mevcut `Status: Accepted` PRD kapsamındaki yazım/kopya/stil düzeltmesi, davranışı değiştirmeyen
yeniden düzenleme veya mevcut kabul ölçütüne geri döndüren hata düzeltmesi yeni PRD istemez. Mevcut
PRD yolu ile exact `Requirement <n>`/`Acceptance <n>` kimliklerini ilgili `tasks.md` görevi ve
koşum/kanıt makbuzunda kullanın. Gereksinim veya kabul ölçütü aynı aktör/sonuç içinde değişiyorsa aynı
PRD'yi revize edip yeniden insan kabulüne sunun; yeni risk/sözleşme sınırında yeni yol haritası satırı
ve PRD açın. Satır veya dosya sayısı bu kararı değiştirmez.
