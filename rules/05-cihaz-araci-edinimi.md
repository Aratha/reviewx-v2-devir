---
id: "05-cihaz-araci-edinimi"
title: "Eksik cihaz aracını önce kurumsal uygulama kataloğundan edindir"
scope: governance
authority: mandatory
priority: 50
trigger: always
applies_to: []
gate: "review"
---

# Cihaz aracı edinimi

Geliştirici cihazları kurumca yönetilir. `Docker`, `Python`, `Node.js` ve `Git` gibi cihaz
düzeyindeki uygulama ve çalışma zamanları Jamf veya başka bir MDM (kurumsal cihaz yönetimi) aracıyla
dağıtılır ve kurumsal uygulama kataloğunda (macOS'ta Jamf `Self Service`) kuruluma hazır bekler.
İş böyle bir araç gerektiriyorsa önce aracın kurulu olduğunu ve teknoloji profilinin istediği
sürümü karşıladığını `docker --version` gibi salt okunur bir sürüm sorgusuyla doğrula.

Araç eksikse veya sürümü uymuyorsa kullanıcıdan aracı kurumsal uygulama kataloğundan kurmasını iste;
aracın adını ve gereken sürümü belirt. Kullanıcı kurulumu bildirdikten sonra aynı salt okunur
sorguyla yeniden doğrula. Araç kurulu fakat çalışmıyorsa, örneğin `Docker Desktop` açık değilse,
kullanıcıdan uygulamayı başlatmasını iste; bu yeni kurulum değildir.

Cihaz aracını kataloğu atlayarak kurma: `brew`, `curl | sh`, üretici sitesinden indirilen kurulum
paketi, `sudo` ile sistem dizinine yazma veya genel paket yöneticisiyle küresel kurulum kullanma.
Katalog dışından eşdeğer bir alternatif, örneğin `Docker` yerine `Colima` veya `Podman`, önerme ya
da kurma. Araç katalogda yoksa dur, eksik önkoşulu bildir ve kullanıcıyı kurumsal BT talep kanalına
yönlendir; araç gerektiren adımı tamamlanmış sayma.

Bu kural yalnız cihaz düzeyindeki araçları kapsar. Proje `.venv` ortamı ve proje bağımlılıkları kendi
sabitlenmiş kaynaklarından gelir; sürümlerinin ilerleyişi `54-bagimlilik-guncelligi` kuralına aittir.
