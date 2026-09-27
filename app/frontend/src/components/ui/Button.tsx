import type {ButtonHTMLAttributes} from 'react';
import {classes} from '@/lib/utils';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-outline';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'md' | 'sm';
  /** Shows a spinner and marks the button busy; the caller keeps it disabled while busy. */
  busy?: boolean;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  busy = false,
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={classes('btn', `btn-${variant}`, size === 'sm' && 'btn-sm', className)}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
