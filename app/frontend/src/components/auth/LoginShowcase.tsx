import {BrandMark} from '@/components/brand/BrandMark';
import {Icon, type IconName} from '@/components/ui/Icon';
import {useIntl} from '@/contexts/IntlContext';
import {config} from '@/lib/config';

interface Capability {
  icon: IconName;
  title: string;
  body: string;
}

/**
 * The sign-in screen's second half: what the product does, in the words of its accepted PRDs.
 * Wide screens only; the form stands alone on narrow ones.
 */
export function LoginShowcase() {
  const {t} = useIntl();
  const capabilities: Capability[] = [
    {icon: 'database', title: t('auth.login.hero.objectReview.title'), body: t('auth.login.hero.objectReview.body')},
    {icon: 'code', title: t('auth.login.hero.scriptReview.title'), body: t('auth.login.hero.scriptReview.body')},
    {icon: 'listChecks', title: t('auth.login.hero.rules.title'), body: t('auth.login.hero.rules.body')},
    {icon: 'sparkles', title: t('auth.login.hero.llm.title'), body: t('auth.login.hero.llm.body')},
    {icon: 'history', title: t('auth.login.hero.history.title'), body: t('auth.login.hero.history.body')},
  ];

  return (
    <aside className="login-showcase" aria-labelledby="login-showcase-title">
      <div className="login-showcase-content">
        <div className="login-showcase-brand">
          <BrandMark className="login-showcase-mark" />
          <div>
            <h2 id="login-showcase-title">{config.productName}</h2>
            <p>{t('shell.tagline')}</p>
          </div>
        </div>

        <ul className="login-capabilities">
          {capabilities.map((capability) => (
            <li key={capability.icon} className="login-capability">
              <span className="login-capability-icon">
                <Icon name={capability.icon} />
              </span>
              <div>
                <h3>{capability.title}</h3>
                <p>{capability.body}</p>
              </div>
            </li>
          ))}
        </ul>

        <div className="login-trust">
          <span className="login-trust-icons">
            <span className="login-trust-icon login-trust-icon-primary">
              <Icon name="building" />
            </span>
            <span className="login-trust-icon login-trust-icon-info">
              <Icon name="userCheck" />
            </span>
            <span className="login-trust-icon login-trust-icon-warning">
              <Icon name="shieldCheck" />
            </span>
          </span>
          <p>{t('auth.login.hero.trust')}</p>
        </div>
      </div>
    </aside>
  );
}
