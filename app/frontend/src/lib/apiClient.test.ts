import {beforeEach, describe, expect, it, vi} from 'vitest';
import {ApiError, apiFetch, apiRequest, refreshSession} from './apiClient';
import {clearAuth, readAccessToken, readUser, writeSession} from './authStorage';
import type {AuthenticatedUser} from '@/types/auth';

const user = {username: 'ayse.kaya', tenant_id: 'tenant-1', public_id: 'u-1'} as AuthenticatedUser;

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {'Content-Type': 'application/json', ...headers},
  });
}

function envelope(code: string, message = 'safe'): {detail: {code: string; message: string}} {
  return {detail: {code, message}};
}

function refreshed(token: string): Response {
  return jsonResponse(200, {access_token: token, token_type: 'bearer', expires_in: 900, user});
}

const bearerRejected = () =>
  jsonResponse(401, envelope('not_authenticated'), {'WWW-Authenticate': 'Bearer'});

function requestHeaders(call: unknown[]): Headers {
  return new Headers((call[1] as RequestInit | undefined)?.headers);
}

describe('api client', () => {
  beforeEach(() => {
    clearAuth();
    writeSession('jwt', user);
  });

  it('keeps the access token in memory only', () => {
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(readAccessToken()).toBe('jwt');
  });

  it('sends bearer and tenant context together, and JSON type only with a body', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(200, {ok: true}));
    await apiRequest('/auth/me');
    await apiRequest('/rule-set/draft', {method: 'PUT', body: '{}'});
    const [getCall, putCall] = fetchMock.mock.calls;
    expect(getCall[0]).toBe('/api/dwhcodereview/v1/auth/me');
    expect(requestHeaders(getCall).get('Authorization')).toBe('Bearer jwt');
    expect(requestHeaders(getCall).get('x-tenant-id')).toBe('tenant-1');
    expect(requestHeaders(getCall).get('Content-Type')).toBeNull();
    expect(requestHeaders(putCall).get('Content-Type')).toBe('application/json');
  });

  it('reads the error envelope code and message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(409, envelope('rule_set_draft_conflict', 'Kurallar değişti')),
    );
    const error = await apiRequest('/rule-set/draft').catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({status: 409, code: 'rule_set_draft_conflict', sessionExpired: false});
  });

  it('resolves a 204 answer without a body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, {status: 204}));
    await expect(apiRequest('/review-runs/r-1', {method: 'DELETE'})).resolves.toBeUndefined();
  });

  it('refreshes once when the bearer token is rejected and repeats the request', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(bearerRejected())
      .mockResolvedValueOnce(refreshed('jwt-2'))
      .mockResolvedValueOnce(jsonResponse(200, {items: []}));

    await expect(apiRequest('/review-runs')).resolves.toEqual({items: []});

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const refreshCall = fetchMock.mock.calls[1];
    expect(refreshCall[0]).toBe('/api/dwhcodereview/v1/auth/refresh');
    expect(refreshCall[1]).toMatchObject({method: 'POST', credentials: 'same-origin'});
    expect(requestHeaders(refreshCall).get('Authorization')).toBeNull();
    expect(requestHeaders(fetchMock.mock.calls[2]).get('Authorization')).toBe('Bearer jwt-2');
    expect(readAccessToken()).toBe('jwt-2');
  });

  it('shares one refresh between concurrent rejected requests', async () => {
    let refreshCalls = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        return refreshed('jwt-2');
      }
      const token = new Headers(init?.headers).get('Authorization');
      return token === 'Bearer jwt-2' ? jsonResponse(200, {url}) : bearerRejected();
    });

    const [first, second] = await Promise.all([apiRequest('/a'), apiRequest('/b')]);

    expect(first).toEqual({url: '/api/dwhcodereview/v1/a'});
    expect(second).toEqual({url: '/api/dwhcodereview/v1/b'});
    expect(refreshCalls).toBe(1);
  });

  it('ends the session when the refresh session itself expired', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(bearerRejected())
      .mockResolvedValueOnce(jsonResponse(401, envelope('session_expired')));

    const error = await apiRequest('/review-runs').catch((reason: unknown) => reason);

    expect(error).toMatchObject({status: 401, code: 'session_expired', sessionExpired: true});
    expect(readAccessToken()).toBeNull();
    expect(readUser()).toBeNull();
  });

  it('ends the session when the renewed token is rejected as well', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(bearerRejected())
      .mockResolvedValueOnce(refreshed('jwt-2'))
      .mockResolvedValueOnce(bearerRejected());

    await expect(apiRequest('/review-runs')).rejects.toMatchObject({sessionExpired: true});
    expect(readAccessToken()).toBeNull();
  });

  it.each([
    ['a 401 without a challenge', () => jsonResponse(401, {detail: 'Unauthorized'})],
    ['a proxy Basic challenge', () => jsonResponse(401, {}, {'WWW-Authenticate': 'Basic realm="proxy"'})],
    [
      'a Bearer challenge for another error',
      () => jsonResponse(401, {}, {'WWW-Authenticate': 'Bearer error="invalid_request"'}),
    ],
    ['a 403', () => jsonResponse(403, envelope('forbidden'))],
    ['a 429', () => jsonResponse(429, envelope('rate_limited'), {'Retry-After': '60'})],
    ['a 500', () => jsonResponse(500, {detail: 'Internal Server Error'})],
    ['a 502 from a proxy', () => new Response('<html>Bad Gateway</html>', {status: 502})],
    ['a 503 without a body', () => new Response(null, {status: 503})],
  ])('keeps the session and does not refresh on %s', async (_, response) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response());
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({sessionExpired: false});
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(readAccessToken()).toBe('jwt');
  });

  it('keeps the session when the refresh fails for a network reason', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(bearerRejected())
      .mockRejectedValueOnce(new TypeError('Failed to fetch'));

    await expect(apiRequest('/review-runs')).rejects.toMatchObject({status: 401, sessionExpired: false});
    expect(readAccessToken()).toBe('jwt');
  });

  it('keeps the session on a network error or a timeout', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new DOMException('The operation timed out.', 'TimeoutError'));
    await expect(apiRequest('/auth/me')).rejects.toThrow('Failed to fetch');
    await expect(apiRequest('/auth/me')).rejects.toMatchObject({name: 'TimeoutError'});
    expect(readAccessToken()).toBe('jwt');
  });

  it('keeps the session when a successful response cannot be parsed', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not json', {status: 200, headers: {'Content-Type': 'application/json'}}),
    );
    await expect(apiRequest('/auth/me')).rejects.toBeInstanceOf(SyntaxError);
    expect(readAccessToken()).toBe('jwt');
  });

  it('does not refresh when the rejected request carried no bearer credential', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(401, envelope('invalid_credentials'), {'WWW-Authenticate': 'Bearer'}));

    await expect(apiRequest('/auth/login', {method: 'POST', body: '{}'}, false)).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
      sessionExpired: false,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(requestHeaders(fetchMock.mock.calls[0]).get('Authorization')).toBeNull();
  });

  it('retries with a newer token instead of refreshing when another call already renewed it', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if (new Headers(init?.headers).get('Authorization') === 'Bearer jwt') {
        writeSession('jwt-new', user);
        return bearerRejected();
      }
      return jsonResponse(200, {ok: true});
    });

    await expect(apiRequest('/auth/me')).resolves.toEqual({ok: true});
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(readAccessToken()).toBe('jwt-new');
  });

  it('returns the raw successful response for streams and downloads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('a,b\r\n', {status: 200, headers: {'Content-Type': 'text/csv'}}),
    );
    const response = await apiFetch('/review-runs/r-1/exports/csv');
    expect(await response.text()).toBe('a,b\r\n');
  });

  it('restores a session from the refresh cookie without any stored token', async () => {
    clearAuth();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(refreshed('jwt-restored'));
    await expect(refreshSession()).resolves.toMatchObject({access_token: 'jwt-restored'});
    expect(readUser()).toEqual(user);
    expect(localStorage.length).toBe(0);
  });
});
