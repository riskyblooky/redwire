import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface VaultItem {
    id: string;
    engagement_id: string;
    name: string;
    item_type: 'CREDENTIAL' | 'KEY' | 'FILE' | 'NOTE';
    username?: string;
    password?: string;
    note?: string;
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

