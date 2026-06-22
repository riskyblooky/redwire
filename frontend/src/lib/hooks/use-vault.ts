import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

// GHSA-fp69-w2mg-4pqp follow-up: the list / get / create / update
// endpoints return only metadata + has_* + password_looks_like_hash —
// never the decrypted username / password / note. The plaintext fields
// live on ``VaultItemReveal`` and are only populated by the dedicated
// reveal endpoint, which writes an ``accessed_vault_secret``
// activity-log row before returning.
export interface VaultItem {
    id: string;
    engagement_id: string;
    name: string;
    item_type: 'CREDENTIAL' | 'KEY' | 'FILE' | 'NOTE';
    has_username: boolean;
    has_password: boolean;
    has_note: boolean;
    // Server-side classification of the encrypted password value —
    // lets the UI surface a "Crack this hash" affordance without
    // forcing a reveal call first.
    password_looks_like_hash: boolean;
    filename?: string;
    file_path?: string;
    description?: string;
    created_at: string;
    created_by: string;
    created_by_username?: string;
    created_by_profile_photo?: string;
    findings?: { id: string; title: string; severity: string }[];
    testcases?: { id: string; title: string }[];
    assets?: { id: string; name: string; asset_type: string; identifier?: string }[];
}

// Returned by ``GET /vault/{id}/reveal``. Same shape as VaultItem plus
// the three decrypted plaintext fields. Don't cache forever — the
// audit log dedups per (user, item) over 5 minutes, so a stale-cache
// reveal beyond that window won't re-log.
export interface VaultItemReveal extends VaultItem {
    username?: string;
    password?: string;
    note?: string;
}

export function useVaultItems(engagementId: string) {
    return useQuery({
        queryKey: ['engagements', engagementId, 'vault'],
        queryFn: async () => {
            const { data } = await api.get<VaultItem[]>(`/vault?engagement_id=${engagementId}`);
            return data;
        },
        enabled: !!engagementId,
    });
}

// Lazy reveal hook. ``enabled=false`` keeps the query idle so a page
// load doesn't trip every item's audit log. Set ``enabled=true`` on
// eye-icon click; the query fires, the server writes an audit row
// (deduped per 5-min window), and the plaintext lands in the cache.
// Setting ``enabled=false`` again removes the query from refetch
// rotation but keeps the cached value until the cache entry expires
// or the user navigates away.
export function useVaultItemReveal(itemId: string | null | undefined, enabled: boolean) {
    return useQuery({
        queryKey: ['vault', itemId, 'reveal'],
        queryFn: async () => {
            const { data } = await api.get<VaultItemReveal>(`/vault/${itemId}/reveal`);
            return data;
        },
        enabled: !!itemId && enabled,
        // Match the server-side 5-minute dedup window. Within that
        // window, a refetch is treated as the same access event and
        // shouldn't generate a fresh audit row — staleTime here
        // mirrors that intent so React Query reuses the cached
        // reveal rather than hitting the endpoint again.
        staleTime: 5 * 60 * 1000,
        gcTime: 5 * 60 * 1000,
    });
}

export function useLinkVaultToFinding() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, findingId }: { vaultItemId: string; findingId: string }) => {
            await api.post(`/vault/${vaultItemId}/findings/${findingId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

export function useUnlinkVaultFromFinding() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, findingId }: { vaultItemId: string; findingId: string }) => {
            await api.delete(`/vault/${vaultItemId}/findings/${findingId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['findings'] });
        },
    });
}

export function useLinkVaultToTestCase() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, testcaseId }: { vaultItemId: string; testcaseId: string }) => {
            await api.post(`/vault/${vaultItemId}/testcases/${testcaseId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

export function useUnlinkVaultFromTestCase() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, testcaseId }: { vaultItemId: string; testcaseId: string }) => {
            await api.delete(`/vault/${vaultItemId}/testcases/${testcaseId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

export function useLinkVaultToAsset() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, assetId }: { vaultItemId: string; assetId: string }) => {
            await api.post(`/vault/${vaultItemId}/assets/${assetId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

export function useUnlinkVaultFromAsset() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ vaultItemId, assetId }: { vaultItemId: string; assetId: string }) => {
            await api.delete(`/vault/${vaultItemId}/assets/${assetId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

