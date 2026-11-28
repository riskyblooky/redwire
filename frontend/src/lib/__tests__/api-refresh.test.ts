/**
 * The axios 401 → refresh → retry interceptor in src/lib/api.ts. Requests go
 * to a fake adapter (no network); browser globals are stubbed before the
 * module loads.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import axios, { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

class MemoryStorage {
    private m = new Map<string, string>();
    getItem(k: string) { return this.m.has(k) ? this.m.get(k)! : null; }
    setItem(k: string, v: string) { this.m.set(k, String(v)); }
    removeItem(k: string) { this.m.delete(k); }
    clear() { this.m.clear(); }
}

const storage = new MemoryStorage();
const doc = { cookie: '' };
const win = {
    location: { pathname: '/findings/42', search: '?tab=evidence', hash: '', href: '' },
    addEventListener: vi.fn(),
};
vi.stubGlobal('localStorage', storage);
vi.stubGlobal('document', doc);
vi.stubGlobal('window', win);

let api: typeof import('@/lib/api').api;

// ── fake server ──
// Tokens are deliberately not JWTs, so the proactive-refresh timer never arms.
let validToken = 'new-token';
let refreshCalls = 0;
let refreshImpl: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;
let routes: Record<string, (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>>;
const seen: { url: string; auth: string | undefined }[] = [];

function respond(config: InternalAxiosRequestConfig, status: number, data: unknown = {}): Promise<AxiosResponse> {
    const response = { data, status, statusText: String(status), headers: {}, config, request: {} } as AxiosResponse;
    if (status >= 200 && status < 300) return Promise.resolve(response);
    return Promise.reject(new AxiosError(`Request failed with status code ${status}`,
        status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST, config, {}, response));
}

const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

/** 200 for the current valid token, else 401. */
const guarded = (data: unknown) => (config: InternalAxiosRequestConfig) =>
    respond(config, config.headers.Authorization === `Bearer ${validToken}` ? 200 : 401, data);

const adapter: AxiosAdapter = async (config) => {
    const url = config.url || '';
    if (url.endsWith('/auth/refresh')) {
        refreshCalls++;
        return refreshImpl(config);
    }
    seen.push({ url, auth: config.headers.Authorization as string | undefined });
    const route = routes[url];
    if (!route) return respond(config, 404);
    return route(config);
};

const sentTo = (url: string) => seen.filter(s => s.url === url);

beforeAll(async () => {
    ({ api } = await import('@/lib/api'));
    api.defaults.adapter = adapter;      // the app's instance
    axios.defaults.adapter = adapter;    // refreshAccessToken() posts via the global axios
});

beforeEach(() => {
    storage.clear();
    storage.setItem('access_token', 'old-token');
    storage.setItem('engagement-context', '{"id":"e1"}');
    doc.cookie = 'has_session=1';
    win.location.href = '';
    validToken = 'new-token';
    refreshCalls = 0;
    seen.length = 0;
    refreshImpl = async (config) => { await delay(5); return respond(config, 200, { access_token: 'new-token' }); };
    routes = {
        '/things': guarded({ ok: 'things' }),
        '/other': guarded({ ok: 'other' }),
        '/third': guarded({ ok: 'third' }),
    };
});

afterEach(() => {
    vi.useRealTimers();
});

describe('401 → refresh → retry', () => {
    it('refreshes once and retries the request with the new token', async () => {
        const res = await api.get('/things');
        expect(res.data).toEqual({ ok: 'things' });
        expect(refreshCalls).toBe(1);
        expect(sentTo('/things').map(s => s.auth)).toEqual(['Bearer old-token', 'Bearer new-token']);
        expect(storage.getItem('access_token')).toBe('new-token');
        expect(doc.cookie).toMatch(/^has_session=1;/);
    });

    it('sends a valid token straight through without refreshing', async () => {
        storage.setItem('access_token', 'new-token');
        await expect(api.get('/things')).resolves.toMatchObject({ data: { ok: 'things' } });
        expect(refreshCalls).toBe(0);
        expect(sentTo('/things')).toHaveLength(1);
    });

    it('concurrent 401s share a single refresh and all retry with its token', async () => {
        const results = await Promise.all([api.get('/things'), api.get('/other'), api.get('/third')]);
        expect(results.map(r => r.data)).toEqual([{ ok: 'things' }, { ok: 'other' }, { ok: 'third' }]);
        expect(refreshCalls).toBe(1);
        for (const url of ['/things', '/other', '/third']) {
            expect(sentTo(url).map(s => s.auth)).toEqual(['Bearer old-token', 'Bearer new-token']);
        }
    });

    it('a 401 that lands after the refresh finished retries with the new token, not a second refresh', async () => {
        // /slow was sent with the old token but its 401 arrives late.
        routes['/slow'] = async (config) => { await delay(40); return respond(config, 401); };
        const fast = api.get('/things');
        const slow = api.get('/slow');
        await fast;
        expect(refreshCalls).toBe(1);
        routes['/slow'] = guarded({ ok: 'slow' });
        await expect(slow).resolves.toMatchObject({ data: { ok: 'slow' } });
        expect(refreshCalls).toBe(1);
        expect(sentTo('/slow').map(s => s.auth)).toEqual(['Bearer old-token', 'Bearer new-token']);
    });

    it('does not refresh again when the retried request is still 401', async () => {
        validToken = 'never-issued';
        const err = await api.get('/things').catch(e => e);
        expect(err).toBeInstanceOf(AxiosError);
        expect(err.response.status).toBe(401);
        expect(refreshCalls).toBe(1);
        expect(sentTo('/things')).toHaveLength(2);
    });

    it('a later independent 401 can refresh again (the in-flight promise is cleared)', async () => {
        await api.get('/things');
        validToken = 'newer-token';
        refreshImpl = async (config) => respond(config, 200, { access_token: 'newer-token' });
        await expect(api.get('/other')).resolves.toMatchObject({ data: { ok: 'other' } });
        expect(refreshCalls).toBe(2);
        expect(storage.getItem('access_token')).toBe('newer-token');
    });
});

