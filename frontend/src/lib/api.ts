import axios from 'axios';
import { loginUrlForCurrentPage } from './login-redirect';

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
        if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
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
// Refresh the access token 2 minutes before it expires (every 28 minutes for a 30-min token)
const PROACTIVE_REFRESH_INTERVAL_MS = 28 * 60 * 1000; // 28 minutes

let proactiveRefreshTimer: ReturnType<typeof setInterval> | null = null;

function startProactiveRefresh() {
    if (proactiveRefreshTimer) return; // Already running

    proactiveRefreshTimer = setInterval(async () => {
        // If there's no access token in localStorage we're not logged in;
        // the refresh cookie (if any) will be sent automatically, but there
        // is nothing to keep alive on this tab.
        if (!localStorage.getItem('access_token')) {
            stopProactiveRefresh();
            return;
        }

        try {
            // Joins a refresh already in flight rather than starting another.
            await refreshAccessToken();
        } catch {
            // Proactive refresh failed — don't force logout, let the reactive interceptor handle it
        }
    }, PROACTIVE_REFRESH_INTERVAL_MS);
}

function stopProactiveRefresh() {
    if (proactiveRefreshTimer) {
        clearInterval(proactiveRefreshTimer);
        proactiveRefreshTimer = null;
    }
}

// Auto-start proactive refresh if we have tokens (runs in browser only)
if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
        startProactiveRefresh();
    }

    // Listen for login/logout to start/stop proactive refresh
    window.addEventListener('storage', (e) => {
        if (e.key === 'access_token') {
            if (e.newValue) {
                startProactiveRefresh();
            } else {
                stopProactiveRefresh();
            }
        }
    });
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
