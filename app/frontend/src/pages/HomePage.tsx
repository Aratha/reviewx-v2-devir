import {useEffect} from "react";
import {Link} from "react-router";
import {ApprovalFlow} from "@/components/rules/ApprovalFlow";
import {Badge} from "@/components/ui/Badge";
import {Icon, type IconName} from "@/components/ui/Icon";
import {useAuth} from "@/contexts/AuthContext";
import {useIntl} from "@/contexts/IntlContext";
import {useResource} from "@/hooks/useResource";
import {useRuleProposalMenu} from "@/hooks/useRuleProposalMenu";
import {roleLabel} from "@/lib/access";
import {config} from "@/lib/config";
import {REQUEST_STATUS} from "@/lib/ruleProposals";
import {RuleProposalService} from "@/services/ruleProposals";

interface Action {
  to: string;
  icon: IconName;
  title: string;
  text: string;
}

/**
 * The signed-in start page: what the product does, the user's role, the shortcuts the role can use
 * and, for rule changes, what waits for whom (sql-review rule-proposals Requirement 7).
 */
export default function HomePage() {
  const {user, access} = useAuth();
  const {t} = useIntl();
  const menu = useRuleProposalMenu(access.review, "home");
  const ruleManager = access.manageRules && !user?.is_super_admin;
  useEffect(() => {
    document.title = config.productName;
  }, []);

  const actions: Action[] = [
    ...(access.review
      ? [
          {to: "/inceleme", icon: "database" as const, title: "Nesne incelemesi", text: "SQL Server'daki nesneleri seçip yayımlanmış kurallarla inceleyin."},
          {to: "/sql-inceleme", icon: "code" as const, title: "SQL betiği incelemesi", text: "Yapıştırdığınız SQL metnini satır referanslı bulgularla inceleyin."},
          {to: "/gecmis", icon: "history" as const, title: "İnceleme geçmişi", text: "Önceki incelemeleri açın, CSV veya SQL olarak dışa aktarın."},
          {to: "/zamanlanmis-incelemeler", icon: "clock" as const, title: "Zamanlanmış incelemeler", text: "Periyodik incelemeler tanımlayın, özetleri e-postayla alın."},
          {to: "/yayimlanmis-kurallar", icon: "book" as const, title: "Yayımlanmış kurallar", text: "İncelemelerde kullanılan kuralları tek cümlelik özetleriyle görün."},
        ]
      : []),
    ...(menu.canPropose
      ? [{to: "/kural-onerilerim", icon: "lightbulb" as const, title: "Kural önerilerim", text: "Yeni kural veya grup önerin; kararları takip edin."}]
      : []),
    ...(access.manageRules
      ? [{to: "/kurallar", icon: "pencil" as const, title: "Kurallar", text: user?.is_super_admin ? "Taslağı düzenleyin ve doğrudan yayımlayın." : "Taslağı düzenleyin ve onaya gönderin."}]
      : []),
  ];

  return (
    <div className="page">
      <section className="dash-hero" aria-labelledby="home-title">
        <div>
          <div className="eyebrow">{config.primaryDomain}</div>
          <h1 id="home-title">{config.productName}</h1>
          <p>
            <strong>Hoş geldiniz{user?.display_name ? `, ${user.display_name}` : ""}.</strong> {config.projectIntent}
          </p>
        </div>
        <Badge tone="primary">{user?.is_super_admin ? t("home.overview.superAdmin") : roleLabel(user?.role)}</Badge>
      </section>

      {menu.canDecide && (
        <section className="stack" aria-labelledby="home-approvals">
          <div className="section-head">
            <h2 id="home-approvals" className="section-title">Onay bekleyen işler</h2>
            <Link to="/kural-onaylari">Kural onaylarına git</Link>
          </div>
          <div className="stat-grid">
            <Link to="/kural-onaylari" className={`stat${menu.pending > 0 ? " is-attention" : ""}`}>
              <span className="stat-icon"><Icon name="inbox" /></span>
              <span>
                <span className="stat-value">{menu.pending}</span>
                <span className="stat-label">Karar bekleyen öneri ve yayın isteği</span>
              </span>
            </Link>
          </div>
        </section>
      )}

      {ruleManager && <LatestRequestStat />}

      <section className="stack" aria-labelledby="home-actions">
        <h2 id="home-actions" className="section-title">{t("home.empty.title")}</h2>
        <div className="action-grid">
          {actions.map((action) => (
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

      {menu.canDecide ? (
        <ApprovalFlow role="decider" />
      ) : ruleManager ? (
        <ApprovalFlow role="manager" />
      ) : menu.canPropose ? (
        <ApprovalFlow role="proposer" />
      ) : null}
    </div>
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
      <div className="stat-grid">
        <Link to="/kurallar" className={`stat${request.status === "bekliyor" ? " is-attention" : ""}`}>
          <span className="stat-icon"><Icon name="send" /></span>
          <span>
            <span className="stat-label">Durum</span>
            <strong>{REQUEST_STATUS[request.status]}</strong>
            {request.rejection_reason && <span className="stat-label">Gerekçe: {request.rejection_reason}</span>}
          </span>
        </Link>
      </div>
    </section>
  );
}