describe('failed refresh', () => {
    it('a refused refresh ends the session once, without looping', async () => {
        refreshImpl = async (config) => respond(config, 401, { detail: 'refresh expired' });
        const results = await Promise.allSettled([api.get('/things'), api.get('/other')]);
        expect(results.every(r => r.status === 'rejected')).toBe(true);
        // The rejection is the refresh's error, not the original request's.
        const reason = (results[0] as PromiseRejectedResult).reason;
        expect(reason.config.url).toMatch(/\/auth\/refresh$/);
        expect(refreshCalls).toBe(1);
        expect(sentTo('/things')).toHaveLength(1);
        expect(sentTo('/other')).toHaveLength(1);
        expect(storage.getItem('access_token')).toBeNull();
        expect(storage.getItem('engagement-context')).toBeNull();
        expect(doc.cookie).toMatch(/^has_session=; .*max-age=0/);
        expect(win.location.href).toBe(`/login?next=${encodeURIComponent('/findings/42?tab=evidence')}`);
    });

    it('does not redirect when already on /login', async () => {
        win.location.pathname = '/login';
        refreshImpl = async (config) => respond(config, 403);
        await expect(api.get('/things')).rejects.toBeInstanceOf(AxiosError);
        expect(win.location.href).toBe('');
        win.location.pathname = '/findings/42';
    });

    it.each([
        ['a 5xx', 503],
        ['a 429', 429],
    ])('keeps the session on %s from /auth/refresh and fails only this request', async (_label, status) => {
        refreshImpl = async (config) => respond(config, status);
        const err = await api.get('/things').catch(e => e);
        expect(err.response.status).toBe(401);           // the original 401, not the refresh error
        expect(err.config.url).toBe('/things');
        expect(storage.getItem('access_token')).toBe('old-token');
        expect(storage.getItem('engagement-context')).not.toBeNull();
        expect(win.location.href).toBe('');
        expect(refreshCalls).toBe(1);
    });

    it('treats a network failure of the refresh as transient', async () => {
        refreshImpl = async (config) => { throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config); };
        await expect(api.get('/things')).rejects.toMatchObject({ response: { status: 401 } });
        expect(storage.getItem('access_token')).toBe('old-token');
        expect(win.location.href).toBe('');
    });
});

describe('requests the interceptor must leave alone', () => {
    it.each(['/auth/login', '/auth/register', '/auth/verify-2fa'])('%s 401 is not refreshed', async (url) => {
        routes[url] = (config) => respond(config, 401, { detail: 'Invalid credentials' });
        const err = await api.post(url, {}).catch(e => e);
        expect(err.response.status).toBe(401);
        expect(refreshCalls).toBe(0);
    });

    it('skipAuthRefresh requests are not refreshed', async () => {
        routes['/auth/step-up'] = (config) => respond(config, 401);
        await expect(api.post('/auth/step-up', {}, { skipAuthRefresh: true })).rejects.toBeInstanceOf(AxiosError);
        expect(refreshCalls).toBe(0);
        expect(sentTo('/auth/step-up')).toHaveLength(1);
    });

    it('non-401 errors are passed through without a refresh', async () => {
        routes['/boom'] = (config) => respond(config, 500);
        await expect(api.get('/boom')).rejects.toMatchObject({ response: { status: 500 } });
        expect(refreshCalls).toBe(0);
    });

    it('does not overwrite an explicit Authorization header', async () => {
        routes['/auth/me'] = (config) => respond(config, 200, { auth: config.headers.Authorization });
        const res = await api.get('/auth/me', { headers: { Authorization: 'Bearer 2fa-pending' } });
        expect(res.data.auth).toBe('Bearer 2fa-pending');
    });

    it('sends no Authorization header when signed out', async () => {
        storage.removeItem('access_token');
        routes['/public'] = (config) => respond(config, 200, { auth: config.headers.Authorization ?? null });
        expect((await api.get('/public')).data.auth).toBeNull();
    });
});

describe('error redaction', () => {
    it('scrubs the bearer token from a rejected request', async () => {
        storage.setItem('access_token', 'new-token');
        routes['/boom'] = (config) => respond(config, 500);
        const err = await api.get('/boom').catch(e => e);
        expect(err.config.headers.Authorization).toBe('<redacted>');
        expect(JSON.stringify(err.config.headers)).not.toContain('new-token');
    });
});
