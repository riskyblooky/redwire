import axios from 'axios';

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
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// --- Token refresh with race condition protection ---
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

function subscribeTokenRefresh(cb: (token: string) => void) {
    refreshSubscribers.push(cb);
}

function onTokenRefreshed(newToken: string) {
    refreshSubscribers.forEach((cb) => cb(newToken));
    refreshSubscribers = [];
}

function onRefreshFailed() {
    refreshSubscribers = [];
}

// Response interceptor to handle token expiration
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        // Handle 401 Unauthorized (Token expiration)
        // Skip refresh logic for auth endpoints — their 401s are expected business errors
        const url = originalRequest?.url || '';
        const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/verify-2fa');
        if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
            originalRequest._retry = true;

            // If already refreshing, queue this request to retry after refresh completes
            if (isRefreshing) {
                return new Promise((resolve, reject) => {
                    subscribeTokenRefresh((newToken: string) => {
                        originalRequest.headers.Authorization = `Bearer ${newToken}`;
                        resolve(api(originalRequest));
                    });
                    // If refresh fails while waiting, the promise will just hang
                    // which is fine because onRefreshFailed + redirect happens
                });
            }

            isRefreshing = true;

            try {
                // Refresh token now lives in an HttpOnly cookie set by
                // /auth/login (GHSA-gv65-p25x-qrqj); the JS side just calls
                // /auth/refresh with credentials and reads the new access
                // token back from the JSON body.
                const response = await axios.post(`${API_URL}/auth/refresh`, {}, {
                    withCredentials: true,
                });

                const { access_token } = response.data;
                localStorage.setItem('access_token', access_token);
                // Renew session cookie on successful refresh
                document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';

                isRefreshing = false;
                onTokenRefreshed(access_token);

                originalRequest.headers.Authorization = `Bearer ${access_token}`;
                return api(originalRequest);
            } catch (refreshError) {
                isRefreshing = false;
                onRefreshFailed();
                // Refresh failed, clear access token and redirect to login.
                // The refresh cookie is cleared by /auth/logout, or by the
                // server when it issues a 401 on an expired/missing cookie.
                localStorage.removeItem('access_token');
                document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
                window.location.href = '/login';
                return Promise.reject(refreshError);
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

        // Don't proactively refresh if a reactive refresh is already in flight
        if (isRefreshing) return;

        try {
            isRefreshing = true;
            const response = await axios.post(`${API_URL}/auth/refresh`, {}, {
                withCredentials: true,
            });

            const { access_token } = response.data;
            localStorage.setItem('access_token', access_token);
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            isRefreshing = false;
        } catch {
            isRefreshing = false;
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

export { startProactiveRefresh, stopProactiveRefresh };
export default api;
