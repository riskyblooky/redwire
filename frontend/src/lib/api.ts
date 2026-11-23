import axios from 'axios';
import { loginUrlForCurrentPage } from './login-redirect';

declare module 'axios' {
    interface AxiosRequestConfig {
        /** Don't treat this request's 401 as an expired session (see the 401 handler). */
        skipAuthRefresh?: boolean;
    }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
    baseURL: API_URL,
    // Send the HttpOnly refresh-token cookie on /auth/refresh & /auth/logout.
    // Backend CORS already has allow_credentials=True; this is the matching
    // half. GHSA-gv65-p25x-qrqj.
    withCredentials: true,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request interceptor to add auth token
api.interceptors.request.use(
    (config) => {
        // Don't clobber an explicit Authorization header (e.g. /auth/verify-2fa
        // sends the 2FA-pending token directly, while a stale access_token may
        // still be in localStorage from a prior session).
        if (config.headers.Authorization) {
            return config;
        }
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
            // Which token this request went out with (see the 401 handler).
            Object.assign(config, { _sentToken: token });
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// --- Token refresh with race condition protection ---
// One /auth/refresh at a time: every caller (the 401 interceptor, the
// proactive timer, WebSocket reconnects) awaits the same in-flight promise,
// so all of them get its token or its error. (A flag plus a subscriber list
// left requests queued behind a proactive or failed refresh hanging forever.)
let refreshInFlight: Promise<string> | null = null;

/** A failure that says nothing about the session: no response at all, a
 *  server error, or rate limiting. */
export function isTransientAuthFailure(err: unknown): boolean {
    const status = (err as { response?: { status?: number } } | null)?.response?.status;
    return !status || status >= 500 || status === 429;
}

function refreshAccessToken(): Promise<string> {
    if (!refreshInFlight) {
        refreshInFlight = (async () => {
            try {
                // Refresh token lives in an HttpOnly cookie set by /auth/login
                // (GHSA-gv65-p25x-qrqj); the new access token comes back in the body.
                const response = await axios.post(`${API_URL}/auth/refresh`, {}, { withCredentials: true });
                const { access_token } = response.data;
                localStorage.setItem('access_token', access_token);
                // Renew session cookie on successful refresh
                document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
                scheduleProactiveRefresh();
                return access_token as string;
            } finally {
                refreshInFlight = null;
            }
        })();
    }
    return refreshInFlight;
}

// GHSA-7x2f-ff7r-h388 #15 (CWE-532): scrub the Authorization header
// from any axios error object BEFORE it propagates to a downstream
// `.catch(err => console.error(err))` (~32 sites across the frontend)
// or a React error boundary. The axios error carries `error.config`
// with the request's raw `headers.Authorization: "Bearer <JWT>"` —
// logging that object to the browser console persisted the caller's
// JWT into DevTools and any error-tracking sink hooked up. Runs on
// every rejected response, not just 401 — a 500 or network error
// carries the same bearer in the same slot.
function _redactAuthOnError(err: any): any {
    try {
        if (err?.config?.headers?.Authorization) {
            err.config.headers.Authorization = '<redacted>';
        }
        if (err?.request?.config?.headers?.Authorization) {
            err.request.config.headers.Authorization = '<redacted>';
        }
        // Some axios shapes stash the original request inside
        // response.request.config too — belt-and-suspenders.
        if (err?.response?.config?.headers?.Authorization) {
            err.response.config.headers.Authorization = '<redacted>';
        }
    } catch {
        // Never let the redactor itself throw — the caller's business
        // error must still propagate.
    }
    return err;
}

// Response interceptor to handle token expiration
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        _redactAuthOnError(error);
        const originalRequest = error.config;

        // Handle 401 Unauthorized (Token expiration)
        // Skip refresh logic for auth endpoints — their 401s are expected business errors
        const url = originalRequest?.url || '';
        const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/verify-2fa');
        // skipAuthRefresh: the request's 401 is a credential check of its own
        // (step-up password / TOTP), not an expired session — don't refresh
        // the session and resend the password.
        if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint && !originalRequest.skipAuthRefresh) {
            originalRequest._retry = true;

            // Sent with a token that has since been replaced (a refresh
            // finished while it was in flight): retry with the current one
            // rather than rotating the refresh cookie again.
            const current = localStorage.getItem('access_token');
            const sentWith = originalRequest._sentToken;
            if (current && sentWith && sentWith !== current && !refreshInFlight) {
                originalRequest.headers.Authorization = `Bearer ${current}`;
                return api(originalRequest);
            }

            try {
                const access_token = await refreshAccessToken();
                originalRequest.headers.Authorization = `Bearer ${access_token}`;
                return api(originalRequest);
            } catch (refreshError) {
                // Only a refresh the server refused (401/403...) ends the
                // session. No response (network down, backend restarting
                // during a deploy), a 5xx or a 429 is transient: keep the
                // session and fail just this request, instead of logging
                // the user out of every tab.
                if (isTransientAuthFailure(refreshError)) {
                    return Promise.reject(_redactAuthOnError(error));
                }
                // Refresh failed, clear access token and redirect to login.
                // The refresh cookie is cleared by /auth/logout, or by the
                // server when it issues a 401 on an expired/missing cookie.
                localStorage.removeItem('access_token');
                localStorage.removeItem('engagement-context'); // per-user selection (engagement-store)
                document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
                // Session expired mid-use: come back to this page after sign-in.
                if (window.location.pathname !== '/login') window.location.href = loginUrlForCurrentPage();
                return Promise.reject(_redactAuthOnError(refreshError));
            }
        }

        return Promise.reject(error);
    }
);

