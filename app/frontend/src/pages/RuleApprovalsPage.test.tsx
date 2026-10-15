import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import RuleApprovalsPage from './RuleApprovalsPage';
import {RuleProposalService} from '@/services/ruleProposals';
import {RuleSetService} from '@/services/ruleSet';
import {apiError, renderWithSession} from '@/test/render';
import type {RuleProposalDetail, RuleProposalItem, RuleSetVersionDetail} from '@/types/sqlReview';

const VERSION: RuleSetVersionDetail = {
  number: 4,
  published_at: '2026-10-14T09:00:00Z',
  published_by_name: 'Uygulama Yöneticisi',
  source: 'arayuz',
  critical: [{id: 'Kural01', text: 'NOLOCK kullanılmamalıdır. Kirli okuma yapar.', summary: '', requires_metadata: false, rule_group_ids: []}],
  normal: [],
  groups: [{id: 'grp-perf', name: 'Performans', description: ''}],
  critical_count: 1,
  normal_count: 0,
};

function proposal(overrides: Partial<RuleProposalItem> = {}): RuleProposalItem {
  return {
    id: 'p-1',
    kind: 'rule',
    status: 'bekliyor',
    proposer_name: 'Ayşe İnceleyici',
    created_at: '2026-10-14T10:00:00Z',
    summary: 'Geçici tablolar silinmelidir.',
    group_name: '',
    decided_by_name: null,
    decided_at: null,
    rejection_reason: null,
    published_version_number: null,
    new_rule_id: null,
    owned: false,
    ...overrides,
  };
}

function proposalDetail(base: RuleProposalItem, overrides: Partial<RuleProposalDetail> = {}): RuleProposalDetail {
  return {
    ...base,
    text: 'Geçici tablolar işlem sonunda DROP edilmelidir; aksi halde tempdb dolar.',
    priority: 'critical',
    requires_metadata: true,
    rule_group_ids: ['grp-perf'],
    group_description: '',
    rule_codes: [],
    rationale: 'Gece işlerinde tempdb doldu.',
    ...overrides,
  };
}

function pending(items: RuleProposalItem[]) {
  return {items, page: 1, page_size: 100, total: items.length};
}

describe('rule approvals page (rule-proposals Requirement 1, 5-7)', () => {
  beforeEach(() => {
    const rule = proposal();
    const group = proposal({id: 'p-2', kind: 'group', summary: '', group_name: 'Veri kalitesi'});
    vi.spyOn(RuleProposalService, 'list').mockResolvedValue(pending([rule, group]));
    vi.spyOn(RuleProposalService, 'get').mockImplementation(async (id) =>
      id === 'p-1'
        ? proposalDetail(rule)
        : proposalDetail(group, {priority: null, requires_metadata: false, rule_group_ids: [], rule_codes: ['Kural01', 'Kural77'], rationale: ''}),
    );
    vi.spyOn(RuleSetService, 'latest').mockResolvedValue(VERSION);
  });

  it('shows a rule proposal with its detailed text and approves it', async () => {
    const approve = vi.spyOn(RuleProposalService, 'approve').mockResolvedValue(proposalDetail(proposal({status: 'onaylandi'})));
    renderWithSession(<RuleApprovalsPage />, {role: 'super_admin'});
    expect(await screen.findByRole('tab', {name: 'Kural önerileri (1)'})).toHaveAttribute('aria-selected', 'true');
    const card = await screen.findByRole('listitem', {name: 'Geçici tablolar silinmelidir.'});
    expect(await within(card).findByText(/aksi halde tempdb dolar/)).toBeInTheDocument();
    expect(within(card).getByText('Kritik')).toBeInTheDocument();
    expect(within(card).getByText('Performans')).toBeInTheDocument();
    expect(within(card).getByText('Gerekçe: Gece işlerinde tempdb doldu.')).toBeInTheDocument();
    fireEvent.click(within(card).getByRole('button', {name: 'Geçici tablolar silinmelidir. onayla'}));
    await waitFor(() => expect(approve).toHaveBeenCalledWith('p-1'));
    await waitFor(() => expect(RuleProposalService.list).toHaveBeenCalledTimes(2));
  });

  it('rejects only with a reason and shows a conflict', async () => {
    const reject = vi.spyOn(RuleProposalService, 'reject').mockResolvedValue(proposalDetail(proposal({status: 'reddedildi'})));
    vi.spyOn(RuleProposalService, 'approve').mockRejectedValue(apiError(409, 'proposal_conflict'));
    renderWithSession(<RuleApprovalsPage />, {role: 'super_admin'});
    const card = await screen.findByRole('listitem', {name: 'Geçici tablolar silinmelidir.'});
    fireEvent.click(within(card).getByRole('button', {name: 'Geçici tablolar silinmelidir. onayla'}));
    expect(await within(card).findByText(/en son yayımlanmış sürüme artık uymuyor/)).toBeInTheDocument();
    fireEvent.click(within(card).getByRole('button', {name: 'Geçici tablolar silinmelidir. reddet'}));
    const send = within(card).getByRole('button', {name: 'Reddi gönder'});
    expect(send).toBeDisabled();
    fireEvent.change(within(card).getByLabelText(/Ret gerekçesi/), {target: {value: 'Kural03 ile aynı.'}});
    fireEvent.click(send);
    await waitFor(() => expect(reject).toHaveBeenCalledWith('p-1', 'Kural03 ile aynı.'));
  });

  it('lists a group proposal with the summaries of its rules', async () => {
    renderWithSession(<RuleApprovalsPage />, {role: 'super_admin'});
    fireEvent.click(await screen.findByRole('tab', {name: 'Grup önerileri (1)'}));
    const card = await screen.findByRole('listitem', {name: 'Veri kalitesi'});
    expect(await within(card).findByText('NOLOCK kullanılmamalıdır.')).toBeInTheDocument();
    expect(within(card).getByText('yayımlanmış sürümde artık yok')).toBeInTheDocument();
  });

  it('has no permission list: every reviewer may propose (Decision 6)', async () => {
    renderWithSession(<RuleApprovalsPage />, {role: 'super_admin'});
    await screen.findByRole('tab', {name: /Kural önerileri/});
    expect(screen.queryByRole('tab', {name: 'Öneri yetkisi'})).toBeNull();
  });
});
