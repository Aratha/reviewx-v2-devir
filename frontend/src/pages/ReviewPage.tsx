import { useCallback, useEffect, useState } from 'react'
import { PRODUCT_NAME } from '../brand'
import { AccordionSection } from '../components/AccordionSection'
import { ObjectTable } from '../components/ObjectTable'
import { useReviewAnalysis } from '../contexts/ReviewAnalysisContext'
import type { DbObject } from '../services/api'
import { getDatabases, getObjects } from '../services/api'

const SESSION_DB_KEY = 'dwh_review_selected_database'

function readStoredDatabase(): string {
  try {
    if (typeof sessionStorage === 'undefined') return ''
    return sessionStorage.getItem(SESSION_DB_KEY) ?? ''
  } catch {
    return ''
  }
}

function writeStoredDatabase(value: string) {
  try {
    if (typeof sessionStorage === 'undefined') return
    if (value) sessionStorage.setItem(SESSION_DB_KEY, value)
    else sessionStorage.removeItem(SESSION_DB_KEY)
  } catch {
    /* yok say */
  }
}

export function ReviewPage() {
  const {
    reviewing,
    hasReviewOutput,
    openResultsModal,
    startReview,
    invalidateReviewSession,
  } = useReviewAnalysis()

  const [databases, setDatabases] = useState<string[]>([])
  const [dbLoading, setDbLoading] = useState(true)
  const [dbError, setDbError] = useState<string | null>(null)
  const [database, setDatabase] = useState(readStoredDatabase)

  const [objects, setObjects] = useState<DbObject[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  /** YYYY-MM-DD; boşsa tüm nesneler (API filtre yok) */
  const [fromDate, setFromDate] = useState('')
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const loadDatabases = useCallback(async () => {
    setDbLoading(true)
    setDbError(null)
    try {
      const rows = await getDatabases()
      setDatabases(rows)
    } catch (e) {
      setDbError((e as Error).message || 'Veritabanları yüklenemedi')
    } finally {
      setDbLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDatabases()
  }, [loadDatabases])

  useEffect(() => {
    if (!database) {
      setObjects([])
      setSelectedKeys(new Set())
      /* invalidateReviewSession burada ÇAĞRILMAZ: Strict Mode / yeniden mount'ta
         database geçici '' olunca devam eden LLM isteği iptal oluyordu. */
      return
    }
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    getObjects(database, undefined, fromDate.trim() || null)
      .then((rows) => {
        if (!cancelled) setObjects(rows)
      })
      .catch((e: Error) => {
        if (!cancelled) setLoadError(e.message || 'Nesneler yüklenemedi')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [database, fromDate])

  /** Çoklu veritabanı seçiminde satır anahtarı: catalog\x1fşema\x1fad\x1ftür */
  const rowKeyForObject = useCallback(
    (o: DbObject) =>
      `${database}\x1f${o.schema}\x1f${o.name}\x1f${o.type_code}`,
    [database],
  )

  useEffect(() => {
    setSelectedKeys((prev) => {
      const validCurrent = new Set(objects.map(rowKeyForObject))
      const next = new Set<string>()
      for (const k of prev) {
        const keyDb = k.split('\x1f')[0] ?? ''
        if (keyDb === database) {
          if (validCurrent.has(k)) next.add(k)
        } else {
          /* Başka catalog’tan seçim; geçerli liste o DB’ye ait olmadığı için koru */
          next.add(k)
        }
      }
      return next
    })
  }, [objects, rowKeyForObject, database])

  const onDatabaseChange = useCallback(
    (value: string) => {
      setDatabase(value)
      writeStoredDatabase(value)
    },
    [],
  )

  const onToggle = useCallback((key: string, selected: boolean) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (selected) next.add(key)
      else next.delete(key)
      return next
    })
  }, [])

  const onToggleAll = useCallback((keys: string[], selected: boolean) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      for (const k of keys) {
        if (selected) next.add(k)
        else next.delete(k)
      }
      return next
    })
  }, [])

  const onClearTableSelections = useCallback(() => {
    setSelectedKeys(new Set())
  }, [])

  const onReview = useCallback(() => {
    if (selectedKeys.size === 0) return
    const selections = Array.from(selectedKeys).map((k) => {
      const parts = k.split('\x1f')
      const db = parts[0] ?? ''
      const schema = parts[1] ?? ''
      const name = parts[2] ?? ''
      const object_type = parts[3] ?? ''
      return { database: db, schema, name, object_type }
    })
    startReview(selections)
  }, [selectedKeys, startReview])

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <header className="mb-6 shrink-0">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-500">
          {PRODUCT_NAME}
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Veritabanı nesneleri
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Veritabanını seçip nesneleri işaretleyin; başka bir veritabanına
          geçerek seçime eklemeye devam edebilirsiniz (çoklu DB). İnceleme
          sonuçları açılır pencerede gösterilir.
        </p>
      </header>

      <div className="mb-6 max-w-md shrink-0">
        <div className="mb-1 flex items-center justify-between gap-3">
          <label className="block text-xs font-medium text-zinc-600 dark:text-zinc-400">
            Nesne listesi için veritabanı
          </label>
          <button
            type="button"
            onClick={() => void loadDatabases()}
            disabled={dbLoading}
            className="text-xs font-medium text-zinc-600 hover:text-zinc-900 disabled:opacity-50 dark:text-zinc-400 dark:hover:text-zinc-100"
          >
            Listeyi yenile
          </button>
        </div>
        <select
          value={database}
          onChange={(e) => onDatabaseChange(e.target.value)}
          disabled={dbLoading || databases.length === 0}
          className="w-full min-w-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-inset focus:ring-zinc-400 disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-950 dark:focus:ring-zinc-500"
        >
          <option value="">
            {dbLoading ? 'Yükleniyor…' : '— Veritabanı seçin —'}
          </option>
          {databases.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        {dbError && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">
            {dbError}
          </p>
        )}
      </div>

      {!database && !dbLoading && (
        <p className="shrink-0 rounded-lg border border-dashed border-zinc-400 bg-zinc-50 px-4 py-8 text-center text-sm text-zinc-600 dark:border-zinc-600 dark:bg-zinc-900/60 dark:text-zinc-400">
          Nesne listesini görmek için yukarıdan bir veritabanı seçin.
        </p>
      )}

      {database ? (
        <div className="mt-2 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          {hasReviewOutput ? (
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-200/90 bg-gradient-to-r from-emerald-50 to-teal-50/80 px-4 py-3 shadow-sm ring-1 ring-emerald-500/10 dark:border-emerald-800/50 dark:from-emerald-950/40 dark:to-teal-950/30 dark:ring-emerald-400/10">
              <p className="text-sm font-medium text-emerald-950 dark:text-emerald-100/95">
                Son inceleme tamamlandı. Ayrıntılar sonuç penceresinde.
              </p>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={openResultsModal}
                  className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600 dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:focus-visible:outline-emerald-400"
                >
                  Sonuçları aç
                </button>
                <button
                  type="button"
                  onClick={invalidateReviewSession}
                  disabled={reviewing}
                  className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-900 shadow-sm hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-700 dark:bg-rose-950/50 dark:text-rose-100 dark:hover:bg-rose-900/70 dark:focus-visible:outline-rose-500"
                >
                  Sonuçları temizle
                </button>
              </div>
            </div>
          ) : null}

          <AccordionSection
            id="accordion-objects"
            hideHeading
            title="Nesne seçimi"
            fillHeight
          >
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <ObjectTable
                embedded
                objects={objects}
                loading={loading}
                selectedKeys={selectedKeys}
                getRowKey={rowKeyForObject}
                onToggle={onToggle}
                onToggleAll={onToggleAll}
                onClearSelection={onClearTableSelections}
                onReview={onReview}
                reviewing={reviewing}
                fromDate={fromDate}
                onFromDateChange={setFromDate}
              />
            </div>
            {loadError ? (
              <div className="shrink-0 border-t border-zinc-200 px-4 py-3 text-sm text-red-800 dark:border-zinc-700 dark:text-red-300">
                {loadError}
              </div>
            ) : null}
          </AccordionSection>
        </div>
      ) : null}
    </div>
  )
}
