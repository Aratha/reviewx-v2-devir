import {fireEvent, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import ObjectReviewPage from './ObjectReviewPage';
import {CatalogService, type ObjectQuery} from '@/services/catalog';
import {ReviewService} from '@/services/reviews';
import {apiError, renderWithSession} from '@/test/render';
import type {CatalogObject, CatalogObjectPage} from '@/types/sqlReview';

function objects(prefix: string, count: number): CatalogObject[] {
  return Array.from({length: count}, (_, index) => ({
    schema: 'dbo',
    name: `${prefix}_${String(index + 1).padStart(2, '0')}`,
    type: 'PROCEDURE',
    type_code: 'P',
    created_at: '2026-01-02T10:00:00Z',
    last_modified: '2026-03-04T10:00:00Z',
  }));
}

function page(items: CatalogObject[]): CatalogObjectPage {
  return {items, page: 1, page_size: 100, total: items.length};
}

async function chooseDatabase(name: string) {
  const select = await screen.findByLabelText('Nesne listesi için veritabanı');
  await waitFor(() => expect(select).toBeEnabled());
  fireEvent.change(select, {target: {value: name}});
}

describe('object review page', () => {
  beforeEach(() => {
    vi.spyOn(CatalogService, 'databases').mockResolvedValue({items: ['DWH', 'MART'], page: 1, page_size: 500, total: 2});
    vi.spyOn(CatalogService, 'objects').mockImplementation(async (database) =>
      page(objects(database === 'DWH' ? 'dwh' : 'mart', database === 'DWH' ? 40 : 30)),
    );
  });

  it('offers every database the server returns in the picker', async () => {
    // sql-server-connection Requirement 7: no list narrows what the account can access.
    const items = Array.from({length: 25}, (_, index) => `DB_${String(index + 1).padStart(2, '0')}`);
    vi.mocked(CatalogService.databases).mockResolvedValue({items, page: 1, page_size: 500, total: 25});
    renderWithSession(<ObjectReviewPage />);
    const select = await screen.findByLabelText('Nesne listesi için veritabanı');
    await waitFor(() => expect(select).toBeEnabled());
    const offered = within(select)
      .getAllByRole('option')
      .map((option) => option.textContent);
    expect(offered).toEqual(['— Veritabanı seçin —', ...items]);
  });

  it('says so when the account can access no database', async () => {
    vi.mocked(CatalogService.databases).mockResolvedValue({items: [], page: 1, page_size: 500, total: 0});
    renderWithSession(<ObjectReviewPage />);
    expect(await screen.findByText('Bağlantı hesabının erişebildiği çevrimiçi veritabanı yok.')).toBeInTheDocument();
    expect(screen.queryByText(/İzinli/)).toBeNull();
  });

  it('shows the fixed message when a system database is requested', async () => {
    vi.mocked(CatalogService.objects).mockRejectedValue(apiError(403, 'database_not_allowed'));
    renderWithSession(<ObjectReviewPage />);
    await chooseDatabase('DWH');
    expect(await screen.findByText('Sistem veritabanları incelenemez.')).toBeInTheDocument();
  });

  it('shows a Turkish error and a refresh button when SQL Server is unreachable', async () => {
    vi.mocked(CatalogService.databases).mockRejectedValue(apiError(503, 'sql_server_unreachable'));
    renderWithSession(<ObjectReviewPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent("SQL Server'a ulaşılamadı.");
    vi.mocked(CatalogService.databases).mockResolvedValue({items: ['DWH'], page: 1, page_size: 500, total: 1});
    fireEvent.click(screen.getByRole('button', {name: 'Listeyi yenile'}));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  });

  it('sends the text, type and date filters to the server', async () => {
    renderWithSession(<ObjectReviewPage />);
    await chooseDatabase('DWH');
    await screen.findByText('dwh_01');
    fireEvent.change(screen.getByLabelText('Ara'), {target: {value: 'load'}});
    fireEvent.change(screen.getByLabelText('Tür'), {target: {value: 'V'}});
    fireEvent.change(screen.getByLabelText('Bu tarihten sonra oluşturulan veya değişen'), {
      target: {value: '2026-02-01'},
    });
    await waitFor(() =>
      expect(vi.mocked(CatalogService.objects)).toHaveBeenLastCalledWith(
        'DWH',
        {q: 'load', type: 'V', fromDate: '2026-02-01', page: 1, pageSize: 100} satisfies ObjectQuery,
        expect.any(AbortSignal),
      ),
    );
  });

  it('keeps selections across databases, counts databases and stops at 50 objects', async () => {
    const stream = vi.spyOn(ReviewService, 'streamObjectReview').mockResolvedValue(undefined);
    renderWithSession(<ObjectReviewPage />);
    await chooseDatabase('DWH');
    await screen.findByText('dwh_01');
    fireEvent.click(screen.getByLabelText('Görünen nesnelerin tümünü seç'));
    expect(screen.getByText('40 / 50 seçili · 1 veritabanı')).toBeInTheDocument();

    await chooseDatabase('MART');
    await screen.findByText('mart_01');
    fireEvent.click(screen.getByLabelText('Görünen nesnelerin tümünü seç'));
    expect(screen.getByText('50 / 50 seçili · 2 veritabanı')).toBeInTheDocument();
    expect(screen.getByText(/En çok 50 nesne seçilebilir/)).toBeInTheDocument();
    expect(screen.getByLabelText('dbo.mart_11 seç')).toBeDisabled();
    fireEvent.click(screen.getByText('mart_12'));
    expect(screen.getByLabelText('dbo.mart_12 seç')).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', {name: 'Seçilen 50 nesneyi incele'}));
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(1));
    const selections = stream.mock.calls[0][0];
    expect(selections).toHaveLength(50);
    expect(selections[0]).toEqual({database: 'DWH', schema: 'dbo', name: 'dwh_01', type_code: 'P'});
    expect(selections.at(-1)).toEqual({database: 'MART', schema: 'dbo', name: 'mart_10', type_code: 'P'});
  });

  it('toggles a row by clicking it and by its checkbox, and clears the selection', async () => {
    renderWithSession(<ObjectReviewPage />);
    await chooseDatabase('DWH');
    const row = (await screen.findByText('dwh_03')).closest('tr');
    fireEvent.click(row!);
    expect(within(row!).getByRole('checkbox')).toBeChecked();
    fireEvent.click(within(row!).getByRole('checkbox'));
    expect(within(row!).getByRole('checkbox')).not.toBeChecked();
    fireEvent.click(row!);
    fireEvent.click(screen.getByRole('button', {name: 'Seçimi temizle'}));
    expect(screen.getByText('0 / 50 seçili · 0 veritabanı')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'İnceleme için en az bir nesne seçin'})).toBeDisabled();
  });
});
