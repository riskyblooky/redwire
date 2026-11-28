import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({ authedFetch: vi.fn() }));

import { authedFetch } from '@/lib/api';
import { streamAiChat } from '@/lib/ai-chat-stream';

const fetchMock = vi.mocked(authedFetch);

/** A 200 SSE response whose body arrives in exactly these byte chunks. */
function sseResponse(chunks: (string | Uint8Array)[]): Response {
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
        start(controller) {
            for (const c of chunks) controller.enqueue(typeof c === 'string' ? enc.encode(c) : c);
            controller.close();
        },
    });
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

async function collect(chunks: (string | Uint8Array)[]) {
    fetchMock.mockResolvedValueOnce(sseResponse(chunks));
    const events: [string, unknown][] = [];
    await streamAiChat({ message: 'hi' }, { onEvent: (e, d) => events.push([e, d]) });
    return events;
}

beforeEach(() => {
    fetchMock.mockReset();
});

describe('streamAiChat', () => {
    it('POSTs the JSON body to /ai/chat with the abort signal', async () => {
        fetchMock.mockResolvedValueOnce(sseResponse([]));
        const ctrl = new AbortController();
        await streamAiChat({ message: 'hi', session_id: 's1' }, { onEvent: () => {}, signal: ctrl.signal });
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [path, init] = fetchMock.mock.calls[0];
        expect(path).toBe('/ai/chat');
        expect(init?.method).toBe('POST');
        expect(init?.signal).toBe(ctrl.signal);
        expect(JSON.parse(init?.body as string)).toEqual({ message: 'hi', session_id: 's1' });
    });

    it('parses named events in order', async () => {
        const events = await collect([
            'event: chunk\ndata: {"content":"Hel"}\n\n',
            'event: chunk\ndata: {"content":"lo"}\n\n',
            'event: tool_call_pending\ndata: {"tool":"list_findings","args":{}}\n\n',
            'event: done\ndata: {"session_id":"abc"}\n\n',
        ]);
        expect(events).toEqual([
            ['chunk', { content: 'Hel' }],
            ['chunk', { content: 'lo' }],
            ['tool_call_pending', { tool: 'list_findings', args: {} }],
            ['done', { session_id: 'abc' }],
        ]);
    });

    it('reassembles an event split across reads, mid-line', async () => {
        const events = await collect(['eve', 'nt: chu', 'nk\nda', 'ta: {"content":', '"split"}\n', '\n']);
        expect(events).toEqual([['chunk', { content: 'split' }]]);
    });

    it('decodes a multi-byte character split across reads', async () => {
        const bytes = new TextEncoder().encode('event: chunk\ndata: {"content":"café 🔥"}\n\n');
        // Cut inside the 4-byte emoji and inside the 2-byte é.
        const emoji = bytes.indexOf(0xf0);
        const eAcute = bytes.indexOf(0xc3);
        const events = await collect([
            bytes.slice(0, eAcute + 1), bytes.slice(eAcute + 1, emoji + 2), bytes.slice(emoji + 2),
        ]);
        expect(events).toEqual([['chunk', { content: 'café 🔥' }]]);
    });

    it('handles several events in one read and CRLF line endings', async () => {
        const events = await collect([
            'event: chunk\r\ndata: {"content":"a"}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n',
        ]);
        expect(events).toEqual([['chunk', { content: 'a' }], ['done', {}]]);
    });

    it('defaults to "chunk" when the event line is missing', async () => {
        expect(await collect(['data: {"content":"x"}\n\n'])).toEqual([['chunk', { content: 'x' }]]);
    });

    it('skips unparseable, empty and [DONE] data lines and non-data lines', async () => {
        const events = await collect([
            ': keep-alive comment\n',
            'event: chunk\ndata: not json\n\n',
            'data: \n\n',
            'data: [DONE]\n\n',
            'id: 7\nretry: 1000\n',
            'event: chunk\ndata: {"content":"ok"}\n\n',
        ]);
        expect(events).toEqual([['chunk', { content: 'ok' }]]);
    });

    it('passes non-object JSON through', async () => {
        expect(await collect(['event: chunk\ndata: "plain"\n\nevent: chunk\ndata: 42\n\n']))
            .toEqual([['chunk', 'plain'], ['chunk', 42]]);
    });

    it('resolves with no events for an empty stream or missing body', async () => {
        expect(await collect([])).toEqual([]);
        fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));
        const onEvent = vi.fn();
        const onOpen = vi.fn();
        await streamAiChat({}, { onEvent, onOpen });
        expect(onOpen).toHaveBeenCalledTimes(1);
        expect(onEvent).not.toHaveBeenCalled();
    });

    it('calls onOpen once, before the first event', async () => {
        fetchMock.mockResolvedValueOnce(sseResponse(['event: chunk\ndata: {"n":1}\n\n', 'event: chunk\ndata: {"n":2}\n\n']));
        const order: string[] = [];
        await streamAiChat({}, { onOpen: () => order.push('open'), onEvent: (_e, d) => order.push(`event${d.n}`) });
        expect(order).toEqual(['open', 'event1', 'event2']);
    });

    it('throws the server detail on a non-OK response, without opening', async () => {
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'AI is disabled' }), { status: 403 }));
        const onOpen = vi.fn();
        await expect(streamAiChat({}, { onEvent: () => {}, onOpen })).rejects.toThrow('AI is disabled');
        expect(onOpen).not.toHaveBeenCalled();
    });

    it('falls back to statusText, then HTTP status, when detail is not a string', async () => {
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ msg: 'bad' }] }), { status: 422, statusText: 'Unprocessable Entity' }));
        await expect(streamAiChat({}, { onEvent: () => {} })).rejects.toThrow('Unprocessable Entity');
        fetchMock.mockResolvedValueOnce(new Response('<html>gateway</html>', { status: 502, statusText: '' }));
        await expect(streamAiChat({}, { onEvent: () => {} })).rejects.toThrow('HTTP 502');
    });

    it('propagates a fetch abort', async () => {
        const abort = new DOMException('The operation was aborted.', 'AbortError');
        fetchMock.mockRejectedValueOnce(abort);
        await expect(streamAiChat({}, { onEvent: () => {} })).rejects.toBe(abort);
    });
});
