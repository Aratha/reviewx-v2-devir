import {Suspense, useEffect, useState} from 'react';
import {Link, Outlet, useLocation} from 'react-router';
import {BrandMark} from '@/components/brand/BrandMark';
import {CommandPalette} from '@/components/layout/CommandPalette';
import {GlobalReviewIndicator, ReviewWindows} from '@/components/review/ReviewWindows';
import {Button} from '@/components/ui/Button';
import {Icon} from '@/components/ui/Icon';
import {LoadingState} from '@/components/ui/States';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {ReviewSessionProvider, useReviewSession} from '@/contexts/ReviewSessionContext';
import {NavigationProvider, useAppNavigation} from '@/contexts/NavigationContext';
import {isCurrent} from '@/lib/navigation';
import {roleLabel} from '@/lib/access';
import {config} from '@/lib/config';

/**
 * Signed-in layout: one slim top bar with the role-aware destinations, Ctrl+K quick navigation,
 * the live review indicator, the user and sign-out; the page fills the rest of the screen.
 * Hiding a destination is not authorization; every page's data comes from role-checked endpoints.
 */
export function AppShell() {
  return (
    <ReviewSessionProvider>
      <NavigationProvider>
        <ShellLayout />
      </NavigationProvider>
    </ReviewSessionProvider>
  );
}

function ShellLayout() {
  const {user, logout} = useAuth();
  const {t} = useIntl();
  const {session} = useReviewSession();
  const navigation = useAppNavigation();
  const {pathname} = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  // Close the narrow-screen menu after navigation.
  if (menuPath !== pathname) {
    setMenuPath(pathname);
    setMenuOpen(false);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const reviewing = session.phase === 'running';
  const displayName = user?.display_name || user?.username || '';
  const role = user?.is_super_admin ? t('home.overview.superAdmin') : roleLabel(user?.role);

  async function signOut() {
    setSigningOut(true);
    await logout();
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        {t('shell.skipToContent')}
      </a>
      <header className="topbar" data-open={menuOpen}>
        <div className="topbar-inner">
          <Link to="/" className="topbar-brand" aria-label={`${config.productName} ana sayfa`}>
            <BrandMark />
            <span className="topbar-brand-name" aria-hidden="true">
              {config.productName}
            </span>
          </Link>
          <nav id="main-navigation" className="topnav" aria-label={t('shell.navigation')}>
            {navigation.primary.map((item) => (
              <Link key={item.to} to={item.to} aria-current={isCurrent(item, pathname) ? 'page' : undefined}>
                <Icon name={item.icon} />
                <span>{item.label}</span>
                {item.to === '/inceleme' && reviewing && (
                  <span className="pulse-dot" role="img" aria-label="İnceleme sürüyor" />
                )}
                {item.count !== undefined && item.count > 0 && (
                  <span className="nav-count" aria-label={`${item.count} bekleyen`}>
                    {item.count}
                  </span>
                )}
              </Link>
            ))}
          </nav>
          <div className="topbar-tools">
            <GlobalReviewIndicator />
            <button
              type="button"
              className="cmdk-trigger"
              onClick={() => setPaletteOpen(true)}
              aria-keyshortcuts="Control+K"
              aria-label="Hızlı geçiş (Ctrl+K)"
            >
              <Icon name="search" />
              <span className="cmdk-trigger-text">Ara</span>
              <kbd>Ctrl K</kbd>
            </button>
            <div className="topbar-user">
              <span className="avatar" aria-hidden="true">
                {initials(displayName)}
              </span>
              <span className="topbar-user-text">
                <strong className="truncate">{displayName}</strong>
                <span className="subtle truncate">· {role}</span>
              </span>
            </div>
            <Button size="sm" variant="ghost" onClick={() => void signOut()} disabled={signingOut} busy={signingOut}>
              {t('auth.session.signOut')}
            </Button>
            <Button
              size="sm"
              className="menu-toggle"
              aria-expanded={menuOpen}
              aria-controls="main-navigation"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              {t('shell.menu')}
            </Button>
          </div>
        </div>
      </header>
      <main id="main-content" className="shell-main" tabIndex={-1}>
        <Suspense fallback={<LoadingState />}>
          <Outlet />
        </Suspense>
      </main>
      <ReviewWindows />
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
    </div>
  );
}

/** Up to two initials of a display name for the avatar disc; decorative. */
function initials(name: string): string {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0].toLocaleUpperCase('tr-TR'))
    .join('');
}
