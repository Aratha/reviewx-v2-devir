import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError, apiRequest} from './apiClient';
import {STORAGE_KEYS} from './authStorage';

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {'Content-Type': 'application/json', ...headers},
  });
}

function storeSession(token = 'jwt'): void {
  localStorage.setItem(STORAGE_KEYS.accessToken, token);
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify({tenant_id: 'tenant-1'}));
}

function sessionKept(token = 'jwt'): void {
  expect(localStorage.getItem(STORAGE_KEYS.accessToken)).toBe(token);
  expect(localStorage.getItem(STORAGE_KEYS.user)).not.toBeNull();
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState({}, '', '/login');
  });
  afterEach(() => vi.restoreAllMocks());

  it('sends bearer and tenant context together', async () => {
    storeSession();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(200, {ok: true}));
    await apiRequest('/auth/me');
    const request = fetchMock.mock.calls[0][1]!;
    const headers = new Headers(request.headers);
    expect(headers.get('Authorization')).toBe('Bearer jwt');
    expect(headers.get('x-tenant-id')).toBe('tenant-1');
  });

  it.each([
    ['a bare Bearer challenge', 'Bearer'],
    ['an invalid_token Bearer challenge', 'Bearer realm="api", error="invalid_token"'],
  ])('ends the session when the app bearer credential is rejected with %s', async (_, challenge) => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(401, {detail: 'Invalid or missing access token'}, {'WWW-Authenticate': challenge}),
    );

    const error = await apiRequest('/auth/me').catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({status: 401, sessionExpired: true});
    expect(localStorage.getItem(STORAGE_KEYS.accessToken)).toBeNull();
    expect(localStorage.getItem(STORAGE_KEYS.user)).toBeNull();
  });

  it('redirects to the login page after ending the session elsewhere', async () => {
    window.history.replaceState({}, '', '/reports');
    const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => undefined);
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(401, {}, {'WWW-Authenticate': 'Bearer'}),
    );

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({sessionExpired: true});
    expect(assign).toHaveBeenCalledWith('/login');
  });

  it.each([
    ['a 401 without a challenge', () => jsonResponse(401, {detail: 'Unauthorized'})],
    [
      'a proxy Basic challenge',
      () => jsonResponse(401, {}, {'WWW-Authenticate': 'Basic realm="corporate-proxy"'}),
    ],
    [
      'a Bearer challenge for another error',
      () => jsonResponse(401, {}, {'WWW-Authenticate': 'Bearer error="invalid_request"'}),
    ],
    ['a 403', () => jsonResponse(403, {detail: 'Missing permission: reports:read'})],
    ['a 429', () => jsonResponse(429, {detail: 'Too many requests'}, {'Retry-After': '60'})],
    ['a 500', () => jsonResponse(500, {detail: 'Internal Server Error'})],
    ['a 502 from a proxy', () => new Response('<html>Bad Gateway</html>', {status: 502})],
    ['a 503 without a body', () => new Response(null, {status: 503})],
  ])('keeps the session on %s', async (_, response) => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response());

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({sessionExpired: false});
    sessionKept();
  });

  it('keeps the session on a network error', async () => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(apiRequest('/auth/me')).rejects.toThrow('Failed to fetch');
    sessionKept();
  });

  it('keeps the session on a timeout', async () => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new DOMException('The operation timed out.', 'TimeoutError'),
    );

    await expect(apiRequest('/auth/me', {signal: AbortSignal.timeout(1)})).rejects.toMatchObject({
      name: 'TimeoutError',
    });
    sessionKept();
  });

  it('keeps the session when a successful response cannot be parsed', async () => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not json', {status: 200, headers: {'Content-Type': 'application/json'}}),
    );

    await expect(apiRequest('/auth/me')).rejects.toBeInstanceOf(SyntaxError);
    sessionKept();
  });

  it('keeps the session when the rejected request carried no bearer credential', async () => {
    storeSession();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(401, {detail: 'Incorrect username or password'}, {'WWW-Authenticate': 'Bearer'}),
    );

    await expect(
      apiRequest('/auth/login', {method: 'POST', body: '{}'}, false),
    ).rejects.toMatchObject({status: 401, sessionExpired: false});
    sessionKept();
  });

  it('keeps a newer session when an older credential is rejected', async () => {
    storeSession('old-jwt');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      storeSession('new-jwt');
      return jsonResponse(401, {}, {'WWW-Authenticate': 'Bearer'});
    });

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({sessionExpired: false});
    sessionKept('new-jwt');
  });
});
