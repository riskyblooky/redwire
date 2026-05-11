import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ── Types ───────────────────────────────────────────────────────

export interface IntelItem {
    id: string;
    title: string;
    content?: string;
    source?: string;
    source_url?: string;
    item_type: 'CVE' | 'ADVISORY' | 'ARTICLE' | 'ZINE' | 'EXPLOIT' | 'OTHER';
    severity?: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';
    cve_id?: string;
    published_at?: string;
    feed_id?: string;
    created_by?: string;
    created_at: string;
    updated_at: string;
    linked_count: number;
}

export interface LinkedEntity {
    id: string;
    title: string;
    type: 'finding' | 'testcase' | 'note';
}

export interface IntelAttachment {
    id: string;
    intel_item_id: string;
    original_filename: string;
    file_size: number;
    mime_type?: string;
    created_by?: string;
    created_at: string;
}

export interface IntelItemDetail extends IntelItem {
    linked_findings: LinkedEntity[];
    linked_testcases: LinkedEntity[];
    linked_notes: LinkedEntity[];
    attachments: IntelAttachment[];
}

export interface IntelFeed {
    id: string;
    name: string;
    url: string;
    feed_type: string;
    enabled: boolean;
    last_fetched_at?: string;
    created_at: string;
}

export interface IntelItemsResponse {
    items: IntelItem[];
    total: number;
    limit: number;
    offset: number;
}

// ── Intel Items ─────────────────────────────────────────────────

export function useIntelItems(params?: { search?: string; item_type?: string; severity?: string; sort_by?: string; sort_dir?: string; limit?: number; offset?: number }) {
    return useQuery({
        queryKey: ['intel-items', params],
        queryFn: async () => {
            try {
                const { data } = await api.get<IntelItemsResponse>('/intel/items', { params });
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return { items: [], total: 0, limit: params?.limit ?? 50, offset: params?.offset ?? 0 } as IntelItemsResponse;
                throw err;
            }
        },
        staleTime: 30_000,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useIntelItem(id: string) {
    return useQuery({
        queryKey: ['intel-items', id],
        queryFn: async () => {
            const { data } = await api.get<IntelItemDetail>(`/intel/items/${id}`);
            return data;
        },
        enabled: !!id,
        staleTime: 30_000,
    });
}

export function useIntelByEntity(entityType: 'finding' | 'testcase' | 'note', entityId: string) {
    return useQuery({
        queryKey: ['intel-by-entity', entityType, entityId],
        queryFn: async () => {
            try {
                const { data } = await api.get<IntelItem[]>('/intel/by-entity', {
                    params: { entity_type: entityType, entity_id: entityId },
                });
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        enabled: !!entityId,
        staleTime: 30_000,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useCreateIntelItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (item: { title: string; content?: string; source?: string; source_url?: string; item_type?: string; severity?: string; cve_id?: string; published_at?: string }) => {
            const { data } = await api.post<IntelItem>('/intel/items', item);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
        },
    });
}

export function useUpdateIntelItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string; [key: string]: any }) => {
            const { data } = await api.put<IntelItem>(`/intel/items/${id}`, updates);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
        },
    });
}

export function useDeleteIntelItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/intel/items/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
        },
    });
}

// ── Linking ─────────────────────────────────────────────────────

export function useLinkIntel() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, entityType, entityId }: { itemId: string; entityType: string; entityId: string }) => {
            await api.post(`/intel/items/${itemId}/link`, { entity_type: entityType, entity_id: entityId });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
            queryClient.invalidateQueries({ queryKey: ['intel-by-entity'] });
        },
    });
}

export function useUnlinkIntel() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, entityType, entityId }: { itemId: string; entityType: string; entityId: string }) => {
            await api.delete(`/intel/items/${itemId}/link`, { data: { entity_type: entityType, entity_id: entityId } });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
            queryClient.invalidateQueries({ queryKey: ['intel-by-entity'] });
        },
    });
}

// ── Attachments ─────────────────────────────────────────────────

export function useUploadIntelAttachment() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, files }: { itemId: string; files: File[] }) => {
            const formData = new FormData();
            files.forEach(f => formData.append('files', f));
            const { data } = await api.post<IntelAttachment[]>(`/intel/items/${itemId}/attachments`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
        },
    });
}

export function useDeleteIntelAttachment() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ itemId, attachmentId }: { itemId: string; attachmentId: string }) => {
            await api.delete(`/intel/items/${itemId}/attachments/${attachmentId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
        },
    });
}

// ── Feeds ───────────────────────────────────────────────────────

export function useIntelFeeds() {
    return useQuery({
        queryKey: ['intel-feeds'],
        queryFn: async () => {
            try {
                const { data } = await api.get<IntelFeed[]>('/intel/feeds');
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        staleTime: 60_000,
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useCreateIntelFeed() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (feed: { name: string; url: string; feed_type?: string; enabled?: boolean }) => {
            const { data } = await api.post<IntelFeed>('/intel/feeds', feed);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-feeds'] });
        },
    });
}

export function useDeleteIntelFeed() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/intel/feeds/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-feeds'] });
        },
    });
}

export function useRefreshFeeds() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await api.post('/intel/feeds/refresh');
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['intel-items'] });
            queryClient.invalidateQueries({ queryKey: ['intel-feeds'] });
        },
    });
}
