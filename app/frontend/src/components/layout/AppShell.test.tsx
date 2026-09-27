import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '@/App';
import {AuthProvider} from '@/contexts/AuthContext';
import {IntlProvider} from '@/contexts/IntlContext';
import {clearAuth, readAccessToken, writeSession} from '@/lib/authStorage';
import messages from '@/locales/tr.json';
import {AuthService} from '@/services/auth';
import {ConnectionService} from '@/services/connections';
import {testUser, type TestRole} from '@/test/render';
import {MemoryRouter} from 'react-router';

function renderApp(role: TestRole, path = '/') {
  clearAuth();
  writeSession('jwt', testUser(role));
  render(
    <MemoryRouter initialEntries={[path]}>
      <IntlProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </IntlProvider>
    </MemoryRouter>,
  );
}

function menuLinks(): string[] {
  const nav = screen.getByRole('navigation', {name: messages['shell.navigation']});
  return within(nav)
    .getAllByRole('link')
    .map((link) => link.textContent ?? '');
}

function connectionViews(editable: boolean) {
  const environment = editable ? 'local' : 'nonprod';
  vi.spyOn(ConnectionService, 'sql').mockResolvedValue({environment, editable, configured: true});
  vi.spyOn(ConnectionService, 'llm').mockResolvedValue({environment, editable, chat_api: 'openai', model: 'm'});
}

describe('application shell', () => {
  beforeEach(() => connectionViews(true));

  it('offers review pages but no administration to a reviewer and does not ask for settings', async () => {
    renderApp('inceleyici');
    await screen.findByRole('navigation', {name: messages['shell.navigation']});
    expect(menuLinks()).toEqual([
      'Ana sayfa',
      'Nesne incelemesi',
      'SQL betiği incelemesi',
      'İnceleme geçmişi',
      'Yayımlanmış kurallar',
    ]);
    expect(ConnectionService.sql).not.toHaveBeenCalled();
  });

  it('adds rules, editable connections and LLM calls for the rule manager', async () => {
    renderApp('kural-yoneticisi');
    await screen.findByRole('link', {name: 'SQL bağlantısı'});
    expect(menuLinks()).toEqual([
      'Ana sayfa',
      'Nesne incelemesi',
      'SQL betiği incelemesi',
      'İnceleme geçmişi',
      'Yayımlanmış kurallar',
      'Kurallar',
      'SQL bağlantısı',
      'LLM bağlantısı',
      'LLM çağrıları',
    ]);
  });

  it('hides the connection pages when the backend reports them read-only (nonprod)', async () => {
    vi.restoreAllMocks();
    connectionViews(false);
    renderApp('kural-yoneticisi');
    await screen.findByRole('link', {name: 'Kurallar'});
    await waitFor(() => expect(ConnectionService.llm).toHaveBeenCalled());
    expect(menuLinks()).not.toContain('SQL bağlantısı');
    expect(menuLinks()).not.toContain('LLM bağlantısı');
  });

  it('adds user administration for the super admin', async () => {
    renderApp('super_admin');
    await screen.findByRole('link', {name: 'Kullanıcılar'});
    expect(menuLinks()).toContain('Kurallar');
  });

  it('shows the forbidden screen when a reviewer opens the rules address directly', async () => {
    renderApp('inceleyici', '/kurallar');
    expect(await screen.findByRole('heading', {name: messages['access.forbidden.title']})).toBeInTheDocument();
  });

  it('shows the display name and role, and signs out through the server', async () => {
    const logout = vi.spyOn(AuthService, 'logout').mockResolvedValue(undefined);
    renderApp('inceleyici');
    const banner = await screen.findByRole('banner');
    expect(within(banner).getByText('Ayşe İnceleyici')).toBeInTheDocument();
    expect(within(banner).getByText(/· İnceleyici/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: messages['auth.session.signOut']}));
    await screen.findByLabelText(messages['auth.login.username']);
    expect(logout).toHaveBeenCalledTimes(1);
    expect(readAccessToken()).toBeNull();
  });
});
