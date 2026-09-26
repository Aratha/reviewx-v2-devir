import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import RulesPage from './RulesPage';
import {RuleSetService} from '@/services/ruleSet';
import {apiError, renderWithSession} from '@/test/render';
import type {RuleSetVersionDetail, RuleSetWorkspace} from '@/types/sqlReview';

function workspace(overrides: Partial<RuleSetWorkspace> = {}): RuleSetWorkspace {
  return {
    revision: 4,
    next_rule_id: 'Kural12',
    draft_differs: false,
    critical: [
      {id: 'Kural01', text: 'NOLOCK kullanılmamalıdır.', requires_metadata: false},
      {id: 'Kural05', text: 'Geçici tablolar açıkça silinmelidir.', requires_metadata: true},
    ],
    normal: [{id: 'Kural11', text: 'Yorum satırı bulunmalıdır.', requires_metadata: false}],
    latest_version: {
      number: 1,
      published_at: '2026-04-10T14:05:15Z',
      published_by_name: null,
      source: 'ice-aktarim',
      critical_count: 2,
      normal_count: 1,
    },
    ...overrides,
  };
}

function version(number: number): RuleSetVersionDetail {
  return {
    number,
    published_at: '2026-09-26T10:00:00Z',
    published_by_name: 'Mehmet Kural',
    source: 'arayuz',
    critical: [],
    normal: [],
    critical_count: 0,
    normal_count: 0,
  };
}

async function renderPage() {
  renderWithSession(<RulesPage />, {role: 'kural-yoneticisi'});
  await screen.findByRole('heading', {name: /Kritik/});
}

function column(name: RegExp) {
  return screen.getByRole('region', {name});
}

