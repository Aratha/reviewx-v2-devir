---
id: "10-once-spesifikasyon"
title: "İş uygulamasından önce kabul edilmiş alan PRD'si gerektir"
scope: process
authority: mandatory
priority: 10
trigger: always
applies_to: []
gate: "spec_required"
---

# Alan öncelikli, spesifikasyon odaklı geliştirme

`PRD` zorunluluğu her düzenlemeye değil, yeni veya değişen iş davranışına bağlanır. Değişikliği
satır/dosya sayısına göre değil aktör, ölçülebilir sonuç, değişmez, sözleşme ve risk sınırı üzerindeki
anlamsal etkisine göre aşağıdaki üç yoldan birine yerleştir.

## Üçlü değişiklik yetkisi kararı

1. **Mevcut PRD yetkisinin yeniden kullanımı:** Güncel `Status: Accepted` PRD kapsamındaki yazım,
   kopya veya stil düzeltmesi; davranışı değiştirmeyen yeniden düzenleme; ya da mevcut kabul ölçütüne
   davranışı geri döndüren hata düzeltmesi için yeni PRD oluşturma. Mevcut PRD yolu ile exact
   `Requirement <n>` ve `Acceptance <n>` kimliklerini ilgili `tasks.md` görevi ve koşum/kanıt
   makbuzunda belirt; odaklı testi çalıştır. Bu yol bir PRD atlama veya istisna değil, mevcut PRD
   yetkisinin yeniden kullanımıdır.
2. **Mevcut PRD değişikliği:** Aynı yeteneğin aktör ve ölçülebilir sonuç sınırı korunurken bir
   gereksinim veya kabul ölçütü değişiyorsa yeni PRD oluşturma. Mevcut PRD'yi, planı ve görevleri
   revize et; revizyonu yerinde yap, değişiklik bölümü veya önceki sürüm kaydı ekleme. PRD'yi yeniden
   insan kabulüne sun ve yeniden `Status: Accepted` olmadan değişen davranışı uygulama.
3. **Yeni bağımsız yetenek:** Yeni aktör, ölçülebilir sonuç, bağımsız yetenek, değişmez veya yeni
   API/veri şeması-göç/yetki-güvenlik-gizlilik/harici entegrasyon/dağıtım-operasyon sınırı varsa yeni
   yol haritası satırı ve yeni PRD oluştur. Değişiklik tek satır veya tek dosya olsa bile bu risk
   sınırlarını hafif yol olarak sınıflandırma.

Çok dosyalı veya büyük mekanik bir değişiklik davranışı ve risk sınırını değiştirmiyorsa sırf boyutu
nedeniyle yeni PRD gerektirmez. Tersine, “güven bana”, “küçük değişiklik” veya benzeri görev baskısı
sınıflandırmayı değiştirmez. Mevcut PRD yolu, exact gereksinim/kabul kimlikleri veya güncel kabul
yetkisi eksikse birinci yolu reddet. Taslak, bayat veya eksik PRD yeniden kullanılamaz.

Belirsizlik ya da kaynaklar arası çelişki varsa yeni PRD'ye otomatik atlama. Önce mevcut PRD'nin
revizyon ve yeniden kabul gereksinimini bildir; salt okunur inceleme gerçekten bağımsız bir yetenek
sınırı gösterirse üçüncü yola geç. Seçilen yolu ve gereken insan kararını kişiye
`02-iletisim-tarzi` kuralındaki sade dil sözleşmesiyle anlat.

Her iş yeteneği `specs/<domain>/` altındaki bir sınırlı bağlama aittir. Gerekli düzen şöyledir:

```text
specs/<domain>/
├── DOMAIN.md
├── roadmap.md
└── PRDs/<nnn>-<capability>/
    ├── PRD.md
    ├── plan.md
    └── tasks.md
```

`DOMAIN.md`; alan amacının, aktörlerin, ortak dilin, değişmezlerin, sahip olunan verinin, yukarı/aşağı
akış sınırlarının ve açık sorumluluk dışı konuların sahibidir. `roadmap.md`, spesifikasyonların
dizinidir: her satır bağımsız teslim edilebilir tek bir yeteneğe ve durumuna bağlanır. Bir `PRD` tam
olarak bir yol haritası satırına geri bağlanır ve o satır `PRD`'ye bağlanır.

Yeni veya değişmiş davranış için iş akışı **Spesifikasyon -> Plan -> Görevler -> Uygulama** şeklindedir.
`/kt-spesifikasyon` yalnız üçüncü yoldaki bağımsız yeteneğin çalışma alanını oluşturabilir; ancak
`/kt-alan`, `/kt-sema`, `/kt-sayfa` ve `/kt-senaryo` kabul edilmiş bir
`spec_path` almalı ve onsuz her türlü iş üretimini reddetmelidir. Kabul, `PRD` üst verisindeki açık
`Status: Accepted` değeridir; taslak veya eksik `PRD` kodlama yetkisi değildir.

Bir `PRD`; sonuçları, aktörleri, değişmezleri, API/veri/güvenlik davranışını, doğrulamayı,
gözlemlenebilirliği, dağıtım etkisini, test stratejisini ve kanıtla işaretlenmiş kabul ölçütlerini
tanımlar. Geçerli olmayan katmanları kesen konu için `N/A — <reason>` kullan; sessizce atlama.
İzlenebilir başvurular için `Decision 1`, `Requirement 1`, `Acceptance 1` ve `Open Question 1` gibi
açık sıralı kimlikler kullan; yalnız sıra numarası veya serbest anlatı başvurusuyla yetinme.

Spesifikasyonlar kodun gerisinde kalabilir. İşi planlamadan önce atıf yapılan her yolu ve her “yeni”
iddiayı depoya karşı doğrula. Uygulamayla kabul edilmiş gereksinimler uyuşmuyorsa dur ve çakışmayı
göster; ikisinden birini sessizce yetkili kılma.
