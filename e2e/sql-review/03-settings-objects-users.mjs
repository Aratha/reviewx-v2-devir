import {withBrowser, baseUrl, accounts, message, signIn, apiStatus} from '../shared/harness.mjs';

/**
 * sql-server-connection Acceptance 4 (the parts without a reachable SQL Server), object-review
 * Requirement 1 error state, llm-connection Requirement 11 list and directory-login Acceptance 2
 * user administration on the local stack. Every change is reverted in `finally`.
 */
await withBrowser('connection pages, object review errors and user administration', async ({page, assert, newPage}) => {
  const manager = page;
  await signIn(manager, accounts.ruleManager);
  const nav = manager.getByRole('navigation', {name: message('shell.navigation')});

  // Local environment: both connection pages are in the menu and editable.
  await nav.getByRole('link', {name: 'SQL bağlantısı'}).click();
  await manager.getByRole('heading', {name: 'SQL bağlantısı', level: 1}).waitFor();
  await manager.getByText(/yalnız çalışan sunucu sürecine uygulanır/).waitFor();
  assert.equal(await manager.getByText(/backend\/\.env dosyasına yazılır/).count(), 0);
  // Test without saving: the local network has no route to SQL Server, so a fixed class message
  // appears and nothing is stored.
  await manager.getByLabel('Sunucu adı').fill('sql-server.invalid');
  await manager.getByLabel('Kullanıcı adı').fill('okuyucu');
  await manager.getByLabel('Parola').fill('yalniz-test-icin-parola');
  await manager.getByRole('button', {name: 'Bağlantıyı test et'}).click();
  await manager
    .getByRole('alert')
    .filter({hasText: /SQL Server'a ulaşılamadı\.|SQL Server zamanında yanıt vermedi\.|SQL Server girişi reddedildi\./})
    .waitFor({timeout: 60_000});
  const stored = await apiStatus(manager, '/sql-connection');
  assert.equal(stored.body.configured, false);
  assert.equal(stored.body.server, '');

  await nav.getByRole('link', {name: 'LLM bağlantısı'}).click();
  await manager.getByRole('heading', {name: 'LLM bağlantısı', level: 1}).waitFor();
  assert.equal(await manager.getByText(/vekil|proxy/i).count(), 0);

  await nav.getByRole('link', {name: 'LLM çağrıları'}).click();
  await manager.getByRole('heading', {name: 'LLM çağrıları', level: 1}).waitFor();
  await manager.getByRole('heading', {name: /Çağrı özetleri/}).waitFor();

  // Reviewer: without a SQL Server connection the object page explains it and offers a retry.
  const reviewer = await newPage();
  await signIn(reviewer, accounts.reviewer);
  const reviewerNav = reviewer.getByRole('navigation', {name: message('shell.navigation')});
  for (const name of ['SQL bağlantısı', 'LLM bağlantısı', 'LLM çağrıları', 'Kullanıcılar'])
    assert.equal(await reviewerNav.getByRole('link', {name}).count(), 0, `${name} is hidden from the reviewer`);
  assert.equal((await apiStatus(reviewer, '/sql-connection')).status, 403);
  await reviewerNav.getByRole('link', {name: 'Nesne incelemesi'}).click();
  await reviewer.getByRole('alert').filter({hasText: 'SQL Server bağlantısı yapılandırılmamış.'}).waitFor();
  await reviewer.getByRole('button', {name: 'Listeyi yenile'}).waitFor();
  assert.equal(await reviewer.getByRole('button', {name: 'İnceleme için en az bir nesne seçin'}).isDisabled(), true);

  // Super admin: change the second reviewer's role and status, then restore both.
  const admin = await newPage();
  await signIn(admin, accounts.superAdmin);
  await admin.getByRole('navigation', {name: message('shell.navigation')}).getByRole('link', {name: 'Kullanıcılar'}).click();
  const target = accounts.secondReviewer.username;
  const other = await newPage();
  await signIn(other, accounts.secondReviewer);
  const role = admin.getByRole('combobox', {name: `${target} rolü`});
  try {
    await role.selectOption('kural-yoneticisi');
    await admin.getByText(`${target} için rol “Kural yöneticisi” oldu.`).waitFor();
    // The role change closed the user's refresh sessions (directory-login Requirement 5).
    const refreshed = await other.evaluate(async () => (await fetch('/api/dwhcodereview/v1/auth/refresh', {method: 'POST'})).status);
    assert.equal(refreshed, 401);
    await admin.getByRole('button', {name: `${target} hesabını pasifleştir`}).click();
    await admin.getByText(`${target} hesabı pasifleştirildi.`).waitFor();
    await other.goto(baseUrl + '/login');
    await other.getByLabel(message('auth.login.username')).fill(target);
    await other.getByLabel(message('auth.login.password')).fill(accounts.secondReviewer.password);
    await other.getByRole('button', {name: message('auth.login.submit')}).click();
    await other.getByRole('alert').filter({hasText: message('auth.login.inactive')}).waitFor();
  } finally {
    if (await admin.getByRole('button', {name: `${target} hesabını etkinleştir`}).count()) {
      await admin.getByRole('button', {name: `${target} hesabını etkinleştir`}).click();
      await admin.getByText(`${target} hesabı etkinleştirildi.`).waitFor();
    }
    if ((await role.inputValue()) !== 'inceleyici') {
      await role.selectOption('inceleyici');
      await admin.getByText(`${target} için rol “İnceleyici” oldu.`).waitFor();
    }
  }
}, {
  // The unconfigured SQL Server connection answers the database list with 503 by contract.
  expectedServerErrors: [/^503 GET .*\/api\/dwhcodereview\/v1\/databases\?/],
});
