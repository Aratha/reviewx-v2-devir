import {Navigate, Outlet, useLocation} from 'react-router';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';

export function AuthGuard() {
  const {user, loading} = useAuth();
  const {t} = useIntl();
  const location = useLocation();
  if (loading) return <main className="center" role="status">{t('auth.session.loading')}</main>;
  if (!user) return <Navigate to="/login" replace state={{from: location.pathname}} />;
  return <Outlet />;
}
