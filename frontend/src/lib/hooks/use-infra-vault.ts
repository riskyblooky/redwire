import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ── Types ───────────────────────────────────────────────────────

export interface InfraVaultItem {
    id: string;
    infra_item_id: string;
    name: string;
    item_type: string; // CREDENTIAL, KEY, FILE, NOTE
    username?: string;
    password?: string;
    note?: string;
    filename?: string;
    description?: string;
    created_by?: string;
    updated_by?: string;
    created_by_username?: string;
    created_at: string;
    updated_at: string;
}

export interface InfraVaultAccess {
    user_id: string;
    username: string;
    display_name?: string;
    profile_photo?: string;
    granted_by?: string;
    granted_at: string;
}

export interface InfraVaultAccessCheck {
    has_access: boolean;
    can_manage: boolean;
}

// ── Queries ─────────────────────────────────────────────────────

export function useInfraVault(infraItemId: string) {
    return useQuery({
        queryKey: ['infra-vault', infraItemId],
        queryFn: async () => {
            const { data } = await api.get<InfraVaultItem[]>(`/infra/items/${infraItemId}/vault`);
            return data;
        },
        enabled: !!infraItemId,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useInfraVaultAccessCheck(infraItemId: string) {
    return useQuery({
        queryKey: ['infra-vault-access-check', infraItemId],
        queryFn: async () => {
            const { data } = await api.get<InfraVaultAccessCheck>(`/infra/items/${infraItemId}/vault/check-access`);
            return data;
        },
        enabled: !!infraItemId,
    });
}

export function useInfraVaultAccessList(infraItemId: string) {
    return useQuery({
        queryKey: ['infra-vault-access', infraItemId],
        queryFn: async () => {
            try {
                const { data } = await api.get<InfraVaultAccess[]>(`/infra/items/${infraItemId}/vault/access`);
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        enabled: !!infraItemId,
    });
}

// ── Mutations ───────────────────────────────────────────────────

export function useCreateInfraVaultItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, ...data }: {
            infraItemId: string;
            name: string;
            item_type: string;
            username?: string;
            password?: string;
            note?: string;
            description?: string;
        }) => {
            const { data: result } = await api.post<InfraVaultItem>(`/infra/items/${infraItemId}/vault`, data);
            return result;
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault', vars.infraItemId] });
        },
    });
}

export function useUploadInfraVaultFile() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, name, description, file }: {
            infraItemId: string;
            name: string;
            description?: string;
            file: File;
        }) => {
            const formData = new FormData();
            formData.append('name', name);
            if (description) formData.append('description', description);
            formData.append('file', file);
            const { data } = await api.post<InfraVaultItem>(
                `/infra/items/${infraItemId}/vault/upload`,
                formData,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            return data;
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault', vars.infraItemId] });
        },
    });
}

export function useUpdateInfraVaultItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, vaultId, ...updates }: {
            infraItemId: string;
            vaultId: string;
            [key: string]: any;
        }) => {
            const { data } = await api.put<InfraVaultItem>(`/infra/items/${infraItemId}/vault/${vaultId}`, updates);
            return data;
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault', vars.infraItemId] });
        },
    });
}

export function useDeleteInfraVaultItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, vaultId }: { infraItemId: string; vaultId: string }) => {
            await api.delete(`/infra/items/${infraItemId}/vault/${vaultId}`);
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault', vars.infraItemId] });
        },
    });
}

// ── Access Management ───────────────────────────────────────────

export function useGrantInfraVaultAccess() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, userId }: { infraItemId: string; userId: string }) => {
            await api.post(`/infra/items/${infraItemId}/vault/access?user_id=${userId}`);
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault-access', vars.infraItemId] });
            queryClient.invalidateQueries({ queryKey: ['infra-vault-access-check', vars.infraItemId] });
        },
    });
}

export function useRevokeInfraVaultAccess() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ infraItemId, userId }: { infraItemId: string; userId: string }) => {
            await api.delete(`/infra/items/${infraItemId}/vault/access/${userId}`);
        },
        onSuccess: (_, vars) => {
            queryClient.invalidateQueries({ queryKey: ['infra-vault-access', vars.infraItemId] });
            queryClient.invalidateQueries({ queryKey: ['infra-vault-access-check', vars.infraItemId] });
        },
    });
}

// ── Password Strength Check (Bloom Filter) ──────────────────────

export function useCheckPassword(password: string, debounceMs = 500) {
    return useQuery({
        queryKey: ['check-password', password],
        queryFn: async () => {
            const { data } = await api.post<{ found: boolean }>('/wordlist/check-password', { password });
            return data;
        },
        enabled: !!password && password.length >= 3,
        staleTime: 60_000,
        gcTime: 5 * 60_000,
    });
}

