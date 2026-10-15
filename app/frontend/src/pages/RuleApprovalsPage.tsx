import {useId, useState} from 'react';
import {ApprovalFlow} from '@/components/rules/ApprovalFlow';
import {Alert} from '@/components/ui/Alert';
import {Badge} from '@/components/ui/Badge';
import {Button} from '@/components/ui/Button';
import {PageHeader} from '@/components/ui/PageHeader';
import {EmptyState, ErrorState, LoadingState} from '@/components/ui/States';
import {Tabs} from '@/components/ui/Tabs';
import {useResource} from '@/hooks/useResource';
import {notifyRuleApprovalsChanged} from '@/hooks/useRuleProposalMenu';
import {describeError} from '@/lib/errorMessages';
import {formatDateTime} from '@/lib/format';
import {displaySummary} from '@/lib/rules';
import {RuleProposalService} from '@/services/ruleProposals';
import {RuleSetService} from '@/services/ruleSet';
import type {RuleProposalItem, RuleSetVersionDetail} from '@/types/sqlReview';

type Tab = 'rule' | 'group';
const REASON_LIMIT = 500;

/**
 * "Kural onayları" (sql-review rule-proposals Requirement 1, 5-7): the super admin reads every
 * pending rule proposal, group proposal and publish request in detail, approves it — which
 * publishes a new version at once — or rejects it with a reason the requester sees. Every
 * user may propose (Decision 6). The backend checks the super admin on every request.
 */
export default function RuleApprovalsPage() {
  const [tab, setTab] = useState<Tab>('rule');
  const [generation, setGeneration] = useState(0);
  const proposals = useResource(`rule-proposals:pending:${generation}`, (signal) =>
    RuleProposalService.list('pending', 1, 100, signal),
  );
  const latest = useResource(`rule-set-version:latest:${generation}`, (signal) => RuleSetService.latest(signal));
  const ruleItems = proposals.data?.items.filter((item) => item.kind === 'rule') ?? [];
  const groupItems = proposals.data?.items.filter((item) => item.kind === 'group') ?? [];
  const refresh = () => {
    setGeneration((value) => value + 1);
    notifyRuleApprovalsChanged();
  };

  return (
    <div className="page">
      <PageHeader
        title="Kural onayları"
        description="Onayladığınız öneri hemen yeni sürüm olarak yayımlanır; ret gerekçesi öneri sahibine görünür."
      />
      <Tabs
        label="Kural onayları"
        value={tab}
        onChange={setTab}
        items={[
          {id: 'rule', label: 'Kural önerileri', count: ruleItems.length, attention: true},
          {id: 'group', label: 'Grup önerileri', count: groupItems.length, attention: true},
        ]}
      />
      {(tab === 'rule' || tab === 'group') && proposals.status === 'error' && (
        <ErrorState message={describeError(proposals.error)} onRetry={proposals.reload} />
      )}
      {(tab === 'rule' || tab === 'group') && proposals.data === undefined && proposals.status !== 'error' && (
        <LoadingState />
      )}
      {tab === 'rule' && proposals.data && (
        <ProposalQueue items={ruleItems} version={latest.data} empty="Bekleyen kural önerisi yok" onDecided={refresh} />
      )}
      {tab === 'group' && proposals.data && (
        <ProposalQueue items={groupItems} version={latest.data} empty="Bekleyen grup önerisi yok" onDecided={refresh} />
      )}
      <ApprovalFlow role="decider" />
    </div>
  );
}

function ProposalQueue({
  items,
  version,
  empty,
  onDecided,
}: {
  items: RuleProposalItem[];
  version: RuleSetVersionDetail | undefined;
  empty: string;
  onDecided: () => void;
}) {
  if (items.length === 0) return <EmptyState title={empty} icon="check" />;
  return (
    <ul className="list stack">
      {items.map((item) => (
        <ProposalCard key={item.id} item={item} version={version} onDecided={onDecided} />
      ))}
    </ul>
  );
}

