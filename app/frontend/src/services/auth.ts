import {apiRequest, refreshSession} from '@/lib/apiClient';
import type {AuthenticatedUser, LoginResponse} from '@/types/auth';

export const AuthService = {
  login(username: string, password: string): Promise<LoginResponse> {
    return apiRequest<LoginResponse>(
      '/auth/login',
      {method: 'POST', body: JSON.stringify({username, password}), credentials: 'same-origin'},
      false,
    );
  },
  /** Restore or renew the session from the HttpOnly refresh cookie. */
  refresh(): Promise<LoginResponse> {
    return refreshSession();
  },
  /** End the refresh session on the server; the cookie is removed by the response. */
  logout(): Promise<void> {
    return apiRequest<void>('/auth/logout', {method: 'POST', credentials: 'same-origin'}, false);
  },
  me(): Promise<AuthenticatedUser> {
    return apiRequest<AuthenticatedUser>('/auth/me');
  },
};
