import type {ReactNode} from 'react';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import type {AccessRequirement} from '@/lib/access';

/**
 * Hide a page from a role that cannot use it. This only improves usability: the backend checks
 * the role on every request (application-foundation directory-login Decision 5).
 */
export function RoleRoute({require, children}: {require: AccessRequirement; children: ReactNode}) {
  const {access} = useAuth();
  const {t} = useIntl();
  if (!access[require])
    return (
      <section className="state" aria-labelledby="forbidden-title">
        <h1 id="forbidden-title">{t('access.forbidden.title')}</h1>
        <p>{t('access.forbidden.body')}</p>
      </section>
    );
  return <>{children}</>;
}
