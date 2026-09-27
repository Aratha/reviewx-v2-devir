import '@testing-library/jest-dom/vitest';
import {cleanup} from '@testing-library/react';
import {afterEach, vi} from 'vitest';
import {clearAuth} from '@/lib/authStorage';

// Vitest globals are off, so Testing Library cannot register its own unmount hook. Unmount first,
// then end the in-memory session and restore spies, so no mounted page reacts to either.
afterEach(() => {
  cleanup();
  clearAuth();
  vi.restoreAllMocks();
});
