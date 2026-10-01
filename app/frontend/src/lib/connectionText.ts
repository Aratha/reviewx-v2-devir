/** Shared wording of the SQL Server and LLM connection pages. */
export const MANAGED_BY_DEPLOYMENT = 'Bu ortamda bağlantı ayarları dağıtımla yönetilir.';
export const SQL_MANAGED_BY_SUPER_ADMIN = 'Bu ortamda SQL bağlantısını yalnız uygulama yöneticisi düzenleyebilir.';
export const SQL_STORED_IN_APPLICATION =
  'Değerler uygulamanın veritabanına kaydedilir; parola şifrelenerek saklanır ve bir daha gösterilmez. Kaydettiğiniz bağlantı, uygulama yeniden başlatılmadan kullanılır.';
export const SQL_ENCRYPTION_FIXED = 'Bu ortamda bağlantı her zaman şifrelidir; bu ayar değiştirilemez.';
export const SQL_ALL_DATABASES =
  'Nesne incelemesi ekranında bu hesabın erişebildiği bütün veritabanları listelenir; sistem veritabanları (master, tempdb, model, msdb) listelenmez. Neyin okunabileceğini hesabın SQL Server yetkileri belirler.';
export const SQL_CERTIFICATE_NOT_VERIFIED =
  'Bağlantı yine şifrelidir, ancak sunucunun kimliği doğrulanmaz; ağdaki biri kendini bu sunucu gibi gösterebilir. Bu seçeneği yalnız sunucunun sertifikası kurumun sertifika otoritesiyle imzalı değilse açın ve sunucuya kurum imzalı sertifika kurulunca kapatın.';
export const RUNTIME_ONLY =
  'Değerler yalnız çalışan sunucu sürecine uygulanır; hiçbir dosyaya yazılmaz. Uygulama yeniden başlayınca .env dosyasındaki değerlere dönülür.';