function ProposalCard({
  item,
  version,
  onDecided,
}: {
  item: RuleProposalItem;
  version: RuleSetVersionDetail | undefined;
  onDecided: () => void;
}) {
  const detail = useResource(`rule-proposal:${item.id}`, (signal) => RuleProposalService.get(item.id, signal));
  const rules = [...(version?.critical ?? []), ...(version?.normal ?? [])];
  const groupNames = new Map((version?.groups ?? []).map((group) => [group.id, group.name]));
  const title = item.kind === 'rule' ? item.summary : item.group_name;
  return (
    <li className="card card-body stack-tight" aria-label={title}>
      <div className="row">
        <Badge tone="neutral">{item.kind === 'rule' ? 'Kural' : 'Grup'}</Badge>
        <strong className="grow">{title}</strong>
        <span className="subtle">
          {item.proposer_name} · {formatDateTime(item.created_at)}
        </span>
      </div>
      {detail.status === 'error' && <Alert tone="error">{describeError(detail.error)}</Alert>}
      {detail.data && item.kind === 'rule' && (
        <div className="stack-tight">
          <div className="row">
            <Badge tone={detail.data.priority === 'critical' ? 'danger' : 'info'}>
              {detail.data.priority === 'critical' ? 'Kritik' : 'Normal'}
            </Badge>
            {detail.data.requires_metadata && <Badge tone="primary">Nesne meta verisi gerekir</Badge>}
            {detail.data.rule_group_ids.map((id) => (
              <Badge key={id} tone="neutral">
                {groupNames.get(id) ?? 'Artık olmayan grup'}
              </Badge>
            ))}
          </div>
          <p className="subtle">Ayrıntılı kural metni:</p>
          <p className="rule-text detail-box">{detail.data.text}</p>
        </div>
      )}
      {detail.data && item.kind === 'group' && (
        <div className="stack-tight">
          {detail.data.group_description && <p>{detail.data.group_description}</p>}
          <ul className="list stack-tight">
            {detail.data.rule_codes.map((code) => {
              const rule = rules.find((candidate) => candidate.id === code);
              return (
                <li key={code}>
                  <span className="mono">{code}</span>{' '}
                  <span className="subtle">{rule ? displaySummary(rule) : 'yayımlanmış sürümde artık yok'}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {detail.data?.rationale && <p className="subtle">Gerekçe: {detail.data.rationale}</p>}
      <Decision
        label={title}
        onApprove={() => RuleProposalService.approve(item.id)}
        onReject={(reason) => RuleProposalService.reject(item.id, reason)}
        onDecided={onDecided}
      />
    </li>
  );
}

function Decision({
  label,
  onApprove,
  onReject,
  onDecided,
}: {
  label: string;
  onApprove: () => Promise<unknown>;
  onReject: (reason: string) => Promise<unknown>;
  onDecided: () => void;
}) {
  const reasonId = useId();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDecided();
    } catch (failure) {
      setError(describeError(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-tight">
      {error && <Alert tone="error">{error}</Alert>}
      {rejecting && (
        <div className="field">
          <label className="field-label" htmlFor={reasonId}>
            Ret gerekçesi ({label})
          </label>
          <textarea
            id={reasonId}
            className="textarea"
            rows={2}
            maxLength={REASON_LIMIT}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      )}
      <div className="row">
        {!rejecting && (
          <Button variant="primary" busy={busy} disabled={busy} onClick={() => void run(onApprove)} aria-label={`${label} onayla`}>
            Onayla ve yayımla
          </Button>
        )}
        {rejecting ? (
          <>
            <Button
              variant="danger-outline"
              busy={busy}
              disabled={busy || reason.trim() === ''}
              onClick={() => void run(() => onReject(reason))}
            >
              Reddi gönder
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setRejecting(false)}>
              Vazgeç
            </Button>
          </>
        ) : (
          <Button variant="danger-outline" disabled={busy} onClick={() => setRejecting(true)} aria-label={`${label} reddet`}>
            Reddet
          </Button>
        )}
      </div>
    </div>
  );
}
