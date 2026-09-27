import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import ReviewHistoryPage from './ReviewHistoryPage';
import * as download from '@/lib/download';
import {ReviewService} from '@/services/reviews';
import {apiError, renderWithSession} from '@/test/render';
import {storedResult} from '@/test/reviewEvents';
import type {ReviewRunDetail, ReviewRunSummary} from '@/types/sqlReview';

function summary(overrides: Partial<ReviewRunSummary> = {}): ReviewRunSummary {
  return {
    id: 'run-1',
    kind: 'object',
    status: 'completed',
    started_at: '2026-09-26T09:00:00Z',
    finished_at: '2026-09-26T09:05:00Z',
    title: 'DWH · 1 nesne',
    subtitle: '[DWH] dbo.usp_load (P)',
    error_code: null,
    error_message: null,
    rule_version: 2,
    object_count: 1,
    finding_count: 1,
    owner_display_name: 'Ayşe İnceleyici',
    owned: true,
    ...overrides,
  };
}

function detail(overrides: Partial<ReviewRunDetail> = {}): ReviewRunDetail {
  return {...summary(), label: null, results: [storedResult()], ...overrides};
}

const cancelled = summary({
  id: 'run-2',
  kind: 'script',
  status: 'cancelled',
  title: 'Yapıştırılan SQL',
  subtitle: null,
  finding_count: 0,
});

describe('review history page', () => {
  beforeEach(() => {
    vi.spyOn(ReviewService, 'runs').mockResolvedValue({items: [summary(), cancelled], page: 1, page_size: 50, total: 2});
    vi.spyOn(ReviewService, 'run').mockImplementation(async (id) =>
      id === 'run-1' ? detail() : detail({...cancelled, results: []}),
    );
  });

  it('lists own runs with status, version and counts; a reviewer has no scope choice', async () => {
    renderWithSession(<ReviewHistoryPage />);
    expect(await screen.findByText('DWH · 1 nesne')).toBeInTheDocument();
    expect(screen.getByText('Kural sürümü 2 · 1 nesne · 1 bulgu')).toBeInTheDocument();
    expect(screen.getByText('Durduruldu')).toBeInTheDocument();
    expect(screen.queryByLabelText('Tüm incelemeler')).toBeNull();
    expect(ReviewService.runs).toHaveBeenCalledWith('mine', 1, 50, expect.any(AbortSignal));
    expect(localStorage.length).toBe(0);
  });

  it('lets the rule manager switch to all runs, which are read-only when owned by others', async () => {
    vi.mocked(ReviewService.run).mockResolvedValue(detail({owned: false, owner_display_name: 'Başka Kişi'}));
    renderWithSession(<ReviewHistoryPage />, {role: 'kural-yoneticisi'});
    await screen.findByText('DWH · 1 nesne');
    fireEvent.click(screen.getByLabelText('Tüm incelemeler'));
    await waitFor(() => expect(ReviewService.runs).toHaveBeenLastCalledWith('all', 1, 50, expect.any(AbortSignal)));
    fireEvent.click(screen.getByText('DWH · 1 nesne').closest('button')!);
    expect(await screen.findByText('Bu inceleme başka bir kullanıcıya ait; yalnız okunabilir.')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', {name: /yanlış pozitif/})).toBeNull();
    expect(screen.getByRole('button', {name: 'SQL indir'})).toBeEnabled();
  });

  it('opens a run with its results, marks a finding and downloads the CSV', async () => {
    const mark = vi.spyOn(ReviewService, 'markFinding').mockResolvedValue({id: 'f-1', false_positive: true, changed_at: null});
    const exportRun = vi
      .spyOn(ReviewService, 'exportRun')
      .mockResolvedValue({blob: new Blob(['a']), filename: 'sql-review-1.csv'});
    const save = vi.spyOn(download, 'saveFile').mockImplementation(() => undefined);
    renderWithSession(<ReviewHistoryPage />);
    fireEvent.click((await screen.findByText('DWH · 1 nesne')).closest('button')!);
    const finding = await screen.findByRole('checkbox', {name: 'Kural01 bulgu 1 yanlış pozitif'});
    fireEvent.click(finding);
    await waitFor(() => expect(finding).toBeChecked());
    expect(mark).toHaveBeenCalledWith('run-1', 'f-1', true);

    fireEvent.click(screen.getByRole('button', {name: 'CSV indir'}));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(exportRun).toHaveBeenCalledWith('run-1', 'csv');
    expect(save.mock.calls[0][1]).toBe('sql-review-1.csv');
  });

  it('disables SQL download for a run without stored SQL and explains a stopped run', async () => {
    renderWithSession(<ReviewHistoryPage />);
    fireEvent.click((await screen.findByText('Yapıştırılan SQL')).closest('button')!);
    expect(await screen.findByText('Bu inceleme durduruldu; kısmi sonuç saklanmaz.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'SQL indir'})).toBeDisabled();
    expect(screen.getByText(/SQL indirme kapalı/)).toBeInTheDocument();
  });

  it('asks before deleting one run and reloads the list', async () => {
    const remove = vi.spyOn(ReviewService, 'deleteRun').mockResolvedValue(undefined);
    renderWithSession(<ReviewHistoryPage />);
    fireEvent.click(await screen.findByRole('button', {name: 'DWH · 1 nesne incelemesini sil'}));
    const dialog = screen.getByRole('dialog', {name: 'Bu inceleme silinsin mi?'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Vazgeç'}));
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'DWH · 1 nesne incelemesini sil'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Sil'}));
    await screen.findByText('İnceleme silindi.');
    expect(remove).toHaveBeenCalledWith('run-1');
    expect(ReviewService.runs).toHaveBeenCalledTimes(2);
  });

  it('deletes all own runs after confirmation and reports the count', async () => {
    vi.spyOn(ReviewService, 'deleteOwnRuns').mockResolvedValue({deleted_count: 2});
    renderWithSession(<ReviewHistoryPage />);
    await screen.findByText('DWH · 1 nesne');
    fireEvent.click(screen.getByRole('button', {name: 'Tümünü sil'}));
    const dialog = screen.getByRole('dialog', {name: 'Tüm incelemeleriniz silinsin mi?'});
    expect(within(dialog).getByText(/Başkalarının incelemelerine dokunulmaz/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', {name: 'Sil'}));
    expect(await screen.findByText('2 inceleme silindi.')).toBeInTheDocument();
  });

  it('shows why a running run cannot be deleted', async () => {
    vi.spyOn(ReviewService, 'deleteRun').mockRejectedValue(apiError(409, 'review_run_in_progress'));
    renderWithSession(<ReviewHistoryPage />);
    fireEvent.click(await screen.findByRole('button', {name: 'DWH · 1 nesne incelemesini sil'}));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Sil'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Süren bir inceleme silinemez.');
  });
});
