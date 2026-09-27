import type {ReactNode} from 'react';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';

export function PermissionRoute({
  permission,
  children,
}: {
  permission?: string;
  children: ReactNode;
}) {
  const {hasPermission} = useAuth();
  const {t} = useIntl();
  if (permission && !hasPermission(permission))
    return (
      <main className="center">
        <div>
          <h1>{t('access.forbidden.title')}</h1>
          <p>{t('access.forbidden.body')}</p>
        </div>
      </main>
    );
  return <>{children}</>;
}
