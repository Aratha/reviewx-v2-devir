import type {ReactNode} from 'react';
import type {Tone} from '@/lib/utils';

export type BadgeTone = Tone;

export function Badge({tone = 'neutral', children, title}: {tone?: Tone; children: ReactNode; title?: string}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}
