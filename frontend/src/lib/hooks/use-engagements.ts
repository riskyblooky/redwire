import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { UserRole } from '../types';
import { EngagementRole } from './use-rbac';

export interface AssignedUser {
    id: string;
    username: string;
    full_name: string | null;
    profile_photo: string | null;
    role: UserRole;
}

export interface EngagementAssignment {
    user_id: string;
    engagement_id: string;
    role_id: string | null;
    role: EngagementRole | null;
}

export interface EngagementAssignmentCreate {
    user_id: string;
    role_id?: string;
}

export interface EngagementPhase {
    id: string;
    engagement_id: string;
    phase_name: string;
    sort_order: number;
    planned_start: string | null;
    planned_end: string | null;
}

export interface Engagement {
    id: string;
    name: string;
    client_name: string;
    client_id?: string;
    engagement_type: string;
    status: string;
    description: string | null;
    scope: string | null;
    objectives: string | null;
    start_date: string;
    end_date: string | null;
    created_by: string;
    created_at: string;
    updated_at: string;
    assigned_users: AssignedUser[];
    assignment_details: EngagementAssignment[];
    phases: EngagementPhase[];
}

export interface EngagementCreate {
    name: string;
    client_name: string;
    client_id?: string;
    engagement_type: string;
    status?: string;
    description?: string;
    scope?: string;
    objectives?: string;
    start_date?: string;
    end_date?: string;
    assigned_user_ids?: string[];
    assignments?: EngagementAssignmentCreate[];
}

export interface EngagementUpdate extends Partial<EngagementCreate> {
    id: string;
}

// Fetch all engagements. Pass `includeProposed` for admins / team leads
// who want to see PROPOSED rows mixed in with the rest. The backend
// 403s if a non-privileged caller asks for them.
export function useEngagements(options?: { includeProposed?: boolean }) {
    const includeProposed = !!options?.includeProposed;
    return useQuery({
        queryKey: ['engagements', { includeProposed }],
        queryFn: async () => {
            const url = includeProposed ? '/engagements?include_proposed=true' : '/engagements';
            const { data } = await api.get<Engagement[]>(url);
            return data;
        },
        staleTime: 30_000,
    });
}

// Fetch single engagement
export function useEngagement(id: string) {
    return useQuery({
        queryKey: ['engagements', id],
        queryFn: async () => {
            const { data } = await api.get<Engagement>(`/engagements/${id}`);
            return data;
        },
        enabled: !!id,
        retry: (failureCount, error: any) => {
            // Don't retry on authorization errors
            if (error.response?.status === 403 || error.response?.status === 401) return false;
            return failureCount < 3;
        },
        staleTime: 30_000,
    });
}

// Create engagement
export function useCreateEngagement() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (engagement: EngagementCreate) => {
            const { data } = await api.post<Engagement>('/engagements', engagement);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
        },
    });
}

// Update engagement
export function useUpdateEngagement() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...engagement }: EngagementUpdate) => {
            const { data } = await api.put<Engagement>(`/engagements/${id}`, engagement);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', data.id] });
        },
    });
}

// Delete engagement
export function useDeleteEngagement() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/engagements/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
        },
    });
}

// Fetch only PROPOSED engagements (for Planning page)
export function useProposedEngagements() {
    return useQuery({
        queryKey: ['engagements', 'proposed'],
        queryFn: async () => {
            const { data } = await api.get<Engagement[]>('/engagements/proposed');
            return data;
        },
        staleTime: 30_000,
    });
}

// Fetch ALL engagements including PROPOSED (for Planning Gantt chart)
export function useAllEngagementsIncludingProposed() {
    return useQuery({
        queryKey: ['engagements', 'all-with-proposed'],
        queryFn: async () => {
            const { data } = await api.get<Engagement[]>('/engagements?include_proposed=true');
            return data;
        },
        staleTime: 30_000,
    });
}

// Update phases for an engagement
export function useUpdateEngagementPhases() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ engagementId, phases }: { engagementId: string; phases: { id: string; planned_start?: string; planned_end?: string }[] }) => {
            const { data } = await api.put<EngagementPhase[]>(`/engagements/${engagementId}/phases`, phases);
            return data;
        },
        onSuccess: (_, variables) => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', variables.engagementId] });
        },
    });
}

// Generate default phases for an existing engagement
export function useGenerateEngagementPhases() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (engagementId: string) => {
            const { data } = await api.post<EngagementPhase[]>(`/engagements/${engagementId}/phases/generate`);
            return data;
        },
        onSuccess: (_, engagementId) => {
            queryClient.invalidateQueries({ queryKey: ['engagements'] });
            queryClient.invalidateQueries({ queryKey: ['engagements', engagementId] });
        },
    });
}
