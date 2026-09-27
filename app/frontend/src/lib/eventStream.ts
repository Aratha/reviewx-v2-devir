/**
 * Minimal `text/event-stream` reader for a `fetch` response body. `EventSource` cannot send the
 * `Authorization` header, so the review streams are read from a POST response instead.
 *
 * Yields the data of each event (several `data:` lines joined with a newline). Comment lines such
 * as the server's `: ping` keep-alive, `event:`, `id:` and `retry:` fields are ignored. CRLF, CR and
 * LF line endings and chunk boundaries anywhere (inside a line or a multi-byte character) are
 * handled. A trailing event without its closing blank line is dropped, like a browser does.
 */
export async function* readEventStream(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let data: string[] = [];
  let pendingCarriageReturn = false;
  let finished = false;
  try {
    for (;;) {
      const {value, done} = await reader.read();
      if (done) {
        finished = true;
        return;
      }
      let text = decoder.decode(value, {stream: true});
      if (pendingCarriageReturn && text.startsWith('\n')) text = text.slice(1);
      pendingCarriageReturn = text.endsWith('\r');
      buffer += text;
      const lines = buffer.split(/\r\n|\r|\n/);
      buffer = lines.pop() ?? '';
      for (const line of lines) {
        if (line === '') {
          if (data.length > 0) yield data.join('\n');
          data = [];
          continue;
        }
        if (line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        if (field !== 'data') continue;
        let content = colon === -1 ? '' : line.slice(colon + 1);
        if (content.startsWith(' ')) content = content.slice(1);
        data.push(content);
      }
    }
  } finally {
    // The consumer stopped early or the read failed: stop the body so the connection closes.
    if (!finished) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
