import {useEffect} from "react";
import {Link} from "react-router";
import {QualityPulse} from "@/components/review/QualityPulse";
import {ApprovalFlow} from "@/components/rules/ApprovalFlow";
import {Badge} from "@/components/ui/Badge";
import {Icon, type IconName} from "@/components/ui/Icon";
import {EmptyState, ErrorState, LoadingState} from "@/components/ui/States";
import {useAuth} from "@/contexts/AuthContext";
import {useIntl} from "@/contexts/IntlContext";
import {useResource} from "@/hooks/useResource";
import {useRuleProposalMenu} from "@/hooks/useRuleProposalMenu";
import {roleLabel} from "@/lib/access";
import {config} from "@/lib/config";
import {describeError} from "@/lib/errorMessages";
import {formatDateTime, formatNumber} from "@/lib/format";
import {RUN_STATUS} from "@/lib/reviewResults";
import {REQUEST_STATUS} from "@/lib/ruleProposals";
import {ReviewService} from "@/services/reviews";
import {RuleProposalService} from "@/services/ruleProposals";

interface Action {
  to: string;
  icon: IconName;
  title: string;
  text: string;
}

const START: Action[] = [
  {to: "/inceleme", icon: "database", title: "Nesne incelemesi", text: "SQL Server nesnelerini seçin, kurallarla inceleyin."},
  {to: "/sql-inceleme", icon: "code", title: "SQL betiği incelemesi", text: "Metni yapıştırın, satır referanslı bulgular alın."},
  {to: "/zamanlanmis-incelemeler", icon: "clock", title: "Zamanlanmış incelemeler", text: "Düzenli çalışsın, özeti e-postayla gelsin."},
];

function greeting(hour: number): string {
  if (hour < 6) return "İyi geceler";
  if (hour < 12) return "Günaydın";
  if (hour < 18) return "İyi günler";
  return "İyi akşamlar";
}

/**
 * The signed-in start page: one screen with the three ways to start a review, the user's latest
 * reviews and, for rule changes, what waits for whom (sql-review rule-proposals Requirement 7).
 */
