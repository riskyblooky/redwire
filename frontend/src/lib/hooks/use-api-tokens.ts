import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface ApiToken {
    id: string;
    name: string;
    token_prefix: string;
    permission: string;
    created_at: string;
    last_used_at: string | null;
    expires_at: string | null;
    is_active: boolean;
}

/** A service token as the admin list returns it (any user's). */
export interface AdminApiToken extends ApiToken {
    user_id: string;
    username?: string;
    user_full_name?: string;
    created_by: string | null;
}

export interface CreatedApiToken {
    raw_token: string;
}

export interface ApiTokenCreate {
    name: string;
    permission: 'ro' | 'rw';
    expires_at?: string;
}

// ['api-tokens', 'mine'] and ['api-tokens', 'all']: a create or revoke on
// either screen refreshes both (an admin revoking their own token, say).
const KEY = ['api-tokens'];

export function useMyApiTokens() {
    return useQuery({
        queryKey: [...KEY, 'mine'],
        queryFn: async () => (await api.get<ApiToken[]>('/api-tokens')).data,
        staleTime: 30_000,
    });
}

export function useCreateMyApiToken() {
    const queryClient = useQueryClient();
    return useMutation({
        // Step-up (GHSA-7rcx-8hqc-mm5f): local users send password (+ TOTP).
        // A 401 here is a wrong step-up password / code, not an expired session.
        mutationFn: async (body: ApiTokenCreate & { password?: string; totp_code?: string }) =>
            (await api.post<CreatedApiToken>('/api-tokens', body, { skipAuthRefresh: true })).data,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useRevokeMyApiToken() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => { await api.delete(`/api-tokens/${id}`); },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useAdminApiTokens() {
    return useQuery({
        queryKey: [...KEY, 'all'],
        queryFn: async () => (await api.get<AdminApiToken[]>('/admin/api-tokens')).data,
        staleTime: 30_000,
    });
}

export function useCreateAdminApiToken() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (body: ApiTokenCreate & { user_id: string }) =>
            (await api.post<CreatedApiToken>('/admin/api-tokens', body)).data,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}

export function useRevokeAdminApiToken() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => { await api.delete(`/admin/api-tokens/${id}`); },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    });
}
