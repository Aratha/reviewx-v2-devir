import {fireEvent, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import ScriptReviewPage, {DATA_NOTE, TOO_LONG_MESSAGE} from './ScriptReviewPage';
import {ReviewService} from '@/services/reviews';
import {deferred, renderWithSession} from '@/test/render';

function button() {
  return screen.getByRole('button', {name: /Kurallara göre incele|İnceleniyor/});
}

describe('script review page', () => {
  it('shows the fixed data note next to the text field', () => {
    renderWithSession(<ScriptReviewPage />);
    expect(screen.getByText(DATA_NOTE)).toBeInTheDocument();
    expect(screen.getByLabelText('SQL')).toHaveAccessibleDescription(expect.stringContaining(DATA_NOTE));
  });

  it('counts characters and keeps the button closed for empty text', () => {
    renderWithSession(<ScriptReviewPage />);
    expect(screen.getByText('Metin yok')).toBeInTheDocument();
    expect(button()).toBeDisabled();
    fireEvent.change(screen.getByLabelText('SQL'), {target: {value: '   \n  '}});
    expect(button()).toBeDisabled();
    fireEvent.change(screen.getByLabelText('SQL'), {target: {value: '  SELECT 1  '}});
    expect(screen.getByText('8 / 120.000 karakter')).toBeInTheDocument();
    expect(button()).toBeEnabled();
  });

  it('accepts 120,000 characters and refuses 120,001 with the limit message', () => {
    renderWithSession(<ScriptReviewPage />);
    fireEvent.change(screen.getByLabelText('SQL'), {target: {value: 'a'.repeat(120_000)}});
    expect(button()).toBeEnabled();
    expect(screen.queryByText(TOO_LONG_MESSAGE)).toBeNull();
    fireEvent.change(screen.getByLabelText('SQL'), {target: {value: 'a'.repeat(120_001)}});
    expect(button()).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent(TOO_LONG_MESSAGE);
  });

  it('limits the label to 200 characters', () => {
    renderWithSession(<ScriptReviewPage />);
    expect(screen.getByLabelText('Sonuçlarda görünecek ad (isteğe bağlı)')).toHaveAttribute('maxLength', '200');
  });

  it('sends the trimmed text and label, locks the fields while running, and stores nothing in the browser', async () => {
    const running = deferred<void>();
    const stream = vi.spyOn(ReviewService, 'streamScriptReview').mockReturnValue(running.promise);
    renderWithSession(<ScriptReviewPage />);
    fireEvent.change(screen.getByLabelText('Sonuçlarda görünecek ad (isteğe bağlı)'), {
      target: {value: ' yükleme '},
    });
    fireEvent.change(screen.getByLabelText('SQL'), {target: {value: '\nSELECT 1\n'}});
    fireEvent.click(button());
    await waitFor(() => expect(stream).toHaveBeenCalledWith('SELECT 1', 'yükleme', expect.any(AbortSignal), expect.any(Function)));
    expect(screen.getByLabelText('SQL')).toBeDisabled();
    expect(screen.getByLabelText('Sonuçlarda görünecek ad (isteğe bağlı)')).toBeDisabled();
    expect(button()).toBeDisabled();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    running.resolve();
  });
});
