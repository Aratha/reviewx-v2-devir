import { lazy, Suspense, useState } from 'react'
import { LiveReviewModal } from './components/LiveReviewModal'
import { ReviewResultsModal } from './components/ReviewResultsModal'
import { Sidebar, type AppView } from './components/Sidebar'
import { ReviewAnalysisProvider } from './contexts/ReviewAnalysisContext'

const ReviewPage = lazy(() =>
  import('./pages/ReviewPage').then((m) => ({ default: m.ReviewPage })),
)
const ScriptReviewPage = lazy(() =>
  import('./pages/ScriptReviewPage').then((m) => ({
    default: m.ScriptReviewPage,
  })),
)
const RulesPage = lazy(() =>
  import('./pages/RulesPage').then((m) => ({ default: m.RulesPage })),
)
const LlmConfigPage = lazy(() =>
  import('./pages/LlmConfigPage').then((m) => ({ default: m.LlmConfigPage })),
)
const SqlConfigPage = lazy(() =>
  import('./pages/SqlConfigPage').then((m) => ({ default: m.SqlConfigPage })),
)
const AnalysisHistoryPage = lazy(() =>
  import('./pages/AnalysisHistoryPage').then((m) => ({
    default: m.AnalysisHistoryPage,
  })),
)

function ViewFallback() {
  return (
    <div
      className="flex min-h-[40vh] flex-1 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50/80 text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900/40 dark:text-zinc-400"
      role="status"
      aria-live="polite"
    >
      Yükleniyor…
    </div>
  )
}

function ActiveView({ view }: { view: AppView }) {
  return (
    <Suspense fallback={<ViewFallback />}>
      {view === 'review' ? (
        <ReviewPage />
      ) : view === 'paste' ? (
        <ScriptReviewPage />
      ) : view === 'rules' ? (
        <RulesPage />
      ) : view === 'llm' ? (
        <LlmConfigPage />
      ) : view === 'sql' ? (
        <SqlConfigPage />
      ) : (
        <AnalysisHistoryPage />
      )}
    </Suspense>
  )
}

function App() {
  const [view, setView] = useState<AppView>('review')

  return (
    <ReviewAnalysisProvider>
      <LiveReviewModal />
      <ReviewResultsModal />
      <div className="flex h-dvh min-h-0">
        <Sidebar active={view} onNavigate={setView} />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col p-6 lg:p-10">
          <ActiveView view={view} />
        </main>
      </div>
    </ReviewAnalysisProvider>
  )
}

export default App
