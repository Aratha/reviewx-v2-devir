import {apiRequest} from '@/lib/apiClient';
import type {AuthenticatedUser, LoginResponse} from '@/types/auth';

export const AuthService = {
  login(username: string, password: string): Promise<LoginResponse> {
    return apiRequest<LoginResponse>(
      '/auth/login',
      {method: 'POST', body: JSON.stringify({username, password})},
      false,
    );
  },
  me(): Promise<AuthenticatedUser> {
    return apiRequest<AuthenticatedUser>('/auth/me');
  },
};

