import {fireEvent, screen, waitFor} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import LlmConnectionPage from './LlmConnectionPage';
import SqlConnectionPage from './SqlConnectionPage';
import {ConnectionService} from '@/services/connections';
import {apiError, renderWithSession} from '@/test/render';
import type {LlmConnectionView, SqlConnectionView} from '@/types/sqlReview';

const sqlLocal: SqlConnectionView = {
  environment: 'local',
  editable: true,
  configured: true,
  managed_by: 'local_process',
  server: 'sql.local',
  port: 1433,
  user: 'reader',
  encrypt: true,
  trust_server_certificate: false,
  password_set: true,
  allowed_databases: ['DWH'],
};

// nonprod without a deployment connection: the super admin saves it in the application.
const sqlStored: SqlConnectionView = {
  environment: 'nonprod',
  editable: true,
  configured: true,
  managed_by: 'super_admin',
  server: 'sql-dwh.kurum.local',
  port: 1433,
  user: 'dwh_okuyucu',
  encrypt: true,
  trust_server_certificate: false,
  password_set: true,
  allowed_databases: ['DWH_Risk', 'DWH_Sales'],
};

const llmLocal: LlmConnectionView = {
  environment: 'local',
  editable: true,
  chat_api: 'openai',
  base_url: 'http://10.0.0.5:1234/v1',
  chat_url: null,
  resolved_chat_url: 'http://10.0.0.5:1234/v1/chat/completions',
  model: 'qwen',
  api_key_set: false,
};

