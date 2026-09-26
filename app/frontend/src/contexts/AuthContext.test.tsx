import {render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {AuthProvider, useAuth} from './AuthContext';
import {ApiError} from '@/lib/apiClient';
import {readAccessToken, readUser, writeSession} from '@/lib/authStorage';
import {AuthService} from '@/services/auth';
import type {AuthenticatedUser} from '@/types/auth';

const cached = {username: 'cached', tenant_id: 'tenant-1', roles: [], permissions: []} as unknown as AuthenticatedUser;

function Probe() {
  const {user, loading} = useAuth();
  return <p data-testid="session">{loading ? 'loading' : (user?.username ?? 'signed-out')}</p>;
}

async function settled(): Promise<string | null> {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await waitFor(() => expect(screen.queryByText('loading')).toBeNull());
  return screen.getByTestId('session').textContent;
}

describe('auth context session recovery', () => {
  beforeEach(() => {
    localStorage.clear();
    writeSession('jwt', cached);
  });
  afterEach(() => vi.restoreAllMocks());

  it('refreshes the stored user from /me', async () => {
    vi.spyOn(AuthService, 'me').mockResolvedValue({...cached, username: 'fresh'});

    expect(await settled()).toBe('fresh');
    expect(readUser()?.username).toBe('fresh');
  });

  it('signs out when the shared client proved the bearer credential expired', async () => {
    vi.spyOn(AuthService, 'me').mockRejectedValue(new ApiError(401, 'expired', undefined, true));

    expect(await settled()).toBe('signed-out');
  });

  it.each([
    ['a network error', new TypeError('Failed to fetch')],
    ['a timeout', new DOMException('The operation timed out.', 'TimeoutError')],
    ['a parse error', new SyntaxError('Unexpected token')],
    ['a 5xx', new ApiError(503, 'Service Unavailable')],
    ['an unrelated 401', new ApiError(401, 'Unauthorized')],
    ['a 403', new ApiError(403, 'Tenant access denied', 'tenant_forbidden')],
  ])('keeps the session on %s', async (_, failure) => {
    vi.spyOn(AuthService, 'me').mockRejectedValue(failure);

    expect(await settled()).toBe('cached');
    expect(readAccessToken()).toBe('jwt');
    expect(readUser()?.username).toBe('cached');
  });
});
