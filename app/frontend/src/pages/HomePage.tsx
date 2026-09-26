import { useAuth } from "@/contexts/AuthContext";
import { useIntl } from "@/contexts/IntlContext";
import { config } from "@/lib/config";

export default function HomePage() {
  const { user, logout } = useAuth();
  const { t } = useIntl();
  return (
    <main className="home">
      <header>
        <div>
          <div className="eyebrow">{config.primaryDomain}</div>
          <h1>{config.productName}</h1>
        </div>
        <button onClick={logout}>{t("auth.session.signOut")}</button>
      </header>
      <section className="hero">
        <p>{config.projectIntent}</p>
        <dl>
          <div>
            <dt>{t("home.overview.actor")}</dt>
            <dd>{user?.username}</dd>
          </div>
          <div>
            <dt>{t("home.overview.tenant")}</dt>
            <dd>{user?.tenant_id}</dd>
          </div>
          <div>
            <dt>{t("home.overview.authority")}</dt>
            <dd>
              {user?.is_super_admin
                ? t("home.overview.superAdmin")
                : user?.roles?.join(", ")}
            </dd>
          </div>
        </dl>
      </section>
      <section className="empty-state">
        <h2>{t("home.empty.title")}</h2>
        <p>{t("home.empty.body")}</p>
      </section>
    </main>
  );
}
