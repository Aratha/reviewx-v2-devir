import {fireEvent, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import PublishedRulesPage from './PublishedRulesPage';
import {RuleSetService} from '@/services/ruleSet';
import {apiError, renderWithSession, type TestRole} from '@/test/render';
import type {RuleSetVersionDetail} from '@/types/sqlReview';

function version(number: number, text: string): RuleSetVersionDetail {
  return {
    number,
    published_at: '2026-09-26T10:00:00Z',
    published_by_name: number === 1 ? null : 'Mehmet Kural',
    source: number === 1 ? 'ice-aktarim' : 'arayuz',
    critical: [{id: 'Kural01', text, requires_metadata: true}],
    normal: [{id: 'Kural11', text: 'Yorum satırı bulunmalıdır.', requires_metadata: false}],
    critical_count: 1,
    normal_count: 1,
  };
}

function mockVersions() {
  vi.spyOn(RuleSetService, 'versions').mockResolvedValue({
    items: [version(2, 'İkinci metin'), version(1, 'İlk metin')].map((detail) => ({
      number: detail.number,
      published_at: detail.published_at,
      published_by_name: detail.published_by_name,
      source: detail.source,
      critical_count: detail.critical_count,
      normal_count: detail.normal_count,
    })),
    page: 1,
    page_size: 100,
    total: 2,
  });
}

describe('published rules page', () => {
  it.each<TestRole>(['inceleyici', 'kural-yoneticisi'])('is read-only for %s', async (role) => {
    mockVersions();
    vi.spyOn(RuleSetService, 'latest').mockResolvedValue(version(2, 'İkinci metin'));
    renderWithSession(<PublishedRulesPage />, {role});
    expect(await screen.findByText('İkinci metin')).toBeInTheDocument();
    expect(screen.getByText('Nesne meta verisi gerekir')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', {name: /kural metni/})).toBeNull();
    for (const name of ['Taslağı kaydet', 'Yayınla', '+ Kural']) expect(screen.queryByRole('button', {name})).toBeNull();
  });

  it('opens an older version from the list and searches in it', async () => {
    mockVersions();
    vi.spyOn(RuleSetService, 'latest').mockResolvedValue(version(2, 'İkinci metin'));
    const older = vi.spyOn(RuleSetService, 'version').mockResolvedValue(version(1, 'İlk metin'));
    renderWithSession(<PublishedRulesPage />);
    await screen.findByText('İkinci metin');
    await waitFor(() => expect(screen.getByLabelText('Sürüm')).toBeEnabled());
    fireEvent.change(screen.getByLabelText('Sürüm'), {target: {value: '1'}});
    expect(await screen.findByText('İlk metin')).toBeInTheDocument();
    expect(older).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    expect(screen.getByText(/yayımlayan: içe aktarım/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Kural ara'), {target: {value: 'yorum'}});
    expect(screen.queryByText('İlk metin')).toBeNull();
    expect(screen.getByText('Yorum satırı bulunmalıdır.')).toBeInTheDocument();
  });

  it('says so when nothing has been published yet', async () => {
    vi.spyOn(RuleSetService, 'versions').mockResolvedValue({items: [], page: 1, page_size: 100, total: 0});
    vi.spyOn(RuleSetService, 'latest').mockRejectedValue(apiError(404, 'no_published_rule_set'));
    renderWithSession(<PublishedRulesPage />);
    expect(await screen.findByText('Henüz yayımlanmış kural yok')).toBeInTheDocument();
  });
});