describe('SQL connection page', () => {
  it('shows only the deployment note and status when settings are not editable (nonprod)', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue({
      environment: 'nonprod',
      editable: false,
      configured: true,
      managed_by: 'deployment',
    });
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    expect(await screen.findByText('Bu ortamda bağlantı ayarları dağıtımla yönetilir.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Sunucu adı')).toBeNull();
    expect(screen.queryByRole('button', {name: 'Kaydet'})).toBeNull();
  });

  it('tells a rule manager that only the application administrator edits the nonprod connection', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue({
      environment: 'nonprod',
      editable: false,
      configured: false,
      managed_by: 'super_admin',
    });
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    expect(
      await screen.findByText('Bu ortamda SQL bağlantısını yalnız uygulama yöneticisi düzenleyebilir.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Bu ortamda bağlantı ayarları dağıtımla yönetilir.')).toBeNull();
    expect(screen.getByText('Yapılandırılmamış')).toBeInTheDocument();
    expect(screen.queryByLabelText('Sunucu adı')).toBeNull();
    expect(screen.queryByRole('button', {name: 'Kaydet'})).toBeNull();
  });

  it('lets the super admin edit the nonprod connection and its allowed databases, with encryption fixed', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlStored);
    const saveSql = vi
      .spyOn(ConnectionService, 'saveSql')
      .mockResolvedValue({...sqlStored, allowed_databases: ['DWH_Risk', 'DWH_Stage']});
    renderWithSession(<SqlConnectionPage />, {role: 'super_admin'});
    expect(await screen.findByText(/parola şifrelenerek saklanır/)).toBeInTheDocument();
    expect(screen.queryByText(/yalnız çalışan sunucu sürecine uygulanır/)).toBeNull();
    expect(screen.queryByLabelText('Şifreli bağlantı (Encrypt)')).toBeNull();
    expect(screen.queryByLabelText(/TrustServerCertificate/)).toBeNull();
    expect(screen.getByText(/her zaman şifrelidir ve sunucu sertifikası doğrulanır/)).toBeInTheDocument();
    const allowed = screen.getByLabelText('İzinli veritabanları');
    expect(allowed).toHaveValue('DWH_Risk\nDWH_Sales');
    fireEvent.change(allowed, {target: {value: ' DWH_Risk \n\nDWH_Stage, '}});
    fireEvent.click(screen.getByRole('button', {name: 'Kaydet'}));
    await screen.findByText('SQL bağlantı ayarları kaydedildi.');
    expect(saveSql).toHaveBeenCalledWith({
      server: 'sql-dwh.kurum.local',
      port: 1433,
      user: 'dwh_okuyucu',
      allowed_databases: ['DWH_Risk', 'DWH_Stage'],
    });
  });

  it('does not save a nonprod connection without business databases or with a system database', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlStored);
    const saveSql = vi.spyOn(ConnectionService, 'saveSql');
    const testSql = vi
      .spyOn(ConnectionService, 'testSql')
      .mockResolvedValue({ok: true, code: null, message: 'ok', databases: ['DWH_Risk', 'DWH_Sales', 'Scratch']});
    renderWithSession(<SqlConnectionPage />, {role: 'super_admin'});
    const allowed = await screen.findByLabelText('İzinli veritabanları');

    fireEvent.change(allowed, {target: {value: 'DWH_Risk\nMaster'}});
    expect(
      screen.getByText('Sistem veritabanları (master, tempdb, model, msdb) incelemeye açılamaz.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Kaydet'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Bağlantıyı test et'})).toBeDisabled();

    fireEvent.change(allowed, {target: {value: '  '}});
    expect(screen.getByText('Kaydetmek için en az bir veritabanı adı yazın.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Kaydet'})).toBeDisabled();
    // Before the list is chosen the test still runs and shows what can be allowed.
    fireEvent.click(screen.getByRole('button', {name: 'Bağlantıyı test et'}));
    expect(await screen.findByText('Bağlantı başarılı: 3 veritabanı bulundu.')).toBeInTheDocument();
    expect(testSql).toHaveBeenCalledWith({
      server: 'sql-dwh.kurum.local',
      port: 1433,
      user: 'dwh_okuyucu',
      allowed_databases: [],
    });
    expect(saveSql).not.toHaveBeenCalled();
  });

  it('shows the fixed message when the server refuses the allowed databases', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlStored);
    vi.spyOn(ConnectionService, 'saveSql').mockRejectedValue(apiError(422, 'sql_allowed_databases_invalid'));
    renderWithSession(<SqlConnectionPage />, {role: 'super_admin'});
    fireEvent.click(await screen.findByRole('button', {name: 'Kaydet'}));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'İzinli veritabanı listesi boş olamaz ve sistem veritabanı (master, tempdb, model, msdb) içeremez.',
    );
  });

  it('keeps the allowed databases read-only and the encryption choices editable in the local environment', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    expect(await screen.findByText('İzinli veritabanları: DWH')).toBeInTheDocument();
    expect(screen.queryByLabelText('İzinli veritabanları')).toBeNull();
    expect(screen.getByLabelText('Şifreli bağlantı (Encrypt)')).toBeChecked();
    expect(screen.getByLabelText(/TrustServerCertificate/)).not.toBeChecked();
  });

  it('says values apply to the running process only and never mentions writing backend/.env', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    expect(await screen.findByText(/yalnız çalışan sunucu sürecine uygulanır/)).toBeInTheDocument();
    expect(screen.queryByText(/backend\/\.env dosyasına yazılır/)).toBeNull();
    expect(screen.getByLabelText('Parola')).toHaveValue('');
    expect(screen.getByText('Kayıtlı parola var. Boş bırakırsanız korunur.')).toBeInTheDocument();
  });

  it('tests without saving and shows the count and the first 8 databases', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    const testSql = vi.spyOn(ConnectionService, 'testSql').mockResolvedValue({
      ok: true,
      code: null,
      message: 'ok',
      databases: Array.from({length: 10}, (_, index) => `DB${index + 1}`),
    });
    const saveSql = vi.spyOn(ConnectionService, 'saveSql');
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    fireEvent.click(await screen.findByRole('button', {name: 'Bağlantıyı test et'}));
    expect(await screen.findByText('Bağlantı başarılı: 10 veritabanı bulundu.')).toBeInTheDocument();
    expect(screen.getByText('İlk veritabanları: DB1, DB2, DB3, DB4, DB5, DB6, DB7, DB8…')).toBeInTheDocument();
    expect(testSql.mock.calls[0][0]).not.toHaveProperty('password');
    expect(saveSql).not.toHaveBeenCalled();
  });

  it('shows the fixed message of a failed test class', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    vi.spyOn(ConnectionService, 'testSql').mockResolvedValue({
      ok: false,
      code: 'password_required',
      message: 'raw',
      databases: [],
    });
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    fireEvent.click(await screen.findByRole('button', {name: 'Bağlantıyı test et'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Bağlantıyı test etmek için parolayı girin.');
  });

  it('keeps the stored password unless a new one is typed or removal is chosen', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    const saveSql = vi.spyOn(ConnectionService, 'saveSql').mockResolvedValue({...sqlLocal, password_set: false});
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    fireEvent.click(await screen.findByLabelText('Kayıtlı parolayı kaldır'));
    fireEvent.click(screen.getByRole('button', {name: 'Kaydet'}));
    await screen.findByText('SQL bağlantı ayarları kaydedildi.');
    expect(saveSql).toHaveBeenCalledWith({
      server: 'sql.local',
      port: 1433,
      user: 'reader',
      encrypt: true,
      trust_server_certificate: false,
      password: '',
    });
    expect(screen.getByText('Kayıtlı parola yok.')).toBeInTheDocument();
  });

  it('rejects an out-of-range port before sending', async () => {
    vi.spyOn(ConnectionService, 'sql').mockResolvedValue(sqlLocal);
    renderWithSession(<SqlConnectionPage />, {role: 'kural-yoneticisi'});
    fireEvent.change(await screen.findByLabelText('Port'), {target: {value: '70000'}});
    expect(screen.getByText('Port 1 ile 65535 arasında bir sayı olmalıdır.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Kaydet'})).toBeDisabled();
  });
});

