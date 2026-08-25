import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export type TagEntityType = 'finding' | 'testcase' | 'engagement';

export interface Tag {
    id: string;
    name: string;
    color: string | null;
    entity_type: TagEntityType;
    created_at: string;
}

export function useCanManageTags() {
    return useQuery<boolean>({
        queryKey: ['tags', 'can-manage'],
        queryFn: async () => {
            const { data } = await api.get('/tags/can-manage');
            return data;
        },
    });
}

export function useTags(entityType?: TagEntityType) {
    return useQuery<Tag[]>({
        queryKey: ['tags', entityType ?? 'all'],
        queryFn: async () => {
            const { data } = await api.get('/tags', {
                params: entityType ? { entity_type: entityType } : undefined,
            });
            return data;
        },
    });
}

export function useCreateTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (tagData: { name: string; color?: string; entity_type?: TagEntityType }) => {
            const { data } = await api.post('/tags', tagData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
        },
    });
}

export function useUpdateTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...tagData }: { id: string; name?: string; color?: string }) => {
            const { data } = await api.put(`/tags/${id}`, tagData);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
        },
    });
}

export function useDeleteTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/tags/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['tags'] });
        },
    });
}
