---
id: "40-kalicilik-kaynagi"
title: "Tek şema yetkisinin sahibi SQLAlchemy ve Alembic olsun"
scope: schema
authority: mandatory
priority: 40
trigger: path-match
applies_to:
  - "schema/**"
  - "app/backend/**/domain/**"
  - "app/backend/**/migrations/**"
  - "specs/**/PRDs/**"
gate: "schema-check.yml"
application_modes:
  - separated-web
---

# Profil sahipli kalıcılık

`PostgreSQL` tek depolama motorudur. `technology-profile.yml`, `.kt-scaffold/answers.yml` ve
`schema/profile.yml`, `sqlalchemy-alembic` değerini tek kalıcılık yetkisi olarak sabitler: hedeflenen
durumun sahibi `SQLAlchemy` üst verisi/modelleridir; göçleri `Alembic` üretir. Başka `ORM`, göç aracı
veya şema yetkisi `PRD` ya da ajan tercihiyle seçilemez.

Şema değişikliği kabul edilmiş `spec_path` gerektirir. `scripts/db.sh` üzerinden tek iş akışı izle:

1. Kaydedilmiş yetkiyi değiştir.
2. `scripts/db.sh generate <descriptive_name>` çalıştır.
3. Üretilmiş göçü oku; silme, tip dönüşümü, varsayılan, dizin, kısıt, kilit/geçmiş veri doldurma
   riskini ve veri kaybı durumlarını incele.
4. Yalnız yerel veritabanına `scripts/db.sh apply` ile uygula.
5. `scripts/db.sh validate` ve `scripts/db.sh status` çalıştır.
6. Yetkiyi ve yalnız eklenen göç geçmişini birlikte `commit` et.

Yetkinin ifade edemediği veri taşıma için özel göçe izin verilir; ancak elle yazılmış şema göçü varsayılan
değildir ve eşleşen yetki değişikliği yine zorunludur. Çalışma zamanı süreci şema oluşturmaz veya
değiştirmez. Dağıtım ortamı, geliştirici makinesi yerine ayrılmış göç sürümü üzerinden uygular.

Yıkıcı komut, istekte birebir yıkıcı eylem ve yerel dahil her ortamda tam etkilenen kapsam denetimi
gerektirir. Şema/geçmiş sapması profil kapısını başarısız kılar.