describe('LLM connection page', () => {
  it('shows format and model read-only when not editable (nonprod)', async () => {
    vi.spyOn(ConnectionService, 'llm').mockResolvedValue({
      environment: 'nonprod',
      editable: false,
      chat_api: 'openai',
      model: '/data/models--Qwen',
    });
    renderWithSession(<LlmConnectionPage />, {role: 'kural-yoneticisi'});
    expect(await screen.findByText('Bu ortamda bağlantı ayarları dağıtımla yönetilir.')).toBeInTheDocument();
    expect(screen.getByText('/data/models--Qwen')).toBeInTheDocument();
    expect(screen.queryByLabelText('Temel adres')).toBeNull();
  });

  it('saves format, addresses and model; an empty key field keeps the stored key', async () => {
    vi.spyOn(ConnectionService, 'llm').mockResolvedValue(llmLocal);
    const save = vi.spyOn(ConnectionService, 'saveLlm').mockResolvedValue({...llmLocal, model: 'yeni'});
    renderWithSession(<LlmConnectionPage />, {role: 'kural-yoneticisi'});
    expect(await screen.findByText('http://10.0.0.5:1234/v1/chat/completions')).toBeInTheDocument();
    expect(screen.queryByText(/vekil|proxy/i)).toBeNull();
    fireEvent.change(screen.getByLabelText('Model'), {target: {value: 'yeni'}});
    fireEvent.click(screen.getByRole('button', {name: 'Kaydet'}));
    await screen.findByText('LLM bağlantı ayarları kaydedildi.');
    expect(save).toHaveBeenCalledWith({
      chat_api: 'openai',
      base_url: 'http://10.0.0.5:1234/v1',
      chat_url: '',
      model: 'yeni',
    });
  });

  it('shows the class message when the address is outside the internal network', async () => {
    vi.spyOn(ConnectionService, 'llm').mockResolvedValue(llmLocal);
    vi.spyOn(ConnectionService, 'saveLlm').mockRejectedValue(apiError(422, 'network_policy_denied'));
    renderWithSession(<LlmConnectionPage />, {role: 'kural-yoneticisi'});
    fireEvent.change(await screen.findByLabelText('Temel adres'), {target: {value: 'https://api.example.com/v1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Kaydet'}));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('LLM adresi kurum içi ağda değil; bu adrese istek gönderilemez.'),
    );
  });
});
