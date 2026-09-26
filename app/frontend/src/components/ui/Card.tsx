import type {ReactNode} from 'react';
import {classes} from '@/lib/utils';

export function Card({
  title,
  headingLevel = 2,
  actions,
  footer,
  children,
  className,
  bodyClassName,
  labelledBy,
}: {
  title?: ReactNode;
  headingLevel?: 2 | 3;
  actions?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  labelledBy?: string;
}) {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <section className={classes('card', className)} aria-labelledby={labelledBy}>
      {(title !== undefined || actions !== undefined) && (
        <header className="card-header">
          {title !== undefined && <Heading id={labelledBy}>{title}</Heading>}
          {actions !== undefined && <div className="page-actions">{actions}</div>}
        </header>
      )}
      {children !== undefined && <div className={classes('card-body', bodyClassName)}>{children}</div>}
      {footer !== undefined && <footer className="card-footer">{footer}</footer>}
    </section>
  );
}
