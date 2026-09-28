import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import LoginPage from './LoginPage';
import {AuthProvider} from '@/contexts/AuthContext';
import {IntlProvider} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import {config} from '@/lib/config';
import messages from '@/locales/tr.json';
import {AuthService} from '@/services/auth';
import {clearAuth, readAccessToken} from '@/lib/authStorage';
import {testUser} from '@/test/render';

function message(key: string): string {
  const value = (messages as Record<string, unknown>)[key];
  if (typeof value !== 'string') throw new Error(`missing catalog key ${key}`);
  return value;
}

function renderLogin() {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <IntlProvider>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </IntlProvider>
    </MemoryRouter>,
  );
}

async function submitAndReadAlert(): Promise<string | null> {
  fireEvent.change(await screen.findByLabelText(message('auth.login.username')), {target: {value: 'admin'}});
  fireEvent.change(screen.getByLabelText(message('auth.login.password')), {target: {value: 'secret'}});
  fireEvent.click(screen.getByRole('button', {name: message('auth.login.submit')}));
  return (await screen.findByRole('alert')).textContent;
}

describe('login page', () => {
  beforeEach(() => {
    clearAuth();
    // No refresh cookie: restoring the session on load fails and the form is shown.
    vi.spyOn(AuthService, 'refresh').mockRejectedValue(new ApiError(401, 'expired', 'session_expired', true));
  });

  it('reports invalid credentials for a 401', async () => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new ApiError(401, 'Incorrect username or password'));
    renderLogin();
    expect(await submitAndReadAlert()).toBe(message('auth.login.invalidCredentials'));
  });

  it('reports the lockout distinctly for a 429', async () => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new ApiError(429, 'Too many failed login attempts'));
    renderLogin();
    expect(await submitAndReadAlert()).toBe(message('auth.login.tooManyAttempts'));
  });

  it.each([
    [403, 'user_inactive', 'auth.login.inactive'],
    [409, 'identity_conflict', 'auth.login.identityConflict'],
    [503, 'directory_unavailable', 'auth.login.directoryUnavailable'],
  ])('reports %s %s with its own message', async (status, code, key) => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new ApiError(status, 'x', code));
    renderLogin();
    expect(await submitAndReadAlert()).toBe(message(key));
  });

  it('asks for the corporate user name and password', async () => {
    renderLogin();
    expect(await screen.findByText(message('auth.login.subtitle'))).toBeInTheDocument();
    expect(message('auth.login.subtitle')).toMatch(/Kurum kullanıcı adınız ve parolanız/);
  });

  it('pairs the sign-in form with a panel naming what the product does', async () => {
    renderLogin();
    await screen.findByLabelText(message('auth.login.username'));
    expect(screen.getByRole('heading', {level: 1}).textContent).toBe(message('auth.login.title'));
    expect(screen.getByRole('heading', {level: 2}).textContent).toBe(config.productName);
    expect(screen.getAllByRole('heading', {level: 3}).map((heading) => heading.textContent)).toEqual(
      ['objectReview', 'scriptReview', 'rules', 'llm', 'history'].map((name) =>
        message(`auth.login.hero.${name}.title`),
      ),
    );
    expect(screen.getByText(message('auth.login.help.firstLogin'))).toBeInTheDocument();
  });

  it('keeps the access token in memory only after a successful login', async () => {
    vi.spyOn(AuthService, 'login').mockResolvedValue({
      access_token: 'jwt-login',
      token_type: 'bearer',
      expires_in: 900,
      user: testUser('inceleyici'),
    });
    renderLogin();
    fireEvent.change(await screen.findByLabelText(message('auth.login.username')), {target: {value: 'ayse'}});
    fireEvent.change(screen.getByLabelText(message('auth.login.password')), {target: {value: 'secret'}});
    fireEvent.click(screen.getByRole('button', {name: message('auth.login.submit')}));
    await waitFor(() => expect(readAccessToken()).toBe('jwt-login'));
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('reports an unavailable service instead of invalid credentials on other failures', async () => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new TypeError('Failed to fetch'));
    renderLogin();
    expect(await submitAndReadAlert()).toBe(message('auth.login.unavailable'));
  });

  it('offers a language choice only when more than one locale is configured', async () => {
    const configured = Object.keys(import.meta.glob('../locales/*.json')).length;
    renderLogin();
    await screen.findByLabelText(message('auth.login.username'));
    expect(screen.queryByLabelText(message('common.language.label')) !== null).toBe(configured > 1);
  });
});
