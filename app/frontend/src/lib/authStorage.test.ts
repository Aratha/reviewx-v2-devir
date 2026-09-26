import {beforeEach, describe, expect, it} from 'vitest';
import {clearAuth, readAccessToken, readUser, STORAGE_KEYS, writeSession, writeUser} from './authStorage';
import type {AuthenticatedUser} from '@/types/auth';

const user = {username: 'admin', tenant_id: 'tenant-1'} as AuthenticatedUser;

describe('auth storage', () => {
  beforeEach(() => localStorage.clear());

  it('rejects malformed stored users and clears both session keys', () => {
    localStorage.setItem(STORAGE_KEYS.user, '{');
    localStorage.setItem(STORAGE_KEYS.accessToken, 'token');
    expect(readUser()).toBeNull();
    clearAuth();
    expect(localStorage.length).toBe(0);
  });

  it('writes and reads the session only through its own keys', () => {
    writeSession('token', user);
    expect(readAccessToken()).toBe('token');
    expect(readUser()).toEqual(user);

    writeUser({...user, username: 'renamed'});
    expect(readUser()?.username).toBe('renamed');
    expect(readAccessToken()).toBe('token');
    expect(localStorage.length).toBe(2);
  });
});