// --- Proactive token refresh ---
// One timer, set from the current token's `exp`: refresh a little before it
// runs out (10% of the lifetime, 30 s to 2 min ahead). It used to fire every
// 28 minutes, which only fit the default 30-minute token: with a shorter
// ACCESS_TOKEN_EXPIRE_MINUTES the token lapsed first (every tab then took the
// 401-and-retry path), and with a longer one it refreshed needlessly. Every
// successful refresh, from any caller or another tab, reschedules it.
const MIN_LEAD_MS = 30_000;
const MAX_LEAD_MS = 120_000;
const RETRY_MS = 60_000;

let proactiveRefreshTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleProactiveRefresh(delayMs?: number) {
    if (proactiveRefreshTimer) clearTimeout(proactiveRefreshTimer);
    proactiveRefreshTimer = null;
    const token = localStorage.getItem('access_token');
    if (!token) return; // not signed in on this browser: nothing to keep alive
    if (delayMs === undefined) {
        const exp = jwtExpiry(token);
        if (exp === null) return; // unreadable token: leave it to the 401 interceptor
        const msLeft = exp * 1000 - Date.now();
        const lifetime = Math.max(msLeft, 0);
        const lead = Math.min(MAX_LEAD_MS, Math.max(MIN_LEAD_MS, lifetime / 10));
        delayMs = Math.max(msLeft - lead, 1_000);
    }
    proactiveRefreshTimer = setTimeout(async () => {
        proactiveRefreshTimer = null;
        if (!localStorage.getItem('access_token')) return;
        try {
            // Joins a refresh already in flight; success reschedules.
            await refreshAccessToken();
        } catch {
            // Don't force logout here — the reactive interceptor owns that.
            // Try again shortly in case it was a blip.
            scheduleProactiveRefresh(RETRY_MS);
        }
    }, delayMs);
}

function startProactiveRefresh() {
    scheduleProactiveRefresh();
}

function stopProactiveRefresh() {
    if (proactiveRefreshTimer) {
        clearTimeout(proactiveRefreshTimer);
        proactiveRefreshTimer = null;
    }
}

