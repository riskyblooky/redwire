import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export interface Group {
    id: string;
    name: string;
    description: string | null;
}

export interface GroupCreate {
    name: string;
    description?: string;
}

export interface EngagementRole {
    id: string;
    name: string;
    description: string | null;
}

export interface EngagementRoleCreate {
    name: string;
    description?: string;
}

// --- Group Hooks ---

export function useGroups() {
    return useQuery({
        queryKey: ['admin', 'groups'],
        queryFn: async () => {
            try {
                const { data } = await api.get<Group[]>('/admin/permissions/groups');
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useCreateGroup() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (group: GroupCreate) => {
            const { data } = await api.post<Group>('/admin/permissions/groups', group);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

export function useUpdateGroup() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...update }: Partial<GroupCreate> & { id: string }) => {
            const { data } = await api.patch<Group>(`/admin/permissions/groups/${id}`, update);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

export function useDeleteGroup() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/admin/permissions/groups/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

// --- Engagement Role Hooks ---

export function useEngagementRoles() {
    return useQuery({
        queryKey: ['admin', 'engagement-roles'],
        queryFn: async () => {
            try {
                const { data } = await api.get<EngagementRole[]>('/admin/permissions/engagement-roles');
                return data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

export function useCreateEngagementRole() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (role: EngagementRoleCreate) => {
            const { data } = await api.post<EngagementRole>('/admin/permissions/engagement-roles', role);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}

export function useUpdateEngagementRole() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...update }: Partial<EngagementRoleCreate> & { id: string }) => {
            const { data } = await api.patch<EngagementRole>(`/admin/permissions/engagement-roles/${id}`, update);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}

export function useDeleteEngagementRole() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/admin/permissions/engagement-roles/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}
