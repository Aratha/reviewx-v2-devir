import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {ReviewResultsView} from './ReviewResultsView';
import {ReviewService} from '@/services/reviews';
import {apiError} from '@/test/render';
import {liveResult} from '@/test/reviewEvents';

function renderView(canMark = true, onMarked = vi.fn()) {
  render(<ReviewResultsView results={[liveResult()]} runId="run-1" canMark={canMark} onMarked={onMarked} />);
  return onMarked;
}

describe('review results', () => {
  it('shows statuses in Turkish, with not-applicable counted as compliant, and line references', () => {
    renderView();
    expect(screen.getByText('1 uyumlu · 2 ihlal · 1 değerlendirilemedi')).toBeInTheDocument();
    expect(screen.getAllByText('İhlal var', {selector: '.badge'})).toHaveLength(2);
    expect(screen.getByText('Kapsam dışı', {selector: '.badge'})).toBeInTheDocument();
    expect(screen.getByText('Değerlendirilemedi', {selector: '.badge'})).toBeInTheDocument();
    expect(screen.getByText('Satır 12')).toBeInTheDocument();
    expect(screen.getByText('FROM t WITH (NOLOCK)')).toBeInTheDocument();
  });

  it('marks findings, and failed rule results only when they have no findings', async () => {
    const markFinding = vi.spyOn(ReviewService, 'markFinding').mockResolvedValue({id: 'f-1', false_positive: true, changed_at: null});
    const markRule = vi.spyOn(ReviewService, 'markRuleResult').mockResolvedValue({id: 'rr-3', false_positive: true, changed_at: null});
    const onMarked = renderView();
    expect(screen.queryByRole('checkbox', {name: 'Kural01 kural sonucu yanlış pozitif'})).toBeNull();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Kural01 bulgu 1 yanlış pozitif'}));
    await waitFor(() => expect(onMarked).toHaveBeenCalledWith({kind: 'finding', id: 'f-1'}, true));
    fireEvent.click(screen.getByRole('checkbox', {name: 'Kural04 kural sonucu yanlış pozitif'}));
    await waitFor(() => expect(onMarked).toHaveBeenCalledWith({kind: 'rule', id: 'rr-3'}, true));
    expect(markFinding).toHaveBeenCalledWith('run-1', 'f-1', true);
    expect(markRule).toHaveBeenCalledWith('run-1', 'rr-3', true);
  });

  it('shows the owner-only refusal without changing the mark', async () => {
    vi.spyOn(ReviewService, 'markFinding').mockRejectedValue(apiError(403, 'review_run_not_owner'));
    const onMarked = renderView();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Kural01 bulgu 1 yanlış pozitif'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Yalnız incelemeyi başlatan kişi bu işlemi yapabilir.');
    expect(onMarked).not.toHaveBeenCalled();
  });

  it('offers no mark controls to someone who does not own the run', () => {
    renderView(false);
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('filters rule results by status, severity and text', () => {
    renderView();
    const object = screen.getByRole('region', {name: 'DWH · dbo.usp_load'});
    fireEvent.change(screen.getByLabelText('Kural durumu'), {target: {value: 'FAIL'}});
    expect(within(object).queryByText('Kural03')).toBeNull();
    fireEvent.change(screen.getByLabelText('Önem (ihlallerde)'), {target: {value: 'LOW'}});
    expect(within(object).queryByText('Kural01')).toBeNull();
    expect(within(object).getByText('Kural04')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Süzgeci sıfırla'}));
    fireEvent.change(screen.getByLabelText('Metin ara'), {target: {value: 'nolock'}});
    expect(within(object).getAllByText('Kural01').length).toBeGreaterThan(0);
    expect(within(object).queryByText('Kural04')).toBeNull();
  });

  it('shows an object error with its fixed message', () => {
    render(
      <ReviewResultsView
        results={[liveResult({error_code: 'sql_timeout', error_message: 'ham', rule_results: [], findings: []})]}
        runId="run-1"
        canMark
        onMarked={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('SQL Server zamanında yanıt vermedi.');
  });
});
