import {fireEvent, render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import LoginPage from './LoginPage';
import {AuthProvider} from '@/contexts/AuthContext';
import {IntlProvider} from '@/contexts/IntlContext';
import {ApiError} from '@/lib/apiClient';
import messages from '@/locales/tr.json';
import {AuthService} from '@/services/auth';

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
  fireEvent.change(screen.getByLabelText(message('auth.login.username')), {target: {value: 'admin'}});
  fireEvent.change(screen.getByLabelText(message('auth.login.password')), {target: {value: 'secret'}});
  fireEvent.click(screen.getByRole('button', {name: message('auth.login.submit')}));
  return (await screen.findByRole('alert')).textContent;
}

describe('login page', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

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

  it('reports an unavailable service instead of invalid credentials on other failures', async () => {
    vi.spyOn(AuthService, 'login').mockRejectedValue(new TypeError('Failed to fetch'));
    renderLogin();
    expect(await submitAndReadAlert()).toBe(message('auth.login.unavailable'));
  });

  it('offers a language choice only when more than one locale is configured', () => {
    const configured = Object.keys(import.meta.glob('../locales/*.json')).length;
    renderLogin();
    expect(screen.queryByLabelText(message('common.language.label')) !== null).toBe(configured > 1);
  });
});
