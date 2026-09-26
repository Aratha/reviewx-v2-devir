import {useState, type FormEvent} from 'react';
import {Navigate, useNavigate} from 'react-router';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import {config} from '@/lib/config';

/** Stable catalog key for each login failure the backend distinguishes. */
function loginErrorKey(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) return 'auth.login.invalidCredentials';
  if (error instanceof ApiError && error.status === 429) return 'auth.login.tooManyAttempts';
  return 'auth.login.unavailable';
}

function languageName(locale: string): string {
  try {
    return new Intl.DisplayNames([locale], {type: 'language'}).of(locale) ?? locale;
  } catch {
    return locale;
  }
}

export default function LoginPage() {
  const {user, login} = useAuth();
  const {locale, locales, setLocale, t} = useIntl();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrorKey(null);
    try {
      await login(username, password);
      navigate('/', {replace: true});
    } catch (error) {
      setErrorKey(loginErrorKey(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="eyebrow">{t('auth.login.context', {domain: config.primaryDomain})}</div>
        <h1>{"DWH Code Review"}</h1>
        <p>{t('auth.login.subtitle')}</p>
        <form onSubmit={submit}>
          <label htmlFor="username">{t('auth.login.username')}</label>
          <input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label htmlFor="password">{t('auth.login.password')}</label>
          <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {errorKey && <div role="alert">{t(errorKey)}</div>}
          <button type="submit" disabled={busy}>{busy ? t('auth.login.busy') : t('auth.login.submit')}</button>
        </form>
        {locales.length > 1 && (
          <div className="language">
            <label htmlFor="language">{t('common.language.label')}</label>
            <select id="language" value={locale} onChange={(e) => setLocale(e.target.value)}>
              {locales.map((option) => (
                <option key={option} value={option} lang={option}>
                  {languageName(option)}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>
    </main>
  );
}
