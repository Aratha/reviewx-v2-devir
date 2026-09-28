import type {ReactNode} from 'react';
import {classes} from '@/lib/utils';

/** Line icons drawn on a 24-unit grid; stroke follows the surrounding text colour. */
const shapes = {
  arrowRight: (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
  building: (
    <>
      <rect x="5" y="3" width="14" height="18" rx="1.5" />
      <path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1" />
      <path d="M11 21v-3h2v3" />
    </>
  ),
  code: (
    <>
      <path d="m8 8-4 4 4 4" />
      <path d="m16 8 4 4-4 4" />
      <path d="m13.5 5-3 14" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="2.5" />
      <path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13" />
      <path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5" />
    </>
  ),
  history: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6L3.5 8.5" />
      <path d="M3.5 3.5v5h5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  listChecks: (
    <>
      <path d="m4 6.5 1.5 1.5 3-3" />
      <path d="m4 16.5 1.5 1.5 3-3" />
      <path d="M12 7h8M12 17h8" />
    </>
  ),
  shieldCheck: (
    <>
      <path d="M12 3 19 6v5.5c0 4.4-3 7.8-7 9.5-4-1.7-7-5.1-7-9.5V6z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  sparkles: (
    <>
      <path d="M11 4.5 12.6 9 17 10.5 12.6 12 11 16.5 9.4 12 5 10.5 9.4 9z" />
      <path d="M18 15v4M16 17h4" />
    </>
  ),
  userCheck: (
    <>
      <circle cx="10" cy="8" r="4" />
      <path d="M3 20c0-3.6 3.1-6 7-6 1.3 0 2.5.3 3.5.8" />
      <path d="m15.5 18 2 2 4-4" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof shapes;

/** Decorative icon; the element beside it carries the accessible name. */
export function Icon({name, className}: {name: IconName; className?: string}) {
  return (
    <svg
      className={classes('icon', className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {shapes[name]}
    </svg>
  );
}
