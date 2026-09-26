import {beforeEach, describe, expect, it, vi} from 'vitest';
import {ReviewService} from './reviews';
import {writeSession} from '@/lib/authStorage';
import {testUser} from '@/test/render';
import {eventStreamResponse, objectRunEvents} from '@/test/reviewEvents';
import type {ReviewStreamEvent} from '@/types/sqlReview';

describe('review service', () => {
  beforeEach(() => writeSession('jwt', testUser('inceleyici')));

  it('reads every event of the stream in order and never puts the token or SQL into the URL', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(eventStreamResponse(objectRunEvents()));
    const seen: ReviewStreamEvent[] = [];
    await ReviewService.streamScriptReview('SELECT secret_column', 'etiket', new AbortController().signal, (event) =>
      seen.push(event),
    );
    expect(seen.map((event) => event.phase)).toEqual(objectRunEvents().map((event) => event.phase));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/dwhcodereview/v1/script-reviews');
    expect(String(url)).not.toMatch(/jwt|secret_column/);
    expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream');
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt');
  });

  it('skips a malformed event instead of stopping the stream', async () => {
    const encoder = new TextEncoder();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode('data: {broken\n\ndata: {"no_phase":1}\n\n'));
            controller.enqueue(encoder.encode('data: {"phase":"error","code":"review_failed","message":"x"}\n\n'));
            controller.close();
          },
        }),
        {status: 200},
      ),
    );
    const seen: string[] = [];
    await ReviewService.streamObjectReview([], new AbortController().signal, (event) => seen.push(String(event.phase)));
    expect(seen).toEqual(['error']);
  });

  it('downloads an export with the session header and the server file name', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('﻿generated_at\r\n', {
        status: 200,
        headers: {'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': 'attachment; filename="sql-review-1727.csv"'},
      }),
    );
    const file = await ReviewService.exportRun('run-1', 'csv');
    expect(file.filename).toBe('sql-review-1727.csv');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/dwhcodereview/v1/review-runs/run-1/exports/csv');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer jwt');
  });

  it('rejects an SQL export without stored text with its code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({detail: {code: 'sql_text_unavailable', message: 'x'}}), {status: 409}),
    );
    await expect(ReviewService.exportRun('run-1', 'sql')).rejects.toMatchObject({
      status: 409,
      code: 'sql_text_unavailable',
    });
  });
});
