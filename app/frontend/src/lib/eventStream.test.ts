import {describe, expect, it} from 'vitest';
import {readEventStream} from './eventStream';

function streamOf(chunks: Array<string | Uint8Array>): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<string[]> {
  const events: string[] = [];
  for await (const data of readEventStream(stream)) events.push(data);
  return events;
}

describe('event stream reader', () => {
  it('yields one data payload per event and skips keep-alive comments', async () => {
    const events = await collect(
      streamOf(['data: {"phase":"run_started"}\n\n', ': ping\n\n', 'data: {"phase":"complete"}\n\n']),
    );
    expect(events).toEqual(['{"phase":"run_started"}', '{"phase":"complete"}']);
  });

  it('joins events split at any byte, including inside a multi-byte character', async () => {
    const bytes = new TextEncoder().encode('data: {"message":"İnceleme durduruldu."}\n\n');
    const chunks = Array.from(bytes, (byte) => new Uint8Array([byte]));
    expect(await collect(streamOf(chunks))).toEqual(['{"message":"İnceleme durduruldu."}']);
  });

  it('accepts CRLF and CR line endings, also when CRLF is split across chunks', async () => {
    const events = await collect(streamOf(['data: a\r', '\n\r\n', 'data: b\r\rdata: c\n\n']));
    expect(events).toEqual(['a', 'b', 'c']);
  });

  it('joins multi-line data and ignores other fields', async () => {
    const events = await collect(streamOf(['event: progress\nid: 7\ndata: first\ndata:second\nretry: 5\n\n']));
    expect(events).toEqual(['first\nsecond']);
  });

  it('drops an unterminated trailing event when the connection ends', async () => {
    expect(await collect(streamOf(['data: done\n\n', 'data: partial']))).toEqual(['done']);
  });

  it('cancels the body when the consumer stops early', async () => {
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.enqueue(new TextEncoder().encode('data: tick\n\n'));
      },
      cancel() {
        cancelled = true;
      },
    });
    for await (const data of readEventStream(stream)) {
      expect(data).toBe('tick');
      break;
    }
    expect(cancelled).toBe(true);
  });

  it('rethrows a read failure such as an aborted request', async () => {
    let pulls = 0;
    const stream = new ReadableStream<Uint8Array>(
      {
        pull(controller) {
          pulls += 1;
          if (pulls === 1) controller.enqueue(new TextEncoder().encode('data: one\n\n'));
          else controller.error(new DOMException('The operation was aborted.', 'AbortError'));
        },
      },
      {highWaterMark: 0},
    );
    const seen: string[] = [];
    await expect(
      (async () => {
        for await (const data of readEventStream(stream)) seen.push(data);
      })(),
    ).rejects.toMatchObject({name: 'AbortError'});
    expect(seen).toEqual(['one']);
  });
});
