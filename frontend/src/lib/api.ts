import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
    baseURL: API_URL,
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
                const refreshToken = localStorage.getItem('refresh_token');
                if (!refreshToken) {
                    throw new Error('No refresh token');
                }

                const response = await axios.post(`${API_URL}/auth/refresh`, {
                    refresh_token: refreshToken,
                });

                const { access_token, refresh_token: newRefreshToken } = response.data;
                localStorage.setItem('access_token', access_token);
                localStorage.setItem('refresh_token', newRefreshToken);
                // Renew session cookie on successful refresh
                document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';

                isRefreshing = false;
                onTokenRefreshed(access_token);

                originalRequest.headers.Authorization = `Bearer ${access_token}`;
                return api(originalRequest);
            } catch (refreshError) {
                isRefreshing = false;
                onRefreshFailed();
                // Refresh failed, clear tokens and redirect to login
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
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
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) {
            stopProactiveRefresh();
            return;
        }

        // Don't proactively refresh if a reactive refresh is already in flight
        if (isRefreshing) return;

        try {
            isRefreshing = true;
            const response = await axios.post(`${API_URL}/auth/refresh`, {
                refresh_token: refreshToken,
            });

            const { access_token, refresh_token: newRefreshToken } = response.data;
            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', newRefreshToken);
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
