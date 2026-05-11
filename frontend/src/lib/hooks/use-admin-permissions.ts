import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// Types
export interface PermissionInfo {
    name: string;
    value: string;
    is_global: boolean;
    is_engagement: boolean;
}

export interface PermissionCategory {
    category: string;
    permissions: PermissionInfo[];
}

export interface Group {
    id: string;
    name: string;
    description?: string;
    permissions: string[];
    member_count?: number;
    is_system?: boolean;
    is_default?: boolean;
}

export interface EngagementRole {
    id: string;
    name: string;
    description?: string;
    permissions: string[];
}

// Permission Categories
export function usePermissionCategories() {
    return useQuery<PermissionCategory[]>({
        queryKey: ['admin', 'permissions', 'list'],
        queryFn: async () => {
            try {
                const response = await api.get('/admin/permissions/list');
                return response.data;
            } catch (err: any) {
                if (err?.response?.status === 403) return [];
                throw err;
            }
        },
        retry: (count, err: any) => err?.response?.status !== 403 && count < 3,
    });
}

// Groups
export function useGroups() {
    return useQuery<Group[]>({
        queryKey: ['admin', 'groups'],
        queryFn: async () => {
            try {
                const response = await api.get('/admin/permissions/groups');
                return response.data;
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
        mutationFn: async (data: { name: string; description?: string }) => {
            const response = await api.post('/admin/permissions/groups', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

export function useUpdateGroup() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ groupId, data }: { groupId: string; data: { name: string; description?: string } }) => {
            const response = await api.put(`/admin/permissions/groups/${groupId}`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

export function useDeleteGroup() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (groupId: string) => {
            await api.delete(`/admin/permissions/groups/${groupId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

export function useUpdateGroupPermissions() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ groupId, permissions }: { groupId: string; permissions: string[] }) => {
            const response = await api.put(`/admin/permissions/groups/${groupId}/permissions`, { permissions });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'groups'] });
        },
    });
}

// Engagement Roles
export function useEngagementRoles() {
    return useQuery<EngagementRole[]>({
        queryKey: ['admin', 'engagement-roles'],
        queryFn: async () => {
            try {
                const response = await api.get('/admin/permissions/engagement-roles');
                return response.data;
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
        mutationFn: async (data: { name: string; description?: string }) => {
            const response = await api.post('/admin/permissions/engagement-roles', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}

export function useUpdateEngagementRole() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ roleId, data }: { roleId: string; data: { name: string; description?: string } }) => {
            const response = await api.put(`/admin/permissions/engagement-roles/${roleId}`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}

export function useDeleteEngagementRole() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (roleId: string) => {
            await api.delete(`/admin/permissions/engagement-roles/${roleId}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}

export function useUpdateEngagementRolePermissions() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ roleId, permissions }: { roleId: string; permissions: string[] }) => {
            const response = await api.put(`/admin/permissions/engagement-roles/${roleId}/permissions`, { permissions });
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'engagement-roles'] });
        },
    });
}
