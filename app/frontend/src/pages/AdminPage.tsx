import {useEffect, useRef, type ComponentType} from 'react';
import {Link, Navigate, useParams} from 'react-router';
import {RoleRoute} from '@/components/auth/RoleRoute';
import {Badge} from '@/components/ui/Badge';
import {Icon} from '@/components/ui/Icon';
import {EmbeddedPage, PageHeader} from '@/components/ui/PageHeader';
import {useAuth} from '@/contexts/AuthContext';
import {
  LlmCallsPage,
  LlmConnectionPage,
  RuleApprovalsPage,
  RulesPage,
  ScheduledReviewSettingsPage,
  SqlConnectionPage,
  UserAdministrationPage,
} from '@/generated/lazyPages';
import {useAppNavigation} from '@/contexts/NavigationContext';
import type {AdminSection, AdminSectionId} from '@/lib/navigation';
import {useResource} from '@/hooks/useResource';
import type {AccessRequirement} from '@/lib/access';
import {ScheduledReviewService} from '@/services/scheduledReviews';

const SECTIONS: Record<AdminSectionId, {page: ComponentType; require: AccessRequirement}> = {
  kurallar: {page: RulesPage, require: 'manageRules'},
  onaylar: {page: RuleApprovalsPage, require: 'administerUsers'},
  sql: {page: SqlConnectionPage, require: 'manageRules'},
  llm: {page: LlmConnectionPage, require: 'manageRules'},
  'llm-cagrilari': {page: LlmCallsPage, require: 'manageRules'},
  zamanlama: {page: ScheduledReviewSettingsPage, require: 'administerUsers'},
  kullanicilar: {page: UserAdministrationPage, require: 'administerUsers'},
};

function isSection(value: string | undefined): value is AdminSectionId {
  return value !== undefined && Object.hasOwn(SECTIONS, value);
}

/**
 * Yönetim: every administration screen on one page. A rail lists the sections this user may
 * open; the chosen section fills the rest, and without a choice an overview shows what needs
 * attention. Each section is the same page as before, shown with a second-level heading, so its
 * behaviour and its backend checks stay unchanged.
 */
export default function AdminPage() {
  return (
    <RoleRoute require="manageRules">
      <AdminLayout />
    </RoleRoute>
  );
}

function AdminLayout() {
  const {section} = useParams();
  const {adminSections} = useAppNavigation();
  const rail = useRef<HTMLElement>(null);
  // On a narrow screen the rail scrolls sideways; keep the chosen section in view.
  useEffect(() => {
    rail.current?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView?.({block: 'nearest', inline: 'nearest'});
  }, [section, adminSections.length]);
  if (section !== undefined && !isSection(section)) return <Navigate to="/yonetim" replace />;
  const current = section !== undefined && isSection(section) ? section : null;
  const Page = current ? SECTIONS[current].page : null;

  return (
    <div className="page page-fill admin">
      <PageHeader
        title="Yönetim"
        description="Kurallar, onaylar, bağlantılar, zamanlama ve kullanıcılar tek sayfada."
      />
      <div className="admin-layout">
        <nav ref={rail} className="admin-rail" aria-label="Yönetim bölümleri">
          <Link to="/yonetim" aria-current={current === null ? 'page' : undefined}>
            <Icon name="home" />
            <span className="grow truncate">Genel durum</span>
          </Link>
          {adminSections.map((item) => (
            <Link
              key={item.id}
              to={`/yonetim/${item.id}`}
              aria-current={current === item.id ? 'page' : undefined}
            >
              <Icon name={item.icon} />
              <span className="grow truncate">{item.label}</span>
              {item.count !== undefined && item.count > 0 && (
                <span className="nav-count" aria-label={`${item.count} bekleyen`}>
                  {item.count}
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="admin-panel">
          {current && Page ? (
            <RoleRoute require={SECTIONS[current].require}>
              <EmbeddedPage host="Yönetim">
                <Page />
              </EmbeddedPage>
            </RoleRoute>
          ) : (
            <Overview sections={adminSections} />
          )}
        </div>
      </div>
    </div>
  );
}

/** What needs attention, one tile per section the user may open. */
function Overview({sections}: {sections: AdminSection[]}) {
  const {access} = useAuth();
  const email = useResource(access.administerUsers ? 'scheduled-review-email' : null, (signal) =>
    ScheduledReviewService.emailStatus(signal),
  );
  const mailReady =
    email.data === undefined
      ? null
      : email.data.scheduler_enabled && email.data.smtp_configured && email.data.allowed_domains.length > 0;

  return (
    <section className="stack" aria-labelledby="admin-overview">
      <h2 id="admin-overview" className="section-title">
        Genel durum
      </h2>
      <div className="admin-tiles">
        {sections.map((item) => (
          <Link key={item.id} to={`/yonetim/${item.id}`} className="admin-tile">
            <span className="stat-icon">
              <Icon name={item.icon} />
            </span>
            <span className="stack-tight">
              <strong>{item.label}</strong>
              <span className="action-text">{item.summary}</span>
              {item.id === 'onaylar' && (
                <Badge tone={item.count ? 'warning' : 'success'}>
                  {item.count ? `${item.count} karar bekliyor` : 'Bekleyen yok'}
                </Badge>
              )}
              {item.id === 'zamanlama' && mailReady !== null && (
                <Badge tone={mailReady ? 'success' : 'warning'}>
                  {mailReady ? 'E-posta hazır' : 'E-posta yapılandırılmadı'}
                </Badge>
              )}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
