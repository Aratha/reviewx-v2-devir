import { useEffect } from "react";
import { Link } from "react-router";
import { useAuth } from "@/contexts/AuthContext";
import { useIntl } from "@/contexts/IntlContext";
import { roleLabel } from "@/lib/access";
import { config } from "@/lib/config";

export default function HomePage() {
  const { user, access } = useAuth();
  const { t } = useIntl();
  useEffect(() => {
    document.title = config.productName;
  }, []);
  return (
    <div className="home">
      <div>
        <div className="eyebrow">{config.primaryDomain}</div>
        <h1>{config.productName}</h1>
      </div>
      <section className="hero">
        <p>{config.projectIntent}</p>
        <dl className="facts">
          <div>
            <dt>{t("home.overview.actor")}</dt>
            <dd>{user?.display_name || user?.username}</dd>
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
                : roleLabel(user?.role)}
            </dd>
          </div>
        </dl>
      </section>
      <section className="empty-state">
        <h2>{t("home.empty.title")}</h2>
        <p>{t("home.empty.body")}</p>
        {access.review && (
          <p className="row">
            <Link className="btn btn-primary" to="/inceleme">
              Nesne incelemesi
            </Link>
            <Link className="btn btn-secondary" to="/sql-inceleme">
              SQL betiği incelemesi
            </Link>
            <Link className="btn btn-secondary" to="/gecmis">
              İnceleme geçmişi
            </Link>
          </p>
        )}
      </section>
    </div>
  );
}
