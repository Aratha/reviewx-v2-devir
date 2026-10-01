import {useState} from 'react';
import {LastReviewBanner} from '@/components/review/LastReviewBanner';
import {ObjectTable} from '@/components/review/ObjectTable';
import {Alert} from '@/components/ui/Alert';
import {Button} from '@/components/ui/Button';
import {Card} from '@/components/ui/Card';
import {PageHeader} from '@/components/ui/PageHeader';
import {Pager} from '@/components/ui/Pager';
import {EmptyState, ErrorState, LoadingState} from '@/components/ui/States';
import {useReviewSession} from '@/contexts/ReviewSessionContext';
import {useDebouncedValue} from '@/hooks/useDebouncedValue';
import {useResource} from '@/hooks/useResource';
import {describeError} from '@/lib/errorMessages';
import {
  MAX_SELECTION,
  OBJECT_TYPES,
  databaseCount,
  toggleAll,
  toggleSelection,
  type SelectionMap,
} from '@/lib/objectSelection';
import {CatalogService} from '@/services/catalog';

const PAGE_SIZE = 100;

/**
 * Object review (sql-review object-review Requirement 1–3): pick a database, filter its objects on
 * the server, collect up to 50 objects from one or more databases and start the review.
 */
export default function ObjectReviewPage() {
  const {session, startObjectReview} = useReviewSession();
  const [database, setDatabase] = useState('');
  const [text, setText] = useState('');
  const [type, setType] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [page, setPage] = useState(1);
  const [selection, setSelection] = useState<SelectionMap>({});
  const query = useDebouncedValue(text.trim(), 300);
  const databases = useResource('databases', (signal) => CatalogService.databases(signal));
  const objectsKey = database ? JSON.stringify([database, query, type, fromDate, page]) : null;
  const objects = useResource(objectsKey, (signal) =>
    CatalogService.objects(database, {q: query, type, fromDate, page, pageSize: PAGE_SIZE}, signal),
  );

  const selected = Object.values(selection);
  const running = session.phase === 'running';
  const full = selected.length >= MAX_SELECTION;

  function filterChanged(apply: () => void) {
    apply();
    setPage(1);
  }

  return (
    <div className="page">
      <PageHeader
        title="Nesne incelemesi"
        description="Veritabanını seçip nesneleri işaretleyin. Başka bir veritabanına geçerek seçime eklemeye devam edebilirsiniz; bir incelemede en çok 50 nesne olur."
      />
      <LastReviewBanner kind="object" />
      <Card
        title="Veritabanı"
        actions={
          <Button size="sm" variant="ghost" onClick={databases.reload} disabled={databases.status === 'loading'}>
            Listeyi yenile
          </Button>
        }
      >
        <div className="stack">
          <div className="field">
            <label className="field-label" htmlFor="review-database">
              Nesne listesi için veritabanı
            </label>
            <select
              id="review-database"
              className="select"
              value={database}
              disabled={databases.data === undefined || databases.data.items.length === 0}
              onChange={(event) => filterChanged(() => setDatabase(event.target.value))}
            >
              <option value="">{databases.status === 'loading' ? 'Yükleniyor…' : '— Veritabanı seçin —'}</option>
              {databases.data?.items.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          {databases.status === 'error' && (
            <ErrorState message={describeError(databases.error)} onRetry={databases.reload} />
          )}
          {databases.status === 'success' && databases.data.items.length === 0 && (
            <p className="muted">Bağlantı hesabının erişebildiği çevrimiçi veritabanı yok.</p>
          )}
        </div>
      </Card>

      <Card
        title="Nesne seçimi"
        actions={
          <>
            <span className="subtle tabular" aria-live="polite">
              {selected.length} / {MAX_SELECTION} seçili · {databaseCount(selection)} veritabanı
            </span>
            <Button size="sm" onClick={() => setSelection({})} disabled={selected.length === 0 || running}>
              Seçimi temizle
            </Button>
            <Button
              variant="primary"
              onClick={() => startObjectReview(selected)}
              disabled={selected.length === 0 || running}
              aria-label={
                selected.length === 0 ? 'İnceleme için en az bir nesne seçin' : `Seçilen ${selected.length} nesneyi incele`
              }
            >
              {running ? 'İnceleniyor…' : `Seçilenleri incele${selected.length ? ` (${selected.length})` : ''}`}
            </Button>
          </>
        }
        footer={
          objects.data ? (
            <Pager page={page} pageSize={PAGE_SIZE} total={objects.data.total} onPage={setPage} />
          ) : undefined
        }
      >
        <div className="stack">
          {full && <Alert tone="warning">En çok 50 nesne seçilebilir; yeni nesne eklemek için seçimden çıkarın.</Alert>}
          <div className="row">
            <div className="field grow">
              <label className="field-label" htmlFor="object-search">
                Ara
              </label>
              <input
                id="object-search"
                className="input"
                type="search"
                value={text}
                maxLength={200}
                placeholder="Şema, ad veya tür…"
                disabled={!database}
                onChange={(event) => filterChanged(() => setText(event.target.value))}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="object-type">
                Tür
              </label>
              <select
                id="object-type"
                className="select"
                value={type}
                disabled={!database}
                onChange={(event) => filterChanged(() => setType(event.target.value))}
              >
                <option value="">Tüm türler</option>
                {OBJECT_TYPES.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor="object-from-date">
                Bu tarihten sonra oluşturulan veya değişen
              </label>
              <input
                id="object-from-date"
                className="input"
                type="date"
                value={fromDate}
                disabled={!database}
                onChange={(event) => filterChanged(() => setFromDate(event.target.value))}
              />
            </div>
          </div>
          {!database && <EmptyState title="Nesne listesini görmek için bir veritabanı seçin." />}
          {objects.status === 'error' && <ErrorState message={describeError(objects.error)} onRetry={objects.reload} />}
          {objects.status === 'loading' && objects.data === undefined && <LoadingState label="Nesneler yükleniyor…" />}
          {objects.data && objects.data.items.length === 0 && <EmptyState title="Süzgeçlere uyan nesne yok." />}
          {objects.data && objects.data.items.length > 0 && (
            <div aria-busy={objects.status === 'loading'}>
              <ObjectTable
                database={database}
                objects={objects.data.items}
                selection={selection}
                onToggle={(object, value) => setSelection((current) => toggleSelection(current, database, object, value))}
                onToggleAll={(items, value) => setSelection((current) => toggleAll(current, database, items, value))}
              />
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
