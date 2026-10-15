import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '@/App';
import {AuthProvider} from '@/contexts/AuthContext';
import {IntlProvider} from '@/contexts/IntlContext';
import {clearAuth, readAccessToken, writeSession} from '@/lib/authStorage';
import messages from '@/locales/tr.json';
import {AuthService} from '@/services/auth';
import {ConnectionService} from '@/services/connections';
import {ReviewService} from '@/services/reviews';
import {RuleProposalService} from '@/services/ruleProposals';
import {ScheduledReviewService} from '@/services/scheduledReviews';
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

function railLinks(): string[] {
  const rail = screen.getByRole('navigation', {name: 'Yönetim bölümleri'});
  return within(rail)
    .getAllByRole('link')
    .map((link) => link.textContent ?? '');
}

function openRail(): Promise<HTMLElement> {
  return screen.findByRole('navigation', {name: 'Yönetim bölümleri'});
}

function pageViews() {
  vi.spyOn(ReviewService, 'runs').mockResolvedValue({items: [], page: 1, page_size: 5, total: 0});
  vi.spyOn(ScheduledReviewService, 'settings').mockResolvedValue({max_concurrent_runs: 2});
  vi.spyOn(ScheduledReviewService, 'emailStatus').mockResolvedValue({
    scheduler_enabled: true,
    smtp_configured: false,
    smtp_security: 'starttls',
    allowed_domains: ['kurum.example'],
    suggested_recipient: null,
  });
}

function connectionViews(editable: boolean) {
  const environment = editable ? 'local' : 'nonprod';
  const managed_by = editable ? 'local_process' : 'deployment';
  vi.spyOn(ConnectionService, 'sql').mockResolvedValue({environment, editable, configured: true, managed_by});
  vi.spyOn(ConnectionService, 'llm').mockResolvedValue({environment, editable, chat_api: 'openai', model: 'm'});
  proposalMenu(false, false);
}

function proposalMenu(canPropose: boolean, canDecide: boolean, pending = 0) {
  vi.spyOn(RuleProposalService, 'capabilities').mockResolvedValue({can_propose: canPropose, can_decide: canDecide});
  vi.spyOn(RuleProposalService, 'list').mockResolvedValue({items: [], page: 1, page_size: 1, total: pending});
}