describe('rules page', () => {
  beforeEach(() => vi.spyOn(RuleSetService, 'workspace').mockResolvedValue(workspace()));

  it('shows both groups, the latest version line and the first 100 characters of each rule', async () => {
    vi.mocked(RuleSetService.workspace).mockResolvedValue(
      workspace({draft_differs: true, normal: [{id: 'Kural11', text: 'x'.repeat(150), requires_metadata: false}]}),
    );
    await renderPage();
    expect(screen.getByText(/Son yayın: sürüm 1 · .* · içe aktarım/)).toBeInTheDocument();
    expect(screen.getByText('Taslakta yayımlanmamış değişiklik var')).toBeInTheDocument();
    expect(within(column(/Kritik/)).getByText('NOLOCK kullanılmamalıdır.')).toBeInTheDocument();
    expect(within(column(/Normal/)).getByText(`${'x'.repeat(100)}…`)).toBeInTheDocument();
  });

  it('filters by identifier or text', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('Kural ara'), {target: {value: 'geçici'}});
    expect(screen.getByText('Kural05')).toBeInTheDocument();
    expect(screen.queryByText('Kural01')).toBeNull();
    expect(within(column(/Normal/)).getByText('Bu grupta eşleşme yok.')).toBeInTheDocument();
  });

  it('moves, deletes and adds rules inside a group and marks the draft unsaved', async () => {
    await renderPage();
    expect(screen.queryByText('Kaydedilmedi')).toBeNull();
    fireEvent.click(within(column(/Kritik/)).getByText('Kural05'));
    fireEvent.click(screen.getByRole('button', {name: 'Kural05 yukarı taşı'}));
    const ids = within(column(/Kritik/)).getAllByText(/^Kural\d+$/).map((node) => node.textContent);
    expect(ids).toEqual(['Kural05', 'Kural01']);
    expect(screen.getByText('Kaydedilmedi')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Kural05 sil'}));
    expect(within(column(/Kritik/)).queryByText('Kural05')).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Normal grubuna kural ekle'}));
    fireEvent.click(screen.getByRole('button', {name: 'Kritik grubuna kural ekle'}));
    expect(within(column(/Normal/)).getByText('Kural12')).toBeInTheDocument();
    expect(within(column(/Kritik/)).getByText('Kural13')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Kural12 kural metni'), {target: {value: 'Yeni kural'}});
    const metadata = screen.getByLabelText(/Kural12: Nesne meta verisi gerekir/);
    fireEvent.click(metadata);
    expect(metadata).toBeChecked();
  });

  it('saves the draft with the revision it last saw', async () => {
    const save = vi.spyOn(RuleSetService, 'saveDraft').mockResolvedValue(workspace({revision: 5}));
    await renderPage();
    fireEvent.click(screen.getByRole('button', {name: 'Normal grubuna kural ekle'}));
    fireEvent.change(screen.getByLabelText('Kural12 kural metni'), {target: {value: 'Yeni kural'}});
    fireEvent.click(screen.getByRole('button', {name: 'Taslağı kaydet'}));
    await screen.findByText('Taslak kaydedildi.');
    expect(save).toHaveBeenCalledWith(4, workspace().critical, [
      ...workspace().normal,
      {id: 'Kural12', text: 'Yeni kural', requires_metadata: false},
    ]);
  });

  it('saves unsaved changes before publishing and reports the new version', async () => {
    const save = vi.spyOn(RuleSetService, 'saveDraft').mockResolvedValue(workspace({revision: 5}));
    const publish = vi.spyOn(RuleSetService, 'publish').mockResolvedValue(version(2));
    await renderPage();
    fireEvent.click(screen.getByRole('button', {name: 'Kritik grubuna kural ekle'}));
    fireEvent.change(screen.getByLabelText('Kural12 kural metni'), {target: {value: 'Yeni'}});
    vi.mocked(RuleSetService.workspace).mockResolvedValue(workspace({revision: 5}));
    fireEvent.click(screen.getByRole('button', {name: 'Yayınla'}));
    await screen.findByText(/Sürüm 2 yayımlandı/);
    expect(save).toHaveBeenCalledTimes(1);
    expect(publish).toHaveBeenCalledWith(5);
    expect(save.mock.invocationCallOrder[0]).toBeLessThan(publish.mock.invocationCallOrder[0]);
  });

  it('publishes directly when nothing is unsaved', async () => {
    const save = vi.spyOn(RuleSetService, 'saveDraft');
    vi.spyOn(RuleSetService, 'publish').mockResolvedValue(version(1));
    await renderPage();
    fireEvent.click(screen.getByRole('button', {name: 'Yayınla'}));
    await screen.findByText('Taslak son sürümle aynı; yeni sürüm oluşmadı (sürüm 1).');
    expect(save).not.toHaveBeenCalled();
  });

  it('shows the 409 message with a reload button when someone else changed the rules', async () => {
    vi.spyOn(RuleSetService, 'saveDraft').mockRejectedValue(apiError(409, 'rule_set_draft_conflict'));
    await renderPage();
    fireEvent.click(screen.getByRole('button', {name: 'Normal grubuna kural ekle'}));
    fireEvent.change(screen.getByLabelText('Kural12 kural metni'), {target: {value: 'x'}});
    fireEvent.click(screen.getByRole('button', {name: 'Taslağı kaydet'}));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Kurallar başka biri tarafından değiştirildi; sayfayı yenileyin.',
    );
    fireEvent.click(screen.getByRole('button', {name: 'Sayfayı yenile'}));
    await waitFor(() => expect(RuleSetService.workspace).toHaveBeenCalledTimes(2));
  });

  it('refuses a rule text over 8,000 characters before sending it', async () => {
    await renderPage();
    fireEvent.click(within(column(/Normal/)).getByText('Kural11'));
    fireEvent.change(screen.getByLabelText('Kural11 kural metni'), {target: {value: 'a'.repeat(8001)}});
    expect(screen.getByRole('button', {name: 'Taslağı kaydet'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Yayınla'})).toBeDisabled();
  });
});
