import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

import { Asset } from '../types';

export interface AssetCreate {
    custom_fields?: Record<string, unknown>;
    engagement_id: string;
    name: string;
    asset_type: string;
    identifier: string;
    description?: string;
    notes?: string;
    is_pwned?: boolean;
    is_scanned?: boolean;
    in_scope?: boolean;
}

export interface AssetUpdate {
    custom_fields?: Record<string, unknown>;
    id: string;
    engagement_id?: string;
    name?: string;
    asset_type?: string;
    identifier?: string;
    description?: string;
    notes?: string;
    is_pwned?: boolean;
    is_scanned?: boolean;
    in_scope?: boolean;
}

interface UseAssetsOptions {
    engagementId?: string;
    search?: string;
    port?: number;
    service?: string;
    portState?: string;
    sortBy?: string;
    sortOrder?: string;
    skip?: number;
    limit?: number;
}

// Fetch assets with optional filters
export function useAssets(engagementIdOrOptions?: string | UseAssetsOptions) {
    // Support both simple string and options object for backward compatibility
    const options: UseAssetsOptions = typeof engagementIdOrOptions === 'string'
        ? { engagementId: engagementIdOrOptions }
        : (engagementIdOrOptions ?? {});

    const { engagementId, search, port, service, portState, sortBy, sortOrder, skip, limit } = options;

    const query = useQuery({
        queryKey: ['assets', engagementId ?? 'all', search ?? '', port ?? '', service ?? '', portState ?? '', sortBy ?? '', sortOrder ?? '', skip ?? 0, limit ?? 100],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (engagementId) params.engagement_id = engagementId;
            if (search) params.search = search;
            if (port !== undefined) params.port = String(port);
            if (service) params.service = service;
            if (portState) params.port_state = portState;
            if (sortBy) params.sort_by = sortBy;
            if (sortOrder) params.sort_order = sortOrder;
            if (skip !== undefined) params.skip = String(skip);
            if (limit !== undefined) params.limit = String(limit);
            const { data } = await api.get<{ items: Asset[]; total: number }>('/assets', { params });
            return data;
        },
        staleTime: 30_000,
    });

    return {
        ...query,
        data: query.data?.items ?? [],
        total: query.data?.total ?? 0,
    };
}

// Fetch single asset
export function useAsset(id: string) {
    return useQuery({
        queryKey: ['assets', id],
        queryFn: async () => {
            const { data } = await api.get<Asset>(`/assets/${id}`);
            return data;
        },
        enabled: !!id,
        staleTime: 30_000,
    });
}

// Create asset
export function useCreateAsset() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (asset: AssetCreate) => {
            const { data } = await api.post<Asset>('/assets', asset);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Update asset
export function useUpdateAsset() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...asset }: AssetUpdate) => {
            const { data } = await api.put<Asset>(`/assets/${id}`, asset);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['assets', data.id] });
        },
    });
}

// Delete asset
export function useDeleteAsset() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/assets/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Import assets from file
export interface ImportResult {
    created: number;
    skipped: number;
    ports_added: number;
    errors: string[];
}

export function useImportAssets() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ file, engagementId }: { file: File; engagementId: string }) => {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('engagement_id', engagementId);
            const { data } = await api.post<ImportResult>('/assets/import', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Add port to asset
export function useAddAssetPort() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ assetId, ...portData }: {
            assetId: string;
            port_number: number;
            protocol: 'TCP' | 'UDP';
            service_name?: string;
            state?: 'OPEN' | 'CLOSED' | 'FILTERED';
            version?: string;
        }) => {
            const { data } = await api.post(`/assets/${assetId}/ports`, portData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Delete port from asset
export function useDeleteAssetPort() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ assetId, portId }: { assetId: string; portId: string }) => {
            await api.delete(`/assets/${assetId}/ports/${portId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Update port on asset
export function useUpdateAssetPort() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ assetId, portId, ...portData }: {
            assetId: string;
            portId: string;
            port_number?: number;
            protocol?: 'TCP' | 'UDP';
            service_name?: string;
            state?: 'OPEN' | 'CLOSED' | 'FILTERED';
            version?: string;
        }) => {
            const { data } = await api.put(`/assets/${assetId}/ports/${portId}`, portData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['assets'] });
        },
    });
}

// Fetch distinct ports and services for filter dropdowns
export function useAssetPortFilters(engagementId?: string) {
    return useQuery({
        queryKey: ['asset-port-filters', engagementId ?? 'all'],
        queryFn: async () => {
            const params: Record<string, string> = {};
            if (engagementId) params.engagement_id = engagementId;
            const { data } = await api.get<{ ports: { port_number: number; protocol: string }[]; services: string[] }>('/assets/port-filters', { params });
            return data;
        },
        enabled: !!engagementId,
    });
}