describe('application shell', () => {
  beforeEach(() => {
    connectionViews(true);
    pageViews();
  });

  it('offers a reviewer four places and no administration, without asking for settings', async () => {
    renderApp('inceleyici');
    await screen.findByRole('navigation', {name: messages['shell.navigation']});
    expect(menuLinks()).toEqual(['Ana sayfa', 'İnceleme', 'Geçmiş', 'Kural kitaplığı']);
    expect(ConnectionService.sql).not.toHaveBeenCalled();
  });

  it('gives the super admin every administration screen on one Yönetim page', async () => {
    renderApp('super_admin', '/yonetim');
    await screen.findByRole('link', {name: 'SQL bağlantısı'});
    expect(menuLinks()).toEqual(['Ana sayfa', 'İnceleme', 'Geçmiş', 'Kural kitaplığı', 'Yönetim']);
    expect(railLinks()).toEqual([
      'Genel durum',
      'Kurallar',
      'SQL bağlantısı',
      'LLM bağlantısı',
      'LLM çağrıları',
      'Zamanlama ve e-posta',
      'Kullanıcılar',
    ]);
    expect(screen.getByRole('heading', {name: 'Yönetim', level: 1})).toBeInTheDocument();
  });

  it('hides the connection sections when the backend reports them read-only (nonprod)', async () => {
    vi.restoreAllMocks();
    pageViews();
    connectionViews(false);
    renderApp('super_admin', '/yonetim');
    await openRail();
    await waitFor(() => expect(ConnectionService.llm).toHaveBeenCalled());
    expect(railLinks()).toEqual(['Genel durum', 'Kurallar', 'LLM çağrıları', 'Zamanlama ve e-posta', 'Kullanıcılar']);
  });

  it('offers the SQL connection section in nonprod only to the super admin who may edit it', async () => {
    // sql-server-connection Requirement 5: the backend reports editable only to the super admin.
    vi.restoreAllMocks();
    proposalMenu(false, false);
    pageViews();
    vi.spyOn(ConnectionService, 'llm').mockResolvedValue({
      environment: 'nonprod',
      editable: false,
      chat_api: 'openai',
      model: 'm',
    });
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue({
      environment: 'nonprod',
      editable: true,
      configured: false,
      managed_by: 'super_admin',
      password_set: false,
    });
    renderApp('super_admin', '/yonetim');
    await screen.findByRole('link', {name: 'SQL bağlantısı'});
    expect(railLinks()).not.toContain('LLM bağlantısı');
    expect(railLinks()).toContain('Kullanıcılar');
    expect(railLinks()).toContain('Zamanlama ve e-posta');
  });

  it('adds user administration and the e-mail state for the super admin', async () => {
    renderApp('super_admin', '/yonetim');
    await screen.findByRole('link', {name: 'Kullanıcılar'});
    expect(railLinks()).toContain('Kurallar');
    expect(await screen.findByText('E-posta yapılandırılmadı')).toBeInTheDocument();
  });

  it('offers "Kural önerilerim" in the rule library to a user the super admin allowed to propose', async () => {
    proposalMenu(true, false);
    renderApp('inceleyici', '/kural-onerilerim');
    const library = await screen.findByRole('navigation', {name: 'Kural kitaplığı'});
    expect(await within(library).findByRole('link', {name: 'Kural önerilerim'})).toHaveAttribute('aria-current', 'page');
    expect(menuLinks()).not.toContain('Yönetim');
  });

  it('shows the pending count on Yönetim and on "Kural onayları" to the super admin', async () => {
    proposalMenu(true, true, 3);
    renderApp('super_admin', '/yonetim');
    const nav = await screen.findByRole('navigation', {name: messages['shell.navigation']});
    const link = await within(nav).findByRole('link', {name: /Yönetim/});
    expect(await within(link).findByLabelText('3 bekleyen')).toHaveTextContent('3');
    const rail = await openRail();
    const approvals = await within(rail).findByRole('link', {name: /Kural onayları/});
    expect(await within(approvals).findByLabelText('3 bekleyen')).toHaveTextContent('3');
  });

  it.each(['/kural-onaylari', '/kurallar', '/yonetim', '/yonetim/onaylar', '/ayarlar/llm'])('shows the forbidden screen when a user opens %s', async (path) => {
    renderApp('inceleyici', path);
    expect(await screen.findByRole('heading', {name: messages['access.forbidden.title']})).toBeInTheDocument();
  });

  it('takes an old administration address to its section on the Yönetim page', async () => {
    renderApp('super_admin', '/ayarlar/zamanlama');
    expect(await screen.findByRole('heading', {name: 'Zamanlama ve e-posta', level: 2})).toBeInTheDocument();
    const rail = await openRail();
    expect(within(rail).getByRole('link', {name: 'Zamanlama ve e-posta'})).toHaveAttribute('aria-current', 'page');
  });

  it('opens quick navigation with Ctrl+K and goes to the chosen place', async () => {
    renderApp('super_admin');
    await screen.findByRole('navigation', {name: messages['shell.navigation']});
    await screen.findByRole('link', {name: /Yönetim/});
    fireEvent.keyDown(window, {key: 'k', ctrlKey: true});
    const input = await screen.findByRole('combobox', {name: 'Gidilecek sayfa'});
    fireEvent.change(input, {target: {value: 'e-posta'}});
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Zamanlama ve e-posta');
    fireEvent.keyDown(input, {key: 'Enter'});
    expect(await screen.findByRole('heading', {name: 'Zamanlama ve e-posta', level: 2})).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the display name and role, and signs out through the server', async () => {
    const logout = vi.spyOn(AuthService, 'logout').mockResolvedValue(undefined);
    renderApp('inceleyici');
    const banner = await screen.findByRole('banner');
    expect(within(banner).getByText('Ayşe İnceleyici')).toBeInTheDocument();
    expect(within(banner).getByText(/· Kullanıcı/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: messages['auth.session.signOut']}));
    await screen.findByLabelText(messages['auth.login.username']);
    expect(logout).toHaveBeenCalledTimes(1);
    expect(readAccessToken()).toBeNull();
  });
});
