import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface EngagementType {
    id: string;
    name: string;
    description: string | null;
    color: string;
    is_system: boolean;
    sort_order: number;
}

export interface EngagementTypeCreate {
    name: string;
    description?: string;
    color?: string;
}

export interface EngagementTypeUpdate {
    name?: string;
    description?: string;
    color?: string;
}

// Fetch all engagement types
export function useEngagementTypes() {
    return useQuery({
        queryKey: ['engagement-types'],
        queryFn: async () => {
            const { data } = await api.get<EngagementType[]>('/engagement-types');
            return data;
        },
    });
}

// Create engagement type
export function useCreateEngagementType() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: EngagementTypeCreate) => {
            const { data: result } = await api.post<EngagementType>('/engagement-types', data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagement-types'] });
        },
    });
}

// Update engagement type
export function useUpdateEngagementType() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...data }: EngagementTypeUpdate & { id: string }) => {
            const { data: result } = await api.put<EngagementType>(`/engagement-types/${id}`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagement-types'] });
        },
    });
}

// Delete engagement type
export function useDeleteEngagementType() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/engagement-types/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagement-types'] });
        },
    });
}
