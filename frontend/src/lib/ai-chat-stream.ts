import { authedFetch } from '@/lib/api';

/**
 * POST /ai/chat and hand each server-sent event to `onEvent`.
 *
 * The backend frames every event as `event: <name>\ndata: <json>\n\n`
 * (names: chunk, tool_call_pending, tool_call_result, tool_call_denied,
 * context_compacted, done). A read can end mid-line or mid-character, so
 * the unfinished tail is kept for the next read; unparseable data lines
 * are skipped.
 *
 * `onOpen` runs once the response is OK, before any event. A non-OK
 * response throws an Error carrying the server's `detail`; an abort via
 * `signal` throws the fetch AbortError. Resolves when the stream ends.
 */
export async function streamAiChat(
    body: Record<string, unknown>,
    {
        onEvent,
        onOpen,
        signal,
    }: {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onEvent: (event: string, data: any) => void;
        onOpen?: () => void;
        signal?: AbortSignal;
    },
): Promise<void> {
    // authedFetch: a stream needs fetch, but not a stale token (raw fetch
    // skips the 401 refresh, so an expired token failed chat).
    const resp = await authedFetch('/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal,
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(typeof err.detail === 'string' ? err.detail : (resp.statusText || `HTTP ${resp.status}`));
    }
    onOpen?.();

    const reader = resp.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = '';
    let event = 'chunk'; // if the server ever omits the event line
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
            if (line.startsWith('event: ')) { event = line.slice(7).trim(); continue; }
            if (!line.startsWith('data: ')) continue;
            const data = line.slice(6).trim();
            if (!data || data === '[DONE]') continue;
            let parsed: unknown;
            try { parsed = JSON.parse(data); } catch { continue; }
            onEvent(event, parsed);
        }
    }
}
