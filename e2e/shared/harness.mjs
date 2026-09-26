import {chromium, expect} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdir} from 'node:fs/promises';

export const baseUrl = (process.env.APP_E2E_BASE || 'http://localhost:8080').replace(/\/$/, '');
export const username = process.env.APP_E2E_SUPER_ADMIN_USER || process.env.DWHCODEREVIEW_SUPER_ADMIN_USER;
export const password = process.env.APP_E2E_SUPER_ADMIN_PASS || process.env.DWHCODEREVIEW_SUPER_ADMIN_PASS;

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

export async function withBrowser(name, scenario) {
  assert.ok(username, 'APP_E2E_SUPER_ADMIN_USER is required');
  assert.ok(password, 'APP_E2E_SUPER_ADMIN_PASS is required');
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext();
  const allowedOrigin = new URL(baseUrl).origin;
  const externalRequests = [];
  const consoleErrors = [];
  const pageErrors = [];
  const serverErrors = [];
  await context.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    const protocol = new URL(requestUrl).protocol;
    if (new URL(requestUrl).origin === allowedOrigin || protocol === 'data:' || protocol === 'blob:') {
      await route.continue();
      return;
    }
    externalRequests.push(requestUrl);
    await route.abort('blockedbyclient');
  });
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    pageErrors.push(error.stack || error.message || String(error));
  });
  page.on('response', (response) => {
    const responseUrl = response.url();
    if (new URL(responseUrl).origin === allowedOrigin && response.status() >= 500) {
      serverErrors.push(`${response.status()} ${response.request().method()} ${responseUrl}`);
    }
  });
  try {
    await scenario({page, assert});
    assert.deepEqual(externalRequests, [], 'browser attempted an external network request');
    assert.deepEqual(consoleErrors, [], 'browser emitted console.error output');
    assert.deepEqual(pageErrors, [], 'browser emitted an uncaught page error');
    assert.deepEqual(serverErrors, [], 'same-origin request returned HTTP 5xx');
    console.log('PASS ' + name);
  } catch (error) {
    await mkdir('test-results', {recursive: true});
    const artifact = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    await page.screenshot({path: `test-results/${artifact || 'scenario'}-failure.png`, fullPage: true});
    throw error;
  } finally {
    await context.close();
    await browser.close();
  }
}

export async function runScenario(name, scenario) {
  return withBrowser(name, ({page}) => scenario({page, expect}));
}
