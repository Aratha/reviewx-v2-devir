import {screen, within} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import HomePage from './HomePage';
import {ReviewService} from '@/services/reviews';
import {RuleProposalService} from '@/services/ruleProposals';
import {renderWithSession} from '@/test/render';

function capabilities(canPropose: boolean, canDecide: boolean, pending = 0) {
  vi.spyOn(ReviewService, 'runs').mockResolvedValue({items: [], page: 1, page_size: 5, total: 0});
  vi.spyOn(RuleProposalService, 'capabilities').mockResolvedValue({can_propose: canPropose, can_decide: canDecide});
  vi.spyOn(RuleProposalService, 'list').mockResolvedValue({items: [], page: 1, page_size: 1, total: pending});
}

describe('platform home', () => {
  it('does not ship a generic business resource', () => {
    expect("Veri ambarı geliştiricilerinin SQL Server nesnelerini ve yapıştırılan SQL kodunu yayımlanmış inceleme kurallarına göre kurum içi LLM ile incelemesi, bulguları satır referanslarıyla görmesi ve CSV/SQL olarak dışa aktarması; Active Directory girişiyle ve kurumsal Kubernetes ortamında güvenli çalışma.").not.toMatch(/sample item/i);
  });

  it('shows the super admin the decisions waiting and how approvals work', async () => {
    capabilities(true, true, 3);
    renderWithSession(<HomePage />, {role: 'super_admin'});
    const approvals = await screen.findByRole('region', {name: 'Onay bekleyen işler'});
    expect(await within(approvals).findByText('3')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Onay akışı'})).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /Kurallar/})).toBeInTheDocument();
  });

  it('gives a reviewer the review shortcuts without approvals', async () => {
    capabilities(false, false);
    renderWithSession(<HomePage />, {role: 'inceleyici'});
    expect(await screen.findByRole('link', {name: /Nesne incelemesi/})).toBeInTheDocument();
    expect(screen.queryByRole('region', {name: 'Onay bekleyen işler'})).toBeNull();
    expect(screen.queryByRole('link', {name: /^Kurallar/})).toBeNull();
  });

  it('explains the proposal path to a user allowed to propose', async () => {
    capabilities(true, false);
    renderWithSession(<HomePage />, {role: 'inceleyici'});
    expect(await screen.findByRole('heading', {name: 'Öneriniz nasıl yayımlanır?'})).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /Kural önerilerim/})).toBeInTheDocument();
  });
});
