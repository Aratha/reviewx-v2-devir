# Kalıcılık

`schema/profile.yml`, sabit yetkiyi ve geçiş uyarlayıcısını kaydeder. Tek depolama motoru
PostgreSQL'dir; hedef durumun sahibi SQLAlchemy modelleri, geçiş geçmişinin sahibi Alembic'tir.

PGVector yalnız aynı PostgreSQL veritabanı içinde kabul edilmiş PRD yetkinliği olarak kullanılabilir.
Platform imajı kabul edilmiş eklenti çalıştırılabilir dosyasını sağlar ve incelenmiş Alembic geçişi,
SQL eklentisi `vector` değerini etkinleştirir; uygulama başlangıcı bunu asla kurmaz veya etkinleştirmez.
Gömme üretimi uygulama portu ve onaylı altyapı uyarlayıcısı arkasında kalır. Veri, kiracı, model
sürümü ve getirim sözleşmesi için `rules/46-vektor-gomme-siniri.md`
dosyasına bakın.

~~~sh
scripts/db.sh generate <migration-name>
scripts/db.sh apply
scripts/db.sh status
scripts/db.sh validate
~~~

Şema otoritesini değiştirmek yerine geçişi elle yazma. Üretilen geçişleri
uygulamadan önce incele.
