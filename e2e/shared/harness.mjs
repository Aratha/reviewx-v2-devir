import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdir} from 'node:fs/promises';

export const baseUrl = (process.env.APP_E2E_BASE || 'http://localhost:8080').replace(/\/$/, '');
export const apiPrefix = '/api/dwhcodereview/v1';
export const username = process.env.APP_E2E_SUPER_ADMIN_USER || process.env.DWHCODEREVIEW_SUPER_ADMIN_USER;
export const password = process.env.APP_E2E_SUPER_ADMIN_PASS || process.env.DWHCODEREVIEW_SUPER_ADMIN_PASS;

/**
 * Process-supplied local accounts; nothing is stored in the repository. Reviewer and rule-manager
 * accounts come from `scripts/create-local-user.sh --role ...` while the directory is disabled.
 */
export const accounts = {
  superAdmin: {username, password},
  reviewer: {username: process.env.APP_E2E_REVIEWER_USER, password: process.env.APP_E2E_REVIEWER_PASS},
  secondReviewer: {
    username: process.env.APP_E2E_SECOND_REVIEWER_USER,
    password: process.env.APP_E2E_SECOND_REVIEWER_PASS,
  },
  ruleManager: {username: process.env.APP_E2E_RULE_MANAGER_USER, password: process.env.APP_E2E_RULE_MANAGER_PASS},
};

const primaryCatalog = JSON.parse(
  readFileSync(new URL('../../app/frontend/src/locales/tr.json', import.meta.url), 'utf8'),
);

/** Resolve a UI text from the primary locale catalog so selectors follow the configured language. */
export function message(key) {
  const value = key in primaryCatalog
    ? primaryCatalog[key]
    : key.split('.').reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), primaryCatalog);
  assert.equal(typeof value, 'string', `missing primary locale message ${key}`);
  return value;
}

/** Sign in through the real login form and wait for the signed-in shell. */
export async function signIn(page, account) {
  assert.ok(account.username && account.password, 'account credentials are required');
  await page.goto(baseUrl + '/login');
  await page.getByLabel(message('auth.login.username')).fill(account.username);
  await page.getByLabel(message('auth.login.password')).fill(account.password);
  await page.getByRole('button', {name: message('auth.login.submit')}).click();
  await page.getByRole('navigation', {name: message('shell.navigation')}).waitFor();
}

/**
 * A fresh access token for API assertions, obtained the way the page does: by rotating the
 * HttpOnly refresh cookie. The token is never read from browser storage (there is none).
 */
export async function sessionToken(page) {
  return page.evaluate(async (prefix) => {
    const response = await fetch(prefix + '/auth/refresh', {method: 'POST', credentials: 'same-origin'});
    const body = await response.json();
    return {token: body.access_token, tenant: body.user.tenant_id};
  }, apiPrefix);
}

/** Call the API from the page with a bearer token (for authorization checks). */
export async function apiStatus(page, path, {method = 'GET', body} = {}) {
  const {token, tenant} = await sessionToken(page);
  return page.evaluate(
    async ({prefix, path, method, body, token, tenant}) => {
      const response = await fetch(prefix + path, {
        method,
        headers: {
          Authorization: 'Bearer ' + token,
          'x-tenant-id': tenant,
          ...(body === undefined ? {} : {'Content-Type': 'application/json'}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await response.text();
      let json = null;
      try {
        json = JSON.parse(text);
      } catch {
        json = null;
      }
      return {status: response.status, body: json};
    },
    {prefix: apiPrefix, path, method, body, token, tenant},
  );
}

// Chromium logs every non-2xx fetch as "Failed to load resource". Those lines only repeat the
// HTTP status: 4xx answers such as the 401 of a session restore without a refresh cookie are part
// of the contract, and every 5xx is checked from the response itself below, with its URL.
const NETWORK_STATUS_LOG = /^Failed to load resource: the server responded with a status of \d{3}/;

async function monitoredPage(context, allowedOrigin, findings, expectedServerErrors) {
  const page = await context.newPage();
  page.on('console', (entry) => {
    if (entry.type() === 'error' && !NETWORK_STATUS_LOG.test(entry.text())) findings.consoleErrors.push(entry.text());
  });
  page.on('pageerror', (error) => {
    findings.pageErrors.push(error.stack || error.message || String(error));
  });
  page.on('response', (response) => {
    const responseUrl = response.url();
    if (new URL(responseUrl).origin === allowedOrigin && response.status() >= 500) {
      const entry = `${response.status()} ${response.request().method()} ${responseUrl}`;
      if (!expectedServerErrors.some((pattern) => pattern.test(entry))) findings.serverErrors.push(entry);
    }
  });
  return page;
}

/**
 * Run `scenario` in a fresh browser. `expectedServerErrors` lists patterns of
 * "<status> <method> <url>" 5xx answers the scenario asserts on purpose (for example a 503 from
 * an unconfigured SQL Server connection); any other 5xx fails the scenario.
 */
export async function withBrowser(name, scenario, {expectedServerErrors = []} = {}) {
  assert.ok(username, 'APP_E2E_SUPER_ADMIN_USER is required');
  assert.ok(password, 'APP_E2E_SUPER_ADMIN_PASS is required');
  const browser = await chromium.launch({headless: true});
  const allowedOrigin = new URL(baseUrl).origin;
  const findings = {externalRequests: [], consoleErrors: [], pageErrors: [], serverErrors: []};
  const contexts = [];

  async function newPage() {
    const context = await browser.newContext({acceptDownloads: true});
    contexts.push(context);
    await context.route('**/*', async (route) => {
      const requestUrl = route.request().url();
      const protocol = new URL(requestUrl).protocol;
      if (new URL(requestUrl).origin === allowedOrigin || protocol === 'data:' || protocol === 'blob:') {
        await route.continue();
        return;
      }
      findings.externalRequests.push(requestUrl);
      await route.abort('blockedbyclient');
    });
    return monitoredPage(context, allowedOrigin, findings, expectedServerErrors);
  }

  const page = await newPage();
  try {
    await scenario({page, assert, newPage});
    assert.deepEqual(findings.externalRequests, [], 'browser attempted an external network request');
    assert.deepEqual(findings.consoleErrors, [], 'browser emitted console.error output');
    assert.deepEqual(findings.pageErrors, [], 'browser emitted an uncaught page error');
    assert.deepEqual(findings.serverErrors, [], 'same-origin request returned HTTP 5xx');
    console.log('PASS ' + name);
  } catch (error) {
    await mkdir('test-results', {recursive: true});
    const artifact = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    await page.screenshot({path: `test-results/${artifact || 'scenario'}-failure.png`, fullPage: true});
    throw error;
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}

export async function runScenario(name, scenario) {
  return withBrowser(name, ({page}) => scenario({page, expect}));
}
