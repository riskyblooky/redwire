import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';
import { User, UserUpdate } from './use-auth';

export function useAdminConfig() {
    return useQuery<{ session_timeout_hours: number }>({
        queryKey: ['admin', 'config'],
        queryFn: async () => {
            const response = await api.get('/admin/config');
            return response.data;
        },
        staleTime: Infinity,
    });
}

export function useAdminUsers() {
    return useQuery<User[]>({
        queryKey: ['admin', 'users'],
        queryFn: async () => {
            const response = await api.get('/admin/users');
            return response.data;
        },
        refetchInterval: 15_000,
        refetchOnWindowFocus: true,
    });
}

export function useUpdateUser() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ userId, data }: { userId: string; data: UserUpdate }) => {
            const response = await api.patch(`/admin/users/${userId}`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
        },
    });
}

export function useDeleteUser() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (userId: string) => {
            await api.delete(`/admin/users/${userId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
        },
    });
}
export function useCreateUser() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: {
            username: string;
            email: string;
            password: string;
            full_name?: string;
            role: string;
        }) => {
            const response = await api.post('/admin/users', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
        },
    });
}

export function useResetPassword() {
    return useMutation({
        mutationFn: async (userId: string) => {
            const response = await api.post(`/admin/users/${userId}/reset-password`);
            return response.data;
        },
    });
}



// ── AI Settings hooks ────────────────────────────────────────────────

export interface AiSettings {
    ai_enabled: string;
    ai_api_key: string;
    ai_api_url: string;
    // "true" / "false". Mirrors ldap_tls_verify: when "false", the
    // backend's httpx client that hits ai_api_url skips certificate
    // verification. For operators pointing at an internal AI gateway
    // with a self-signed / private-CA cert. Default "true".
    ai_tls_verify: string;
    // JSON object string of custom headers (name → value) merged into
    // every outbound AI-API request. Empty string means "none". The
    // backend validates (RFC 7230 header-token names, no CRLF in
    // values, ≤32 entries) and silently drops any invalid row so a
    // stale config can't brick chat.
    ai_custom_headers: string;
    // Numeric string. Empty falls back to the 120s default. Bounded
    // [5, 600] on the backend; a stray 0 or "abc" also falls back.
    ai_request_timeout_seconds: string;
    // JSON object string of extra query params merged onto every
    // outbound AI-API request URL. Empty string means "none".
    ai_extra_query: string;
    // "true" / "false". When "false", the chat endpoint fetches the
    // full response non-streaming and forwards it as a single chunk
    // event — for proxies that strip SSE. Default "true".
    ai_streaming_enabled: string;
    ai_default_model: string;
    chatbot_enabled: string;
    mcp_enabled: string;
    ai_write_tools_enabled: string;
    mcp_url: string;
    // GHSA-f4j9-gvm9-frjw follow-up: token-budget compaction settings.
    // Numeric strings — backend stores everything in the AiSetting
    // (key, value) KV shape and coerces in the chat handler.
    ai_max_context_tokens?: string;
    ai_compact_keep_recent_turns?: string;
    ai_compact_threshold_pct?: string;
}

export function useAiSettings() {
    return useQuery<AiSettings>({
        queryKey: ['admin', 'ai-settings'],
        queryFn: async () => {
            const response = await api.get('/ai/settings');
            return response.data;
        },
        staleTime: 30_000,
    });
}

export function useUpdateAiSettings() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (data: Partial<AiSettings>) => {
            const response = await api.put('/ai/settings', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'ai-settings'] });
            queryClient.invalidateQueries({ queryKey: ['ai', 'status'] });
        },
    });
}

export function useFetchAiModels() {
    return useMutation({
        mutationFn: async () => {
            const response = await api.post('/ai/fetch-models');
            return response.data as { models: string[] };
        },
    });
}


// ── Stats scope-mode toggle ──────────────────────────────────────────
//
// Controls whether non-admin callers of /analytics/* and /stats/* see
// platform-wide counts (with identifying fields stripped) or only
// engagements they're assigned to.

export type StatsScopeMode = 'global' | 'scoped';

export function useStatsScopeMode() {
    return useQuery<{ mode: StatsScopeMode }>({
        queryKey: ['admin', 'stats-scope-mode'],
        queryFn: async () => (await api.get('/admin/settings/stats-scope-mode')).data,
        staleTime: 60_000,
    });
}

export function useUpdateStatsScopeMode() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (mode: StatsScopeMode) => {
            const response = await api.put('/admin/settings/stats-scope-mode', { mode });
            return response.data as { mode: StatsScopeMode };
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'stats-scope-mode'] });
            // Stats responses change shape, so blow away the caches.
            queryClient.invalidateQueries({ queryKey: ['analytics'] });
            queryClient.invalidateQueries({ queryKey: ['stats'] });
        },
    });
}

