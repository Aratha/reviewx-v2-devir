import {formatDateTime} from '@/lib/format';
import type {RuleItem, RuleSetVersionSummary} from '@/types/sqlReview';

export type Tier = 'critical' | 'normal';
export const RULE_TEXT_LIMIT = 8000;
export const PREVIEW_CHARS = 100;

export interface RuleDraft {
  critical: RuleItem[];
  normal: RuleItem[];
}

export function ruleNumber(id: string): number | null {
  const match = /^Kural(\d+)$/.exec(id.trim());
  return match ? Number(match[1]) : null;
}

/** `Kural01` … `Kural99`, then `Kural100` …, as the backend formats identifiers. */
export function formatRuleId(value: number): string {
  return value < 100 ? `Kural${String(value).padStart(2, '0')}` : `Kural${value}`;
}

export function previewText(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '—';
  return trimmed.length <= PREVIEW_CHARS ? trimmed : `${trimmed.slice(0, PREVIEW_CHARS).trim()}…`;
}

export function ruleMatchesSearch(rule: RuleItem, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase('tr-TR');
  if (!needle) return true;
  return (
    rule.id.toLocaleLowerCase('tr-TR').includes(needle) ||
    rule.text.toLocaleLowerCase('tr-TR').includes(needle)
  );
}

export function moveRule(list: RuleItem[], index: number, delta: -1 | 1): RuleItem[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function normalizedDraft(draft: RuleDraft): RuleDraft {
  const clean = (rule: RuleItem): RuleItem => ({
    id: rule.id,
    text: rule.text,
    requires_metadata: Boolean(rule.requires_metadata),
  });
  return {critical: draft.critical.map(clean), normal: draft.normal.map(clean)};
}

export function draftsEqual(left: RuleDraft, right: RuleDraft): boolean {
  return JSON.stringify(normalizedDraft(left)) === JSON.stringify(normalizedDraft(right));
}

export function publisherName(version: Pick<RuleSetVersionSummary, 'published_by_name' | 'source'>): string {
  if (version.source === 'ice-aktarim') return 'içe aktarım';
  return version.published_by_name ?? 'bilinmiyor';
}

/** "Son yayın: sürüm N · tarih · yayımlayan" (rule-management Requirement 10). */
export function latestVersionLine(version: RuleSetVersionSummary | null): string {
  if (version === null) return 'Henüz yayımlanmış sürüm yok';
  return `Son yayın: sürüm ${version.number} · ${formatDateTime(version.published_at)} · ${publisherName(version)}`;
}
