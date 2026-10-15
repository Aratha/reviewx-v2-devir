import {Suspense, useState} from 'react';
import {NavLink, Outlet, useLocation} from 'react-router';
import {BrandMark} from '@/components/brand/BrandMark';
import {GlobalReviewIndicator, ReviewWindows} from '@/components/review/ReviewWindows';
import {Button} from '@/components/ui/Button';
import {Icon, type IconName} from '@/components/ui/Icon';
import {LoadingState} from '@/components/ui/States';
import {useAuth} from '@/contexts/AuthContext';
import {useIntl} from '@/contexts/IntlContext';
import {ReviewSessionProvider, useReviewSession} from '@/contexts/ReviewSessionContext';
import {useConnectionMenu} from '@/hooks/useConnectionMenu';
import {useRuleProposalMenu} from '@/hooks/useRuleProposalMenu';
import {roleLabel} from '@/lib/access';
import {config} from '@/lib/config';

interface MenuItem {
  to: string;
  label: string;
  icon: IconName;
  busy?: boolean;
  /** Pending decisions shown next to the label (rule-proposals Requirement 7). */
  count?: number;
}

/**
 * Signed-in layout: role-aware navigation, the user and sign-out, the live review indicator and
 * windows. Hiding a menu item is not authorization; every page's data comes from role-checked
 * endpoints.
 */
export function AppShell() {
  return (
    <ReviewSessionProvider>
      <ShellLayout />
    </ReviewSessionProvider>
  );
}

function ShellLayout() {
  const {user, access, logout} = useAuth();
  const {t} = useIntl();
  const {session} = useReviewSession();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(location.pathname);
  const [signingOut, setSigningOut] = useState(false);
  const connections = useConnectionMenu(access.manageRules);
  const proposals = useRuleProposalMenu(access.review, location.pathname);

  // Close the narrow-screen menu after navigation.
  if (menuPath !== location.pathname) {
    setMenuPath(location.pathname);
    setMenuOpen(false);
  }

  const running = session.phase === 'running';
  const reviewItems: MenuItem[] = access.review
    ? [
        {to: '/inceleme', label: 'Nesne incelemesi', icon: 'database', busy: running && session.kind === 'object'},
        {to: '/sql-inceleme', label: 'SQL betiği incelemesi', icon: 'code', busy: running && session.kind === 'script'},
        {to: '/gecmis', label: 'İnceleme geçmişi', icon: 'history'},
        {to: '/zamanlanmis-incelemeler', label: 'Zamanlanmış incelemeler', icon: 'clock'},
        {to: '/yayimlanmis-kurallar', label: 'Yayımlanmış kurallar', icon: 'book'},
        ...(proposals.canPropose
          ? [{to: '/kural-onerilerim', label: 'Kural önerilerim', icon: 'lightbulb' as const}]
          : []),
      ]
    : [];
  const adminItems: MenuItem[] = [
    ...(access.manageRules ? [{to: '/kurallar', label: 'Kurallar', icon: 'pencil' as const}] : []),
    ...(proposals.canDecide
      ? [{to: '/kural-onaylari', label: 'Kural onayları', icon: 'inbox' as const, count: proposals.pending}]
      : []),
    ...(access.manageRules && connections.sql
      ? [{to: '/ayarlar/sql', label: 'SQL bağlantısı', icon: 'plug' as const}]
      : []),
    ...(access.manageRules && connections.llm
      ? [{to: '/ayarlar/llm', label: 'LLM bağlantısı', icon: 'sparkles' as const}]
      : []),
    ...(access.manageRules ? [{to: '/llm-cagrilari', label: 'LLM çağrıları', icon: 'activity' as const}] : []),
    ...(access.administerUsers
      ? [{to: '/ayarlar/zamanlama', label: 'Zamanlama ayarı', icon: 'sliders' as const}]
      : []),
    ...(access.administerUsers ? [{to: '/kullanicilar', label: 'Kullanıcılar', icon: 'users' as const}] : []),
  ];
  const displayName = user?.display_name || user?.username || '';

  async function signOut() {
    setSigningOut(true);
    await logout();
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {t('shell.skipToContent')}
      </a>
      <aside className="app-sidebar" data-open={menuOpen}>
        <div className="row">
          <div className="grow app-brand-row">
            <BrandMark />
            <div className="grow">
              <p className="app-brand">{config.productName}</p>
              <p className="app-brand-tag">{t('shell.tagline')}</p>
            </div>
          </div>
          <Button
            size="sm"
            className="app-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {t('shell.menu')}
          </Button>
        </div>
        <nav id="main-navigation" className="app-nav" aria-label={t('shell.navigation')}>
          <MenuGroup title={t('shell.nav.home')} items={[{to: '/', label: t('shell.nav.overview'), icon: 'home'}]} />
          {reviewItems.length > 0 && <MenuGroup title="İnceleme" items={reviewItems} />}
          {adminItems.length > 0 && <MenuGroup title="Yönetim" items={adminItems} />}
        </nav>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <GlobalReviewIndicator />
          <div className="app-topbar-user push-end">
            <span className="avatar" aria-hidden="true">
              {initials(displayName)}
            </span>
            <span>
              <strong>{displayName}</strong>{' '}
              <span className="subtle">
                · {user?.is_super_admin ? t('home.overview.superAdmin') : roleLabel(user?.role)}
              </span>
            </span>
            <Button size="sm" onClick={() => void signOut()} disabled={signingOut} busy={signingOut}>
              {t('auth.session.signOut')}
            </Button>
          </div>
        </header>
        <main id="main-content" className="app-content" tabIndex={-1}>
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <ReviewWindows />
    </div>
  );
}

function MenuGroup({title, items}: {title: string; items: MenuItem[]}) {
  return (
    <div className="app-nav-group">
      <p className="app-nav-title">{title}</p>
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} end>
          <Icon name={item.icon} />
          <span className="app-nav-label">{item.label}</span>
          {item.count !== undefined && item.count > 0 && (
            <span className="nav-count" aria-label={`${item.count} bekleyen`}>
              {item.count}
            </span>
          )}
          {item.busy && <span className="pulse-dot" role="img" aria-label="İnceleme sürüyor" />}
        </NavLink>
      ))}
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
