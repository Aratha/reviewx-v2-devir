import { useCallback, useEffect, useState } from 'react'

import { PRODUCT_NAME } from '../brand'
import type { SqlConfig, SqlConfigPatch, SqlConfigTestPatch } from '../services/api'
import { getSqlConfig, postSqlConfigTest, putSqlConfig } from '../services/api'

const inputClass =
  'w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500 dark:focus:border-zinc-500 dark:focus:ring-zinc-500'

export function SqlConfigPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedOk, setSavedOk] = useState(false)
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [testOk, setTestOk] = useState<boolean | null>(null)
  const [testDatabases, setTestDatabases] = useState<string[]>([])

  const [mssql_server, setMssqlServer] = useState('')
  const [mssql_port, setMssqlPort] = useState(1433)
  const [mssql_user, setMssqlUser] = useState('')
  const [mssql_trusted_connection, setMssqlTrustedConnection] = useState(false)
  const [mssql_encrypt, setMssqlEncrypt] = useState(true)
  const [mssql_trust_server_certificate, setMssqlTrustServerCertificate] = useState(true)

  const [password_set, setPasswordSet] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [removePassword, setRemovePassword] = useState(false)

  const currentPatch = useCallback(
    (): SqlConfigTestPatch => ({
      mssql_server: mssql_server.trim(),
      mssql_port,
      mssql_user: mssql_user.trim(),
      mssql_trusted_connection,
      mssql_encrypt,
      mssql_trust_server_certificate,
      ...(removePassword
        ? { mssql_password: '' }
        : newPassword.trim()
          ? { mssql_password: newPassword.trim() }
          : {}),
    }),
    [
      mssql_server,
      mssql_port,
      mssql_user,
      mssql_trusted_connection,
      mssql_encrypt,
      mssql_trust_server_certificate,
      newPassword,
      removePassword,
    ],
  )

  const applyConfig = useCallback((c: SqlConfig) => {
    setMssqlServer(c.mssql_server)
    setMssqlPort(c.mssql_port)
    setMssqlUser(c.mssql_user)
    setMssqlTrustedConnection(c.mssql_trusted_connection)
    setMssqlEncrypt(c.mssql_encrypt)
    setMssqlTrustServerCertificate(c.mssql_trust_server_certificate)
    setPasswordSet(c.password_set)
    setNewPassword('')
    setRemovePassword(false)
  }, [])

  const load = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      const c = await getSqlConfig()
      applyConfig(c)
    } catch (e) {
      setError((e as Error).message || 'Ayarlar yüklenemedi')
    } finally {
      setLoading(false)
    }
  }, [applyConfig])

  useEffect(() => {
    void load()
  }, [load])

  const onSave = async () => {
    setSaving(true)
    setError(null)
    setSavedOk(false)
    try {
      const patch: SqlConfigPatch = {
        mssql_server: mssql_server.trim(),
        mssql_port,
        mssql_user: mssql_user.trim(),
        mssql_trusted_connection,
        mssql_encrypt,
        mssql_trust_server_certificate,
      }
      if (removePassword) {
        patch.mssql_password = ''
      } else if (newPassword.trim()) {
        patch.mssql_password = newPassword.trim()
      }
      const next = await putSqlConfig(patch)
      applyConfig(next)
      setSavedOk(true)
      window.setTimeout(() => setSavedOk(false), 4000)
    } catch (e) {
      setError((e as Error).message || 'Kayıt başarısız')
    } finally {
      setSaving(false)
    }
  }

  const onTest = async () => {
    setTesting(true)
    setError(null)
    setTestMessage(null)
    setTestOk(null)
    setTestDatabases([])
    try {
      const result = await postSqlConfigTest(currentPatch())
      setTestOk(result.ok)
      setTestMessage(result.message)
      setTestDatabases(result.databases ?? [])
    } catch (e) {
      setTestOk(false)
      setTestMessage((e as Error).message || 'Bağlantı testi başarısız')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="shrink-0">
        <h1 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
          {PRODUCT_NAME} — SQL bağlantısı
        </h1>
        <p className="mt-1 max-w-2xl text-xs text-zinc-500 dark:text-zinc-400">
          PASIFIK, ATLAS veya başka bir SQL Server&apos;a bağlanın. Sunucu adını değiştirdiğinizde
          İnceleme sayfasındaki veritabanı listesi güncellenir. Değerler{' '}
          <code className="rounded bg-zinc-200/80 px-1 py-0.5 text-[11px] text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
            backend/.env
          </code>{' '}
          dosyasına yazılır.
        </p>
      </header>

      {error && (
        <div
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          {error}
        </div>
      )}

      {savedOk && (
        <div
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-100"
          role="status"
        >
          SQL ayarları kaydedildi.
        </div>
      )}

      {testMessage && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            testOk
              ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-100'
              : 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200'
          }`}
          role="status"
        >
          {testMessage}
          {testOk && testDatabases.length > 0 ? (
            <p className="mt-2 text-xs opacity-90">
              Örnek veritabanları: {testDatabases.slice(0, 8).join(', ')}
              {testDatabases.length > 8 ? '…' : ''}
            </p>
          ) : null}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Yükleniyor…</p>
      ) : (
        <div className="max-w-xl space-y-4">
          <div>
            <label htmlFor="mssql-server" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              SQL sunucu adı
            </label>
            <input
              id="mssql-server"
              type="text"
              value={mssql_server}
              onChange={(e) => setMssqlServer(e.target.value)}
              placeholder="PASIFIK, ATLAS, host.docker.internal"
              autoComplete="off"
              spellCheck={false}
              className={inputClass}
            />
          </div>

          <div>
            <label htmlFor="mssql-port" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Port
            </label>
            <input
              id="mssql-port"
              type="number"
              min={1}
              max={65535}
              value={mssql_port}
              onChange={(e) => setMssqlPort(Number(e.target.value) || 1433)}
              className={inputClass}
            />
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <input
              id="mssql-trusted"
              type="checkbox"
              checked={mssql_trusted_connection}
              onChange={(e) => setMssqlTrustedConnection(e.target.checked)}
              className="rounded border-zinc-400 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800"
            />
            <label htmlFor="mssql-trusted" className="text-sm text-zinc-700 dark:text-zinc-300">
              Windows kimlik doğrulaması (Trusted Connection)
            </label>
          </div>

          {!mssql_trusted_connection ? (
            <>
              <div>
                <label htmlFor="mssql-user" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  Kullanıcı adı
                </label>
                <input
                  id="mssql-user"
                  type="text"
                  value={mssql_user}
                  onChange={(e) => setMssqlUser(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  className={inputClass}
                />
              </div>

              <div>
                <label htmlFor="mssql-password" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  Şifre
                </label>
                <input
                  id="mssql-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => {
                    setNewPassword(e.target.value)
                    if (e.target.value) setRemovePassword(false)
                  }}
                  placeholder={password_set ? 'Yeni şifre yazın veya aşağıdan kaldırın' : 'SQL login parolası'}
                  autoComplete="off"
                  className={inputClass}
                />
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  {password_set ? (
                    <span className="text-xs text-zinc-600 dark:text-zinc-400">Kayıtlı şifre var.</span>
                  ) : (
                    <span className="text-xs text-zinc-500">Kayıtlı şifre yok.</span>
                  )}
                  <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
                    <input
                      type="checkbox"
                      checked={removePassword}
                      onChange={(e) => {
                        setRemovePassword(e.target.checked)
                        if (e.target.checked) setNewPassword('')
                      }}
                      className="rounded border-zinc-400 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800"
                    />
                    Kayıtlı şifreyi sil
                  </label>
                </div>
              </div>
            </>
          ) : null}

          <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <input
              id="mssql-encrypt"
              type="checkbox"
              checked={mssql_encrypt}
              onChange={(e) => setMssqlEncrypt(e.target.checked)}
              className="rounded border-zinc-400 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800"
            />
            <label htmlFor="mssql-encrypt" className="text-sm text-zinc-700 dark:text-zinc-300">
              Encrypt=yes
            </label>
          </div>

          <div className="flex items-center gap-3 rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900/50">
            <input
              id="mssql-trust-cert"
              type="checkbox"
              checked={mssql_trust_server_certificate}
              onChange={(e) => setMssqlTrustServerCertificate(e.target.checked)}
              className="rounded border-zinc-400 text-zinc-900 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800"
            />
            <label htmlFor="mssql-trust-cert" className="text-sm text-zinc-700 dark:text-zinc-300">
              TrustServerCertificate=yes
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="button"
              onClick={() => void onTest()}
              disabled={testing || saving}
              className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              {testing ? 'Test ediliyor…' : 'Bağlantıyı test et'}
            </button>
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving || testing}
              className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
            >
              {saving ? 'Kaydediliyor…' : 'Kaydet'}
            </button>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading || saving || testing}
              className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              Yenile
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
