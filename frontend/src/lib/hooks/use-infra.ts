import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ── Types ───────────────────────────────────────────────────────

export type InfraType = 'VPS' | 'C2' | 'REDIRECTOR' | 'PROXY' | 'PHISHING' | 'JUMPBOX' | 'OTHER';
export type InfraStatus = 'ACTIVE' | 'DECOMMISSIONED' | 'STANDBY';

export interface InfraItem {
    id: string;
    name: string;
    infra_type: InfraType;
    status: InfraStatus;
    ip_address?: string;
    internal_ip?: string;
    hostname?: string;
    provider?: string;
    region?: string;
    os?: string;
    point_of_presence?: string;
    notes?: string;
    created_by?: string;
    created_at: string;
    updated_at: string;
}

export interface LinkedEntity {
    id: string;
    title: string;
    type: 'finding' | 'testcase' | 'note';
}

export interface InfraItemDetail extends InfraItem {
    linked_findings: LinkedEntity[];
    linked_testcases: LinkedEntity[];
    linked_notes: LinkedEntity[];
    linked_count: number;
}

// ── Queries ─────────────────────────────────────────────────────

export function useInfraItems(params: {
    search?: string;
    infra_type?: string;
    status?: string;
    limit?: number;
    offset?: number;
} = {}) {
    return useQuery({
        queryKey: ['infra-items', params],
        queryFn: async () => {
            try {
                const { data } = await api.get<{ items: InfraItem[]; total: number }>('/infra/items', { params });
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return { items: [], total: 0 };
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useInfraItem(id: string) {
    return useQuery({
        queryKey: ['infra-items', id],
        queryFn: async () => {
            const { data } = await api.get<InfraItemDetail>(`/infra/items/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useInfraByEntity(entityType: 'finding' | 'testcase' | 'note', entityId: string) {
    return useQuery({
        queryKey: ['infra-by-entity', entityType, entityId],
        queryFn: async () => {
            try {
                const { data } = await api.get<InfraItem[]>('/infra/by-entity', {
                    params: { entity_type: entityType, entity_id: entityId },
                });
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        enabled: !!entityId,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

// ── Mutations ───────────────────────────────────────────────────

export function useCreateInfraItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (item: {
            name: string;
            infra_type?: string;
            status?: string;
            ip_address?: string;
            internal_ip?: string;
            hostname?: string;
            provider?: string;
            region?: string;
            os?: string;
            point_of_presence?: string;
            notes?: string;
        }) => {
            const { data } = await api.post<InfraItem>('/infra/items', item);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['infra-items'] });
        },
    });
}

export function useUpdateInfraItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string; [key: string]: any }) => {
            const { data } = await api.put<InfraItem>(`/infra/items/${id}`, updates);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['infra-items'] });
        },
    });
}

export function useDeleteInfraItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/infra/items/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['infra-items'] });
        },
    });
}

// ── Linking ─────────────────────────────────────────────────────

export function useLinkInfra() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, entityType, entityId }: { itemId: string; entityType: string; entityId: string }) => {
            await api.post(`/infra/items/${itemId}/link`, { entity_type: entityType, entity_id: entityId });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['infra-items'] });
            queryClient.invalidateQueries({ queryKey: ['infra-by-entity'] });
        },
    });
}

export function useUnlinkInfra() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, entityType, entityId }: { itemId: string; entityType: string; entityId: string }) => {
            await api.delete(`/infra/items/${itemId}/link`, { data: { entity_type: entityType, entity_id: entityId } });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['infra-items'] });
            queryClient.invalidateQueries({ queryKey: ['infra-by-entity'] });
        },
    });
}
