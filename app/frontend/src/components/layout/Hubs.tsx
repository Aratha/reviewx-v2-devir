import type {ReactNode} from 'react';
import {Navigate, useLocation} from 'react-router';
import {ModeSwitch} from '@/components/layout/ModeSwitch';
import {TitleRowSwitch} from '@/components/ui/PageHeader';
import {useReviewSession} from '@/contexts/ReviewSessionContext';
import {useAppNavigation} from '@/contexts/NavigationContext';

/** "İnceleme": object, script and scheduled review share one place; the switch sits on the title row. */
export function ReviewHub({children}: {children: ReactNode}) {
  const {reviewModes} = useAppNavigation();
  const {session} = useReviewSession();
  const running = session.phase === 'running';
  const modes = reviewModes.map((mode) => ({
    ...mode,
    busy:
      running &&
      ((mode.to === '/inceleme' && session.kind === 'object') || (mode.to === '/sql-inceleme' && session.kind === 'script')),
  }));
  return <TitleRowSwitch control={<ModeSwitch label="İnceleme türü" items={modes} />}>{children}</TitleRowSwitch>;
}

/** "Kural kitaplığı": the published rules and, when allowed, the user's own proposals. */
export function LibraryHub({children}: {children: ReactNode}) {
  const {libraryModes} = useAppNavigation();
  return <TitleRowSwitch control={<ModeSwitch label="Kural kitaplığı" items={libraryModes} />}>{children}</TitleRowSwitch>;
}

/** An administration address from before Yönetim became one page; keeps links and bookmarks working. */
export function MovedTo({section}: {section: string}) {
  const {search} = useLocation();
  return <Navigate to={{pathname: `/yonetim/${section}`, search}} replace />;
}
