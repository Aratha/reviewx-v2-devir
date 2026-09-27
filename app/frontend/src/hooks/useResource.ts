import {useCallback, useEffect, useRef, useState} from 'react';

export type ResourceState<T> =
  | {status: 'idle'; data: undefined; error: undefined}
  | {status: 'loading'; data: T | undefined; error: undefined}
  | {status: 'success'; data: T; error: undefined}
  | {status: 'error'; data: T | undefined; error: unknown};

interface Settled<T> {
  key: string;
  ok: boolean;
  data?: T;
  error?: unknown;
}

/**
 * Load `key`'s data and model idle, loading, success and error explicitly. A new key, `reload` or
 * unmounting aborts the previous request and ignores its late answer. While a key reloads, the
 * last data of that same key stays visible. `replace` swaps in data the caller already has, such
 * as the answer of a successful save.
 */
export function useResource<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): ResourceState<T> & {reload: () => void; replace: (data: T) => void} {
  const [generation, setGeneration] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });
  const requestKey = key === null ? null : `${key}\u0000${generation}`;

  useEffect(() => {
    if (requestKey === null) return;
    const controller = new AbortController();
    loadRef.current(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({key: requestKey, ok: true, data});
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setSettled({key: requestKey, ok: false, error});
      },
    );
    return () => controller.abort();
  }, [requestKey]);

  const reload = useCallback(() => setGeneration((value) => value + 1), []);
  const replace = useCallback(
    (data: T) => {
      if (requestKey !== null) setSettled({key: requestKey, ok: true, data});
    },
    [requestKey],
  );

  const sameKey = key !== null && settled !== null && settled.key.split('\u0000')[0] === key;
  const lastData = sameKey && settled.ok ? settled.data : undefined;
  if (key === null) return {status: 'idle', data: undefined, error: undefined, reload, replace};
  if (settled === null || settled.key !== requestKey)
    return {status: 'loading', data: lastData, error: undefined, reload, replace};
  if (settled.ok) return {status: 'success', data: settled.data as T, error: undefined, reload, replace};
  return {status: 'error', data: undefined, error: settled.error, reload, replace};
}
