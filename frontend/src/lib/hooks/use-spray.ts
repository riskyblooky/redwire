import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../api';

// ── Types ───────────────────────────────────────────────────────

export interface SprayResultPreview {
    username: string;
    domain?: string | null;
    result: string;       // success / success_admin / failed / locked / disabled
    status_code?: string | null;
    is_admin: boolean;
    target_host?: string | null;
    target_port?: number | null;
    password?: string | null;  // Plaintext during preview/commit; encrypted server-side
}

export interface SprayImportPreview {
    protocol?: string | null;
    target_host?: string | null;
    target_port?: number | null;
    target_hostname?: string | null;
    domain?: string | null;
    password_used?: string | null;
    total_attempts: number;
    successful: number;
    locked_out: number;
    failed: number;
    host_count: number;
    command_line?: string | null;
    matched_asset_count: number;     // Hosts already in the engagement asset list
    unmatched_hosts: string[];       // Hosts the spray touched that aren't inventoried yet
    results: SprayResultPreview[];
    imported_from?: string | null;
}

export interface SprayCampaign {
    id: string;
    engagement_id: string;
    name: string;
    protocol?: string | null;
    target_host?: string | null;
    target_port?: number | null;
    target_hostname?: string | null;
    domain?: string | null;
    password_used?: string | null;
    total_attempts: number;
    successful: number;
    locked_out: number;
    failed: number;
    status?: string | null;
    notes?: string | null;
    imported_from?: string | null;
    created_at: string;
    updated_at: string;
    created_by?: string | null;
}

export interface SprayResultResponse {
    id: string;
    campaign_id: string;
    username: string;
    domain?: string | null;
    result: string;
    status_code?: string | null;
    is_admin: boolean;
    target_host?: string | null;
    target_port?: number | null;
    vault_item_id?: string | null;
    asset_id?: string | null;
    created_at: string;
}

export interface SprayCampaignDetail extends SprayCampaign {
    results: SprayResultResponse[];
}


// ── Hooks ───────────────────────────────────────────────────────

export function useSprayCampaigns(engagementId: string) {
    return useQuery({
        queryKey: ['spray', 'campaigns', engagementId],
        queryFn: async () => {
            const { data } = await api.get<SprayCampaign[]>('/spray/campaigns', {
                params: { engagement_id: engagementId },
            });
            return data;
        },
        enabled: !!engagementId,
    });
}

export function useSprayCampaign(campaignId: string) {
    return useQuery({
        queryKey: ['spray', 'campaign', campaignId],
        queryFn: async () => {
            const { data } = await api.get<SprayCampaignDetail>(`/spray/campaigns/${campaignId}`);
            return data;
        },
        enabled: !!campaignId,
    });
}

export function useImportSpray() {
    return useMutation({
        mutationFn: async ({ file, engagementId }: { file: File; engagementId: string }) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('engagement_id', engagementId);
            const { data } = await api.post<SprayImportPreview>('/spray/import', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
    });
}

export function useCommitSpray() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: {
            engagement_id: string;
            name: string;
            protocol?: string | null;
            target_host?: string | null;
            target_port?: number | null;
            target_hostname?: string | null;
            domain?: string | null;
            password_used?: string | null;
            notes?: string | null;
            imported_from?: string | null;
            create_missing_assets?: boolean;
            results: SprayResultPreview[];
        }) => {
            const { data } = await api.post<SprayCampaign>('/spray/commit', payload);
            return data;
        },
        onSuccess: (_data, variables) => {
            queryClient.invalidateQueries({ queryKey: ['spray', 'campaigns', variables.engagement_id] });
        },
    });
}

export function useDeleteSprayCampaign() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ campaignId, engagementId }: { campaignId: string; engagementId: string }) => {
            await api.delete(`/spray/campaigns/${campaignId}`);
            return { engagementId };
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['spray', 'campaigns', data.engagementId] });
        },
    });
}

export function useVaultSprayHits() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ campaignId, engagementId }: { campaignId: string; engagementId: string }) => {
            const { data } = await api.post<{ vaulted: number; message: string }>(
                `/spray/campaigns/${campaignId}/vault-hits`
            );
            return { ...data, engagementId, campaignId };
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['spray', 'campaigns', data.engagementId] });
            queryClient.invalidateQueries({ queryKey: ['spray', 'campaign', data.campaignId] });
            // Vault items are keyed under ['engagements', id, 'vault'], so invalidating
            // the engagement subtree refreshes them along with anything else that
            // depends on engagement-level state.
            queryClient.invalidateQueries({ queryKey: ['engagements', data.engagementId] });
        },
    });
}
