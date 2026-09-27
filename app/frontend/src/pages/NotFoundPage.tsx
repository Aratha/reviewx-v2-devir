import {Link} from 'react-router';
import {useIntl} from '@/contexts/IntlContext';

export default function NotFoundPage() {
  const {t} = useIntl();
  return (
    <main className="center">
      <div>
        <h1>{t('routing.notFound.title')}</h1>
        <Link to="/">{t('routing.notFound.home')}</Link>
      </div>
    </main>
  );
}
