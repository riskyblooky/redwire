import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface Tag {
    id: string;
    name: string;
    color: string | null;
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

export function useTags() {
    return useQuery<Tag[]>({
        queryKey: ['tags'],
        queryFn: async () => {
            const { data } = await api.get('/tags');
            return data;
        },
    });
}

export function useCreateTag() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (tagData: { name: string; color?: string }) => {
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
