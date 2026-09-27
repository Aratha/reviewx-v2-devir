import {describe, expect, it} from 'vitest';
import {applyEvent, completionRatio, createProgress, orderedObjects, tokenLabel} from './reviewProgress';
import {objectRunEvents} from '@/test/reviewEvents';
import type {ReviewStreamEvent} from '@/types/sqlReview';

function replay(events: ReviewStreamEvent[], objectsTotal = 1) {
  return events.reduce(applyEvent, createProgress(objectsTotal));
}

describe('live review progress', () => {
  it('merges the event sequence into stages, rule counters and token counts', () => {
    const events = objectRunEvents();
    const progress = replay(events.slice(0, -1));
    const [object] = orderedObjects(progress);
    expect(progress).toMatchObject({runId: 'run-1', ruleVersion: 2, objectsDone: 1});
    expect(object).toMatchObject({stage: 'done', rulesTotal: 2, rulesDone: 2, sqlLength: 1200});
    expect(object.ruleOrder).toEqual(['Kural01', 'Kural03']);
    expect(object.rules.Kural01).toMatchObject({stage: 'done', tier: 'critical', completionTokens: 30});
    expect(object.rules.Kural03).toMatchObject({stage: 'failed'});
    expect(completionRatio(progress)).toBe(1);
  });

  it('shows a running rule with streamed counts but no model text', () => {
    const progress = replay(objectRunEvents().slice(0, 7));
    const rule = orderedObjects(progress)[0].rules.Kural01;
    expect(rule).toMatchObject({stage: 'running', completionTokens: 12, totalChars: 48});
    expect(tokenLabel(rule)).toBe('12 belirteç');
    expect(Object.keys(rule)).not.toContain('text');
  });

  it('marks an object error and keeps other objects going', () => {
    const second = {
      kind: 'object' as const,
      database: 'MART',
      object_index: 1,
      objects_total: 2,
      object_label: '[MART] dbo.v (V)',
      schema: 'dbo',
      name: 'v',
      type_code: 'V',
    };
    const progress = replay(
      [
        {phase: 'run_started', run_id: 'run-1', rule_version: 2, objects_total: 2, kind: 'object'},
        ...objectRunEvents().slice(1, 5),
        {...second, phase: 'object_start'},
        {...second, phase: 'object_error', code: 'object_not_found', message: 'Tanım alınamadı (nesne yok veya yetki yok).'},
        {...second, phase: 'object_done'},
      ],
      2,
    );
    const objects = orderedObjects(progress);
    expect(objects.map((object) => object.stage)).toEqual(['rules', 'error']);
    expect(objects[1].error?.code).toBe('object_not_found');
    expect(progress.objectsDone).toBe(1);
    expect(completionRatio(progress)).toBeCloseTo(0.5);
  });

  it('estimates tokens from characters when the server sends no count', () => {
    expect(
      tokenLabel({ruleId: 'K', tier: null, stage: 'running', completionTokens: null, totalChars: 41, twoPart: false}),
    ).toBe('~11 belirteç');
    expect(
      tokenLabel({ruleId: 'K', tier: null, stage: 'running', completionTokens: null, totalChars: 0, twoPart: false}),
    ).toBe('Yanıt bekleniyor');
  });
});
