import {describe, expect, it} from 'vitest';

type MessageTree = {[key: string]: string | MessageTree};

const catalogues = import.meta.glob<MessageTree>('./*.json', {eager: true, import: 'default'});
const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], {
  eager: true,
  query: '?raw',
  import: 'default',
});

function flatten(tree: MessageTree, prefix = ''): Map<string, string> {
  const messages = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') messages.set(path, value);
    else for (const entry of flatten(value, path)) messages.set(...entry);
  }
  return messages;
}

const flattened = Object.fromEntries(
  Object.entries(catalogues).map(([path, tree]) => [path, flatten(tree)]),
);

describe('locale key parity', () => {
  it('ships at least one catalogue', () => {
    expect(Object.keys(flattened).length).toBeGreaterThan(0);
  });

  it('keeps the same non-empty key set in every configured catalogue', () => {
    const [reference, ...others] = Object.values(flattened);
    for (const catalogue of others) expect([...catalogue.keys()].sort()).toEqual([...reference.keys()].sort());
    for (const catalogue of Object.values(flattened))
      for (const [key, value] of catalogue) expect(value.trim(), key).not.toBe('');
  });

  it('resolves every literal message key used in source in every catalogue', () => {
    const used = new Set<string>();
    for (const source of Object.values(sources))
      for (const match of source.matchAll(/\bt\(\s*['"]([^'"]+)['"]/g)) used.add(match[1]);
    expect(used.size).toBeGreaterThan(0);
    for (const [path, catalogue] of Object.entries(flattened))
      for (const key of used) expect(catalogue.has(key), `${path} lacks ${key}`).toBe(true);
  });
});
