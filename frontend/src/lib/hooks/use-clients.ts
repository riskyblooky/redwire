import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { Client, ClientType } from '../types';

// ============ Client Types ============

export function useClientTypes() {
    return useQuery({
        queryKey: ['client-types'],
        queryFn: async () => {
            const { data } = await api.get<ClientType[]>('/client-types');
            return data;
        },
    });
}

export function useCreateClientType() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: { name: string; description?: string; color?: string }) => {
            const { data } = await api.post<ClientType>('/client-types', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['client-types'] });
        },
    });
}

export function useUpdateClientType() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: { id: string; name?: string; description?: string; color?: string }) => {
            const { data } = await api.put<ClientType>(`/client-types/${id}`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['client-types'] });
        },
    });
}

export function useDeleteClientType() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/client-types/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['client-types'] });
        },
    });
}

// ============ Clients ============

export function useClients() {
    return useQuery({
        queryKey: ['clients'],
        queryFn: async () => {
            const { data } = await api.get<Client[]>('/clients');
            return data;
        },
    });
}

export function useClientTree() {
    return useQuery({
        queryKey: ['clients', 'tree'],
        queryFn: async () => {
            const { data } = await api.get<Client[]>('/clients/tree');
            return data;
        },
    });
}

export function useClient(id: string) {
    return useQuery({
        queryKey: ['clients', id],
        queryFn: async () => {
            const { data } = await api.get<Client>(`/clients/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateClient() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: {
            name: string;
            description?: string;
            client_type_id?: string;
            parent_id?: string;
            contact_name?: string;
            contact_email?: string;
            notes?: string;
        }) => {
            const { data } = await api.post<Client>('/clients', payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['clients'] });
        },
    });
}

export function useUpdateClient() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...payload }: {
            id: string;
            name?: string;
            description?: string;
            client_type_id?: string;
            parent_id?: string | null;
            contact_name?: string;
            contact_email?: string;
            notes?: string;
        }) => {
            const { data } = await api.put<Client>(`/clients/${id}`, payload);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['clients'] });
        },
    });
}

export function useDeleteClient() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/clients/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['clients'] });
        },
    });
}

export function useReorderClients() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (items: { id: string; sort_order: number; parent_id?: string | null }[]) => {
            await api.post('/clients/reorder', { items });
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['clients'] });
        },
    });
}


// ============ Client Access ============

export interface ClientAccessUser {
    user_id: string;
    username: string;
    full_name: string | null;
    email: string;
    profile_photo: string | null;
    granted_at: string | null;
}

export function useClientAccess(clientId: string | null) {
    return useQuery<ClientAccessUser[]>({
        queryKey: ['clients', clientId, 'access'],
        queryFn: async () => {
            const { data } = await api.get<ClientAccessUser[]>(`/clients/${clientId}/access`);
            return data;
        },
        enabled: !!clientId,
    });
}

export function useGrantClientAccess() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ clientId, userId }: { clientId: string; userId: string }) => {
            await api.post(`/clients/${clientId}/access`, { user_id: userId });
        },
        onSuccess: (_data, vars) => {
            queryClient.invalidateQueries({ queryKey: ['clients', vars.clientId, 'access'] });
        },
    });
}

export function useRevokeClientAccess() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ clientId, userId }: { clientId: string; userId: string }) => {
            await api.delete(`/clients/${clientId}/access/${userId}`);
        },
        onSuccess: (_data, vars) => {
            queryClient.invalidateQueries({ queryKey: ['clients', vars.clientId, 'access'] });
        },
    });
}


// ============ Stats / Trends / Engagement comparison ============

export interface EngagementSummary {
    id: string;
    name: string;
    status: string;
    engagement_type: string | null;
    client_id: string | null;
    client_name: string | null;
    start_date: string | null;
    end_date: string | null;
    finding_count: number;
    findings_by_severity: Record<string, number>;
    findings_by_status: Record<string, number>;
    open_findings: number;
    closed_findings: number;
    mttr_days: number | null;
}

export interface ClientStats {
    client_id: string;
    include_descendants: boolean;
    engagement_count: number;
    engagements_by_status: Record<string, number>;
    finding_count: number;
    findings_by_severity: Record<string, number>;
    findings_by_status: Record<string, number>;
    open_findings: number;
    closed_findings: number;
    mttr_days: number | null;
    first_engagement_at: string | null;
    last_engagement_at: string | null;
}

export interface EngagementCompare {
    a: EngagementSummary;
    b: EngagementSummary;
    delta: {
        finding_count: number;
        open_findings: number;
        closed_findings: number;
        by_severity: Record<string, number>;
        mttr_days: number | null;
    };
}

export function useClientStats(clientId: string | null, includeDescendants = true) {
    return useQuery({
        queryKey: ['clients', clientId, 'stats', includeDescendants],
        queryFn: async () => {
            const { data } = await api.get<ClientStats>(`/clients/${clientId}/stats`, {
                params: { include_descendants: includeDescendants },
            });
            return data;
        },
        enabled: !!clientId,
        staleTime: 30_000,
    });
}

export function useClientEngagements(clientId: string | null, includeDescendants = true) {
    return useQuery({
        queryKey: ['clients', clientId, 'engagements-summary', includeDescendants],
        queryFn: async () => {
            const { data } = await api.get<EngagementSummary[]>(`/clients/${clientId}/engagements`, {
                params: { include_descendants: includeDescendants },
            });
            return data;
        },
        enabled: !!clientId,
        staleTime: 30_000,
    });
}

export function useCompareEngagements(a: string | null, b: string | null) {
    return useQuery({
        queryKey: ['engagements', 'compare', a, b],
        queryFn: async () => {
            const { data } = await api.get<EngagementCompare>('/engagements/compare/summary', {
                params: { a, b },
            });
            return data;
        },
        enabled: !!a && !!b && a !== b,
        staleTime: 30_000,
    });
}

