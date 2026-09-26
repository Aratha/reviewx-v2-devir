import {useEffect, type ReactNode} from 'react';
import {config} from '@/lib/config';

/** Page title, the document title and the page's main actions. */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  useEffect(() => {
    document.title = `${title} · ${config.productName}`;
  }, [title]);
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description !== undefined && <p className="page-description">{description}</p>}
      </div>
      {actions !== undefined && <div className="page-actions">{actions}</div>}
    </header>
  );
}
