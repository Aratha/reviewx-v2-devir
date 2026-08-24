import { memo, useCallback } from 'react'
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../brand'
import { useReviewAnalysis } from '../contexts/ReviewAnalysisContext'

export type AppView = 'review' | 'paste' | 'rules' | 'llm' | 'sql' | 'logs'

type NavLinkProps = {
  id: AppView
  label: string
  isOn: boolean
  onSelect: (id: AppView) => void
  pulse?: boolean
  tooltip?: string
}

const NavLink = memo(function NavLink({
  id,
  label,
  isOn,
  onSelect,
  pulse,
  tooltip,
}: NavLinkProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left font-medium transition ${
        isOn
          ? 'bg-zinc-200/90 text-zinc-950 ring-1 ring-zinc-300/80 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-zinc-600'
          : 'text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-800/90 dark:hover:text-zinc-100'
      }`}
    >
      <span>{label}</span>
      {pulse ? (
        <span
          className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-amber-500"
          title={tooltip}
          aria-label={tooltip ?? 'İnceleme çalışıyor'}
        />
      ) : null}
    </button>
  )
})

type SidebarNavProps = {
  active: AppView
  onNavigate: (view: AppView) => void
  dbReviewing: boolean
  scriptReviewing: boolean
  dbTooltip?: string
  scriptTooltip?: string
}

const SidebarNav = memo(function SidebarNav({
  active,
  onNavigate,
  dbReviewing,
  scriptReviewing,
  dbTooltip,
  scriptTooltip,
}: SidebarNavProps) {
  const onSelect = useCallback(
    (id: AppView) => {
      onNavigate(id)
    },
    [onNavigate],
  )

  const sectionClass =
    'mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-500'

  return (
    <nav className="flex flex-col gap-3 text-sm" aria-label="Ana menü">
      <div>
        <p className={sectionClass}>Kullanıcı</p>
        <div className="flex flex-col gap-1">
          <NavLink
            id="review"
            label="İnceleme"
            isOn={active === 'review'}
            onSelect={onSelect}
            pulse={dbReviewing}
            tooltip={dbTooltip}
          />
          <NavLink
            id="paste"
            label="SQL yapıştır"
            isOn={active === 'paste'}
            onSelect={onSelect}
            pulse={scriptReviewing}
            tooltip={scriptTooltip}
          />
          <NavLink
            id="logs"
            label="Analiz geçmişi"
            isOn={active === 'logs'}
            onSelect={onSelect}
          />
        </div>
      </div>
      <div>
        <p className={sectionClass}>Sistem</p>
        <div className="flex flex-col gap-1">
          <NavLink
            id="rules"
            label="Kurallar"
            isOn={active === 'rules'}
            onSelect={onSelect}
          />
          <NavLink
            id="llm"
            label="LLM ayarları"
            isOn={active === 'llm'}
            onSelect={onSelect}
          />
          <NavLink
            id="sql"
            label="SQL ayarları"
            isOn={active === 'sql'}
            onSelect={onSelect}
          />
        </div>
      </div>
    </nav>
  )
})

export function Sidebar({
  active,
  onNavigate,
}: {
  active: AppView
  onNavigate: (view: AppView) => void
}) {
  const { reviewing, activeReviewSummary } = useReviewAnalysis()
  const dbReviewing =
    reviewing && activeReviewSummary?.kind === 'db'
  const scriptReviewing =
    reviewing && activeReviewSummary?.kind === 'script'

  const dbTooltip =
    dbReviewing && activeReviewSummary?.kind === 'db'
      ? `${activeReviewSummary.database}: ${activeReviewSummary.targets.slice(0, 3).join(', ')}${activeReviewSummary.targets.length > 3 ? '…' : ''}`
      : dbReviewing
        ? 'İnceleme sürüyor'
        : undefined

  const scriptTooltip =
    scriptReviewing && activeReviewSummary?.kind === 'script'
      ? activeReviewSummary.label
      : scriptReviewing
        ? 'SQL incelemesi sürüyor'
        : undefined

  return (
    <aside className="flex min-h-0 w-56 shrink-0 flex-col overflow-y-auto border-r border-zinc-300 bg-white px-4 py-6 shadow-[2px_0_8px_-2px_rgba(0,0,0,0.06)] dark:border-zinc-700 dark:bg-zinc-900 dark:shadow-[2px_0_12px_-4px_rgba(0,0,0,0.45)]">
      <div className="mb-8">
        <h1 className="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
          {PRODUCT_NAME}
        </h1>
        <p className="mt-1 text-xs leading-snug text-zinc-600 dark:text-zinc-400">
          {PRODUCT_TAGLINE}
        </p>
      </div>
      <SidebarNav
        active={active}
        onNavigate={onNavigate}
        dbReviewing={dbReviewing}
        scriptReviewing={scriptReviewing}
        dbTooltip={dbTooltip}
        scriptTooltip={scriptTooltip}
      />
    </aside>
  )
}
