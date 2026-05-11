import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface ConfigurableType {
    id: string;
    category: string;
    name: string;
    description: string | null;
    color: string;
    is_system: boolean;
    sort_order: number;
}

export interface ConfigurableTypeCreate {
    name: string;
    description?: string;
    color?: string;
}

export interface ConfigurableTypeUpdate {
    name?: string;
    description?: string;
    color?: string;
}

// Fetch all configurable types for a category
export function useConfigurableTypes(category: string) {
    return useQuery({
        queryKey: ['configurable-types', category],
        queryFn: async () => {
            const { data } = await api.get<ConfigurableType[]>(`/configurable-types/${category}`);
            return data;
        },
        enabled: !!category,
    });
}

// Create a configurable type
export function useCreateConfigurableType(category: string) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (data: ConfigurableTypeCreate) => {
            const { data: result } = await api.post<ConfigurableType>(`/configurable-types/${category}`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['configurable-types', category] });
        },
    });
}

// Update a configurable type
export function useUpdateConfigurableType(category: string) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...data }: ConfigurableTypeUpdate & { id: string }) => {
            const { data: result } = await api.put<ConfigurableType>(`/configurable-types/${category}/${id}`, data);
            return result;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['configurable-types', category] });
        },
    });
}

// Delete a configurable type
export function useDeleteConfigurableType(category: string) {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/configurable-types/${category}/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['configurable-types', category] });
        },
    });
}
