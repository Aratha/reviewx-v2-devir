import {afterEach, describe, expect, it, vi} from 'vitest';
import {clearAuth, readAccessToken, readUser, subscribeAuth, writeSession, writeUser} from './authStorage';
import type {AuthenticatedUser} from '@/types/auth';

const user = {username: 'admin', tenant_id: 'tenant-1'} as AuthenticatedUser;

describe('auth storage', () => {
  afterEach(() => clearAuth());

  it('holds the session in memory and never in browser storage', () => {
    writeSession('token', user);
    expect(readAccessToken()).toBe('token');
    expect(readUser()).toEqual(user);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).toBe('');
  });

  it('updates the user without touching the token and clears both together', () => {
    writeSession('token', user);
    writeUser({...user, username: 'renamed'});
    expect(readUser()?.username).toBe('renamed');
    expect(readAccessToken()).toBe('token');
    clearAuth();
    expect(readAccessToken()).toBeNull();
    expect(readUser()).toBeNull();
  });

  it('notifies subscribers on every change until they unsubscribe', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuth(listener);
    writeSession('token', user);
    clearAuth();
    clearAuth();
    unsubscribe();
    writeSession('token', user);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('ignores a user update when no session exists', () => {
    writeUser(user);
    expect(readUser()).toBeNull();
  });
});
