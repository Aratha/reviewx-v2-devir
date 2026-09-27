import {Button} from './Button';

/** Previous/next paging with the current range; hidden when everything fits on one page. */
export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  return (
    <nav className="pager grow" aria-label="Sayfalar">
      <span className="subtle tabular">
        {total === 0 ? 'Kayıt yok' : `${first}–${last} / ${total}`}
      </span>
      {pages > 1 && (
        <span className="row">
          <Button size="sm" onClick={() => onPage(page - 1)} disabled={page <= 1}>
            Önceki
          </Button>
          <span className="subtle tabular" aria-current="page">
            Sayfa {page} / {pages}
          </span>
          <Button size="sm" onClick={() => onPage(page + 1)} disabled={page >= pages}>
            Sonraki
          </Button>
        </span>
      )}
    </nav>
  );
}
