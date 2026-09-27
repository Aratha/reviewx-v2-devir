import {useId, useState} from 'react';
import {Badge} from '@/components/ui/Badge';
import {PageHeader} from '@/components/ui/PageHeader';
import {EmptyState, ErrorState, LoadingState} from '@/components/ui/States';
import {useResource} from '@/hooks/useResource';
import {describeError, errorCode} from '@/lib/errorMessages';
import {formatDateTime} from '@/lib/format';
import {publisherName, ruleMatchesSearch, type Tier} from '@/lib/rules';
import {RuleSetService} from '@/services/ruleSet';
import type {RuleItem, RuleSetVersionDetail} from '@/types/sqlReview';

/**
 * Read-only published rules for both roles (sql-review rule-management Requirement 8, 11):
 * the latest version by default, any older version from the list, search by id or text.
 */
export default function PublishedRulesPage() {
  const [selected, setSelected] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const versions = useResource('rule-set-versions', (signal) => RuleSetService.versions(1, 100, signal));
  const detail = useResource(`rule-set-version:${selected ?? 'latest'}`, (signal) =>
    selected === null ? RuleSetService.latest(signal) : RuleSetService.version(selected, signal),
  );
  const noVersion = detail.status === 'error' && errorCode(detail.error) === 'no_published_rule_set';

  return (
    <div className="page">
      <PageHeader
        title="Yayımlanmış kurallar"
        description="İncelemeler en son yayımlanmış sürümü kullanır. Bulgudaki kural kimliğinin hangi metne karşılık geldiğini burada görebilirsiniz."
      />
      {noVersion && <EmptyState title="Henüz yayımlanmış kural yok" />}
      {detail.status === 'error' && !noVersion && (
        <ErrorState message={describeError(detail.error)} onRetry={detail.reload} />
      )}
      {!noVersion && (
        <div className="row">
          <div className="field grow">
            <label className="field-label" htmlFor="version-select">
              Sürüm
            </label>
            <select
              id="version-select"
              className="select"
              value={selected ?? ''}
              disabled={versions.data === undefined}
              onChange={(event) => setSelected(event.target.value === '' ? null : Number(event.target.value))}
            >
              <option value="">En son sürüm</option>
              {versions.data?.items.map((version) => (
                <option key={version.number} value={version.number}>
                  {`Sürüm ${version.number} · ${formatDateTime(version.published_at)} · ${publisherName(version)} · ${version.critical_count} kritik, ${version.normal_count} normal`}
                </option>
              ))}
            </select>
          </div>
          <div className="field grow">
            <label className="field-label" htmlFor="published-search">
              Kural ara
            </label>
            <input
              id="published-search"
              className="input"
              type="search"
              value={search}
              placeholder="Kural01 veya kural metni…"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
      )}
      {versions.status === 'error' && <ErrorState message={describeError(versions.error)} onRetry={versions.reload} />}
      {detail.status === 'loading' && detail.data === undefined && <LoadingState label="Kurallar yükleniyor…" />}
      {detail.data && !noVersion && <PublishedVersion version={detail.data} search={search} />}
    </div>
  );
}

function PublishedVersion({version, search}: {version: RuleSetVersionDetail; search: string}) {
  return (
    <div className="stack">
      <p className="subtle">
        Sürüm {version.number} · {formatDateTime(version.published_at)} · yayımlayan: {publisherName(version)}
      </p>
      <div className="split">
        <ReadOnlyColumn tier="critical" rules={version.critical} search={search} />
        <ReadOnlyColumn tier="normal" rules={version.normal} search={search} />
      </div>
    </div>
  );
}

function ReadOnlyColumn({tier, rules, search}: {tier: Tier; rules: RuleItem[]; search: string}) {
  const headingId = useId();
  const visible = rules.filter((rule) => ruleMatchesSearch(rule, search));
  return (
    <section className={`card card-${tier}`} aria-labelledby={headingId}>
      <header className="card-header">
        <h2 id={headingId}>
          {tier === 'critical' ? 'Kritik' : 'Normal'} <span className="subtle">({rules.length})</span>
        </h2>
        <Badge tone={tier === 'critical' ? 'danger' : 'info'}>{tier === 'critical' ? 'HIGH' : 'LOW / MEDIUM'}</Badge>
      </header>
      <div className="card-body">
        {visible.length === 0 ? (
          <p className="muted">{rules.length === 0 ? 'Bu grupta kural yok.' : 'Bu grupta eşleşme yok.'}</p>
        ) : (
          <ol className="list stack-tight">
            {visible.map((rule) => (
              <li key={rule.id} className="rule-line">
                <div className="row">
                  <strong className="mono">{rule.id}</strong>
                  {rule.requires_metadata && <Badge tone="primary">Nesne meta verisi gerekir</Badge>}
                </div>
                <p className="rule-text">{rule.text}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
