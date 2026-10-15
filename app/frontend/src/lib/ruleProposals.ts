import type {RuleProposalStatus} from '@/types/sqlReview';

type Tone = 'neutral' | 'success' | 'danger' | 'warning' | 'info';

/** Turkish labels of the proposal states (sql-review rule-proposals Requirement 4). */
export const PROPOSAL_STATUS: Record<RuleProposalStatus, string> = {
  bekliyor: 'Bekliyor',
  onaylandi: 'Onaylandı',
  reddedildi: 'Reddedildi',
  geri_cekildi: 'Geri çekildi',
};

/** The badge tone of a proposal state. */
export function proposalStatusTone(status: RuleProposalStatus): Tone {
  if (status === 'onaylandi') return 'success';
  if (status === 'reddedildi') return 'danger';
  if (status === 'bekliyor') return 'warning';
  return 'neutral';
}
