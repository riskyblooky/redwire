import { create } from 'zustand';
import { User } from '@/lib/types';
import api, { startProactiveRefresh, stopProactiveRefresh } from '@/lib/api';

interface AuthState {
    user: User | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    needsRedirect: boolean;
    // 2FA state
    requires2fa: boolean;
    pendingToken: string | null;
    pendingCredentials: { username: string; password: string } | null;
    // Force password change state
    mustChangePassword: boolean;
    login: (username: string, password: string) => Promise<void>;
    verifyTotp: (code: string) => Promise<void>;
    verifySsoTotp: (code: string, pendingToken: string) => Promise<void>;
    cancel2fa: () => void;
    logout: () => void;
    checkAuth: () => Promise<void>;
    setUser: (user: User) => void;
    clearMustChangePassword: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    isLoading: true,
    isAuthenticated: false,
    needsRedirect: false,
    requires2fa: false,
    pendingToken: null,
    pendingCredentials: null,
    mustChangePassword: false,

    login: async (username: string, password: string) => {
        try {
            const response = await api.post('/auth/login', { username, password });
            const { access_token, refresh_token, requires_2fa, must_change_password } = response.data;

            if (requires_2fa) {
                // Store pending token for the 2FA verification step
                set({ requires2fa: true, pendingToken: access_token, pendingCredentials: { username, password }, isLoading: false });
                return;
            }

            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
            // Set session cookie for Next.js middleware (24h to match refresh token)
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            startProactiveRefresh();

            // Fetch user info
            const userResponse = await api.get('/auth/me');
            set({
                user: userResponse.data,
                isAuthenticated: true,
                isLoading: false,
                needsRedirect: false,
                requires2fa: false,
                pendingCredentials: null,
                mustChangePassword: !!must_change_password,
            });
        } catch (error) {
            set({ user: null, isAuthenticated: false, isLoading: false });
            throw error;
        }
    },

    verifyTotp: async (code: string) => {
        const { pendingToken } = get();
        if (!pendingToken) throw new Error('No pending 2FA verification');

        try {
            const response = await api.post('/auth/verify-2fa', { code }, {
                headers: { Authorization: `Bearer ${pendingToken}` },
            });
            const { access_token, refresh_token, must_change_password } = response.data;

            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            startProactiveRefresh();

            const userResponse = await api.get('/auth/me');
            set({
                user: userResponse.data,
                isAuthenticated: true,
                isLoading: false,
                needsRedirect: false,
                requires2fa: false,
                pendingToken: null,
                pendingCredentials: null,
                mustChangePassword: !!must_change_password,
            });
        } catch (error) {
            throw error;
        }
    },

    cancel2fa: () => {
        set({ requires2fa: false, pendingToken: null, pendingCredentials: null });
    },

    verifySsoTotp: async (code: string, pendingToken: string) => {
        try {
            const response = await api.post('/auth/verify-2fa', { code }, {
                headers: { Authorization: `Bearer ${pendingToken}` },
            });
            const { access_token, refresh_token, must_change_password } = response.data;

            localStorage.setItem('access_token', access_token);
            localStorage.setItem('refresh_token', refresh_token);
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            startProactiveRefresh();

            const userResponse = await api.get('/auth/me');
            set({
                user: userResponse.data,
                isAuthenticated: true,
                isLoading: false,
                needsRedirect: false,
                requires2fa: false,
                pendingCredentials: null,
                mustChangePassword: !!must_change_password,
            });
        } catch (error) {
            throw error;
        }
    },

    logout: () => {
        // Capture tokens BEFORE clearing localStorage
        const token = localStorage.getItem('access_token');
        const refreshToken = localStorage.getItem('refresh_token');

        // Clear local state immediately for responsive UX
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
        stopProactiveRefresh();
        set({ user: null, isAuthenticated: false, needsRedirect: false, requires2fa: false, pendingCredentials: null, mustChangePassword: false });

        // Then blacklist the token on the backend (fire-and-forget)
        // We pass the token explicitly since localStorage is already cleared
        if (token) {
            api.post('/auth/logout', refreshToken ? { refresh_token: refreshToken } : {}, {
                headers: { Authorization: `Bearer ${token}` }
            }).catch(() => {
                // Best-effort: if this fails, the token will still expire naturally
            });
        }

        // Hard redirect to login to ensure clean state reset
        window.location.href = '/login';
    },

    checkAuth: async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            // Clear session cookie if no token
            document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
            set({ isAuthenticated: false, isLoading: false });
            return;
        }

        try {
            const response = await api.get('/auth/me');
            // Refresh session cookie on successful auth check
            document.cookie = 'has_session=1; path=/; max-age=86400; SameSite=Lax';
            set({
                user: response.data,
                isAuthenticated: true,
                isLoading: false,
                needsRedirect: false,
                mustChangePassword: !!response.data.must_change_password,
            });
        } catch (error) {
            // Clear session cookie on failed auth check
            document.cookie = 'has_session=; path=/; max-age=0; SameSite=Lax';
            set({ user: null, isAuthenticated: false, isLoading: false, needsRedirect: false });
        }
    },
    setUser: (user: User) => set({ user }),
    clearMustChangePassword: () => set({ mustChangePassword: false }),
}));
