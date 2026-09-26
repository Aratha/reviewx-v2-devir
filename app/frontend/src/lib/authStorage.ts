import type {AuthenticatedUser} from '@/types/auth';

/** The only module that reads or writes the persisted session. */
export const STORAGE_KEYS = {
  accessToken: 'dwhcodereview.access_token',
  user: 'dwhcodereview.user',
} as const;

export function readAccessToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEYS.accessToken);
  } catch {
    return null;
  }
}

export function readUser(): AuthenticatedUser | null {
  try {
    const value = localStorage.getItem(STORAGE_KEYS.user);
    return value ? (JSON.parse(value) as AuthenticatedUser) : null;
  } catch {
    return null;
  }
}

export function writeSession(accessToken: string, user: AuthenticatedUser): void {
  localStorage.setItem(STORAGE_KEYS.accessToken, accessToken);
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
}

export function writeUser(user: AuthenticatedUser): void {
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEYS.accessToken);
  localStorage.removeItem(STORAGE_KEYS.user);
}
