import {Alert} from '@/components/ui/Alert';
import {Button} from '@/components/ui/Button';
import {useReviewSession} from '@/contexts/ReviewSessionContext';
import type {ReviewKind} from '@/types/sqlReview';

/** "Son inceleme …" strip on the review page that started the tab's last review. */
export function LastReviewBanner({kind}: {kind: ReviewKind}) {
  const {session, showResults, showLive, clear} = useReviewSession();
  if (session.kind !== kind || session.phase === 'idle' || session.phase === 'running') return null;
  const completed = session.phase === 'completed';
  return (
    <Alert tone={completed ? 'success' : session.phase === 'cancelled' ? 'info' : 'error'}>
      <div className="row">
        <p className="grow">
          {completed
            ? 'Son inceleme tamamlandı. Ayrıntılar sonuç penceresinde.'
            : `Son inceleme: ${session.errorMessage ?? 'tamamlanamadı.'}`}
        </p>
        {completed ? (
          <Button size="sm" variant="primary" onClick={() => showResults()}>
            Sonuçları aç
          </Button>
        ) : (
          <Button size="sm" onClick={showLive}>
            Canlı pencereyi aç
          </Button>
        )}
        <Button size="sm" variant="danger-outline" onClick={clear}>
          Sonuçları temizle
        </Button>
      </div>
    </Alert>
  );
}
