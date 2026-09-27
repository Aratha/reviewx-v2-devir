import type {ReactNode} from 'react';
import {classes} from '@/lib/utils';

export type AlertTone = 'error' | 'success' | 'warning' | 'info';

/** Errors are announced assertively; other notices politely. */
export function Alert({
  tone,
  children,
  className,
}: {
  tone: AlertTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={classes('alert', `alert-${tone}`, className)}>
      {children}
    </div>
  );
}
