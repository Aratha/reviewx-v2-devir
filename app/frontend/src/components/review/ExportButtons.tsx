import {useState} from 'react';
import {Alert} from '@/components/ui/Alert';
import {Button} from '@/components/ui/Button';
import {saveFile} from '@/lib/download';
import {describeError} from '@/lib/errorMessages';
import {ReviewService, type ExportFormat} from '@/services/reviews';

/**
 * CSV and fix-commented SQL downloads produced by the server from the stored run
 * (sql-review review-history-export Requirement 7–10). The SQL button is disabled when the run
 * has no stored SQL text.
 */
export function ExportButtons({
  runId,
  sqlAvailable,
  size = 'md',
}: {
  runId: string;
  sqlAvailable: boolean;
  size?: 'md' | 'sm';
}) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(format: ExportFormat) {
    setBusy(format);
    setError(null);
    try {
      const file = await ReviewService.exportRun(runId, format);
      saveFile(file.blob, file.filename);
    } catch (reason) {
      setError(describeError(reason));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <div className="row" role="group" aria-label="Dışa aktar">
        <Button size={size} onClick={() => void download('csv')} disabled={busy !== null} busy={busy === 'csv'}>
          CSV indir
        </Button>
        <Button
          size={size}
          onClick={() => void download('sql')}
          disabled={busy !== null || !sqlAvailable}
          busy={busy === 'sql'}
          title={sqlAvailable ? undefined : 'Bu inceleme için saklanmış SQL metni yok.'}
        >
          SQL indir
        </Button>
      </div>
      {!sqlAvailable && <p className="subtle">SQL indirme kapalı: bu inceleme için saklanmış SQL metni yok.</p>}
      {error && <Alert tone="error">{error}</Alert>}
    </div>
  );
}