export default function HomePage() {
  const {user, access} = useAuth();
  const {t} = useIntl();
  const menu = useRuleProposalMenu(access.review, "home");
  const ruleManager = access.manageRules && !user?.is_super_admin;
  useEffect(() => {
    document.title = config.productName;
  }, []);

  const firstName = (user?.display_name || user?.username || "").split(" ")[0];
  const shortcuts: Action[] = [
    ...(access.review
      ? [
          {to: "/gecmis", icon: "history" as const, title: "İnceleme geçmişi", text: "Önceki incelemeler, CSV ve SQL dışa aktarımı."},
          {to: "/yayimlanmis-kurallar", icon: "book" as const, title: "Yayımlanmış kurallar", text: "İncelemelerde kullanılan kurallar."},
        ]
      : []),
    ...(menu.canPropose
      ? [{to: "/kural-onerilerim", icon: "lightbulb" as const, title: "Kural önerilerim", text: "Kural veya grup önerin, kararı izleyin."}]
      : []),
    ...(access.manageRules
      ? [{to: "/yonetim/kurallar", icon: "pencil" as const, title: "Kurallar", text: user?.is_super_admin ? "Taslağı düzenleyin ve yayımlayın." : "Taslağı düzenleyin, onaya gönderin."}]
      : []),
  ];

  return (
    <div className="page page-fill home">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-text">
          <p className="home-greeting">
            {greeting(new Date().getHours())}
            {firstName ? `, ${firstName}` : ""}
          </p>
          <h1 id="home-title">{config.productName}</h1>
          <p className="home-lead">SQL kodunuzu yayımlanmış kurallarla, kurum içi LLM ile inceleyin; bulguları satır satır görün.</p>
          <div className="row">
            <Badge tone="primary">{user?.is_super_admin ? t("home.overview.superAdmin") : roleLabel(user?.role)}</Badge>
            <span className="subtle">
              <kbd>Ctrl</kbd> + <kbd>K</kbd> ile her yere hızlı geçin
            </span>
          </div>
        </div>
        {access.review && (
          <nav className="home-start" aria-label="İncelemeye başla">
            {START.map((action) => (
              <Link key={action.to} to={action.to} className="start-card">
                <span className="start-icon">
                  <Icon name={action.icon} />
                </span>
                <span className="stack-tight">
                  <strong>{action.title}</strong>
                  <span className="action-text">{action.text}</span>
                </span>
                <Icon name="arrowRight" className="start-arrow" />
              </Link>
            ))}
          </nav>
        )}
      </section>

      <div className="home-grid">
        <div className="home-main">
          {access.review && <RecentReviews />}
          {shortcuts.length > 0 && (
            <section className="stack" aria-labelledby="home-actions">
              <h2 id="home-actions" className="section-title">Kısayollar</h2>
              <div className="action-grid">
                {shortcuts.map((action) => (
                  <Link key={action.to} to={action.to} className="action-card">
                    <span className="stat-icon"><Icon name={action.icon} /></span>
                    <span>
                      <strong>{action.title}</strong>
                      <span className="action-text">{action.text}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="home-side" aria-label="Durum">
          {access.review && <QualityPulse />}
          {menu.canDecide && (
            <section className="stack" aria-labelledby="home-approvals">
              <div className="section-head">
                <h2 id="home-approvals" className="section-title">Onay bekleyen işler</h2>
                <Link to="/yonetim/onaylar">Onaylara git</Link>
              </div>
              <Link to="/yonetim/onaylar" className={`stat${menu.pending > 0 ? " is-attention" : ""}`}>
                <span className="stat-icon"><Icon name="inbox" /></span>
                <span>
                  <span className="stat-value">{menu.pending}</span>
                  <span className="stat-label">Karar bekleyen öneri ve yayın isteği</span>
                </span>
              </Link>
            </section>
          )}
          {ruleManager && <LatestRequestStat />}
          {menu.canDecide ? (
            <ApprovalFlow role="decider" />
          ) : ruleManager ? (
            <ApprovalFlow role="manager" />
          ) : menu.canPropose ? (
            <ApprovalFlow role="proposer" />
          ) : null}
        </aside>
      </div>
    </div>
  );
}

/** The user's five latest reviews; each opens in the history. */
function RecentReviews() {
  const runs = useResource("home:recent-runs", (signal) => ReviewService.runs("mine", 1, 5, signal));
  return (
    <section className="card card-fill" aria-labelledby="home-recent">
      <div className="card-header">
        <h2 id="home-recent">Son incelemeleriniz</h2>
        <Link to="/gecmis">Tümünü gör</Link>
      </div>
      <div className="card-body">
        {runs.status === "error" && <ErrorState message={describeError(runs.error)} onRetry={runs.reload} />}
        {runs.data === undefined && runs.status !== "error" && <LoadingState label="İncelemeler yükleniyor…" />}
        {runs.data && runs.data.items.length === 0 && (
          <EmptyState title="Henüz inceleme yok" icon="sparkles">
            Yukarıdan bir inceleme başlatın; sonuçlar burada görünür.
          </EmptyState>
        )}
        {runs.data && runs.data.items.length > 0 && (
          <ul className="list recent-list">
            {runs.data.items.map((run) => (
              <li key={run.id}>
                <Link to={`/gecmis?run=${encodeURIComponent(run.id)}`} className="recent-row">
                  <span className="stat-icon">
                    <Icon name={run.kind === "script" ? "code" : run.kind === "scheduled" ? "clock" : "database"} />
                  </span>
                  <span className="grow stack-tight">
                    <strong className="truncate">{run.title}</strong>
                    <span className="subtle truncate">{formatDateTime(run.started_at)}</span>
                  </span>
                  <span className="recent-meta">
                    <Badge tone={RUN_STATUS[run.status].tone}>{RUN_STATUS[run.status].label}</Badge>
                    <span className="subtle tabular">{formatNumber(run.finding_count)} bulgu</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** The rule manager's latest publish request, as on the rules page. */
function LatestRequestStat() {
  const latest = useResource("publish-requests:home", (signal) => RuleProposalService.publishRequests(null, 1, 1, signal));
  const request = latest.data?.items[0];
  if (!request) return null;
  return (
    <section className="stack" aria-labelledby="home-request">
      <h2 id="home-request" className="section-title">Son yayın isteğiniz</h2>
      <Link to="/yonetim/kurallar" className={`stat${request.status === "bekliyor" ? " is-attention" : ""}`}>
        <span className="stat-icon"><Icon name="send" /></span>
        <span>
          <span className="stat-label">Durum</span>
          <strong>{REQUEST_STATUS[request.status]}</strong>
          {request.rejection_reason && <span className="stat-label">Gerekçe: {request.rejection_reason}</span>}
        </span>
      </Link>
    </section>
  );
}