// Auto-start proactive refresh if we have tokens (runs in browser only)
if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
        startProactiveRefresh();
    }

    // Whose session this tab is showing. The token is shared by all tabs, so a
    // sign-in as someone else in another tab silently made this tab act as
    // them while it still showed the first user's data and state.
    let tabSub = token ? jwtSub(token) : null;

    // Listen for login/logout to start/stop proactive refresh
    window.addEventListener('storage', (e) => {
        if (e.key === 'access_token') {
            const prev = (e.oldValue ? jwtSub(e.oldValue) : null) ?? tabSub;
            const next = e.newValue ? jwtSub(e.newValue) : null;
            if (prev && next && prev !== next) {
                // Another account: start over as that user (or the login page).
                window.location.reload();
                return;
            }
            if (next) tabSub = next;
            if (e.newValue) {
                startProactiveRefresh();
            } else {
                stopProactiveRefresh();
            }
        }
    });
}

/** `sub` (user id) of a JWT, or null if it can't be read. */
function jwtSub(token: string): string | null {
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        return typeof payload.sub === 'string' ? payload.sub : null;
    } catch {
        return null;
    }
}

/** `exp` (seconds) of a JWT, or null if it can't be read. */
function jwtExpiry(token: string): number | null {
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        return typeof payload.exp === 'number' ? payload.exp : null;
    } catch {
        return null;
    }
}

/**
 * The access token, refreshed first if it expires within a minute. For
 * WebSocket (re)connects, which send the token themselves and so never pass
 * through the axios 401 → refresh interceptor: a socket that reconnects
 * after the 30-minute token lapsed (laptop slept, proactive timer drifted)
 * would otherwise be refused forever. Joins any refresh already in flight;
 * on a failed refresh it returns the current token and lets the
 * server decide.
 */
export async function getFreshAccessToken(): Promise<string | null> {
    const token = localStorage.getItem('access_token');
    if (!token) return null;
    const exp = jwtExpiry(token);
    if (exp === null || exp * 1000 - Date.now() > 60_000) return token;
    try {
        return await refreshAccessToken();
    } catch {
        return localStorage.getItem('access_token');
    }
}

/**
 * fetch() for responses axios can't hand over incrementally (SSE streams),
 * with the same auth handling as the axios instance: a fresh token up front
 * and, on a 401, one refresh and retry. `path` is relative to the API base.
 */
export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const send = (token: string | null) => fetch(`${API_URL}${path}`, {
        ...init,
        headers: { ...(init.headers as Record<string, string> | undefined), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    });
    const resp = await send(await getFreshAccessToken());
    if (resp.status !== 401) return resp;
    try {
        return await send(await refreshAccessToken());
    } catch {
        return resp;
    }
}

export { startProactiveRefresh, stopProactiveRefresh };
export default api;

/**
 * Extract a human-readable message from an axios/FastAPI error.
 *
 * FastAPI returns two error shapes:
 *   - 4xx with a string detail: {"detail": "Not found"}
 *   - 422 with a Pydantic validation array: {"detail": [{"type","loc","msg","input","ctx"}, ...]}
 *
 * The array shape is what crashes React when rendered directly. This
 * helper flattens both shapes to a string suitable for toast.error() or
 * setState in error banners. Falls back to the supplied default if it
 * can't find anything meaningful.
 */
export function apiErrorMessage(err: any, fallback = 'Something went wrong'): string {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d) => {
                if (typeof d === 'string') return d;
                if (d && typeof d === 'object' && typeof d.msg === 'string') {
                    const field = Array.isArray(d.loc) ? d.loc.filter((p: any) => p !== 'body').join('.') : '';
                    return field ? `${field}: ${d.msg}` : d.msg;
                }
                return String(d);
            })
            .join('; ');
    }
    if (detail && typeof detail === 'object') {
        if (typeof (detail as any).msg === 'string') return (detail as any).msg;
        return fallback;
    }
    if (typeof err?.message === 'string') return err.message;
    return fallback;
}
