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
    tags: Array<{ id: string; name: string; color: string | null }>;
    marking_profile_id?: string | null;
    default_classification_level?: string | null;
    default_classification_suffix?: string | null;
    ceiling_classification_level?: string | null;
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
    // Optional tag ids on create. Empty array / omission = no tags.
    tag_ids?: string[];
    marking_profile_id?: string | null;
    default_classification_level?: string | null;
    default_classification_suffix?: string | null;
    ceiling_classification_level?: string | null;
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
            // Callers of this hook expect the full engagement list for
            // pickers/dropdowns (asset new, finding new, calendar, dashboard,
            // etc.). Pull the max page size in one request — the paginated
            // /engagements list page uses `useEngagementsPage` instead.
            const params = new URLSearchParams();
            params.set('limit', '500');
            if (includeProposed) params.set('include_proposed', 'true');
            const { data } = await api.get<Engagement[]>(`/engagements?${params.toString()}`);
            return data;
        },
        staleTime: 30_000,
    });
}

export interface EngagementsPage {
    items: Engagement[];
    total: number;
    page: number;      // 1-indexed for display
    pageSize: number;
}

export interface EngagementsPageQuery {
    includeProposed?: boolean;
    page?: number;      // 1-indexed
    pageSize?: number;
    q?: string;
    status?: string;    // exact EngagementStatus value; omit or 'all' for no filter
    type?: string;      // exact engagement_type; omit or 'all' for no filter
    startDateFrom?: string;   // ISO date
    startDateTo?: string;     // ISO date
    sortBy?: 'name' | 'engagement_type' | 'status' | 'start_date' | 'end_date' | 'created_at';
    sortOrder?: 'asc' | 'desc';
}

/**
 * Paginated engagements list, used by the /engagements page. Backend sets
 * ``X-Total-Count`` with the pre-pagination row count so the client can
 * render page controls; the header is exposed via CORS in main.py.
 * ``placeholderData`` keeps the prior page visible during the next fetch
 * so page-flip doesn't flicker.
 *
 * Search / filter / sort all execute server-side (see
 * ``backend/routers/engagements.py::get_engagements``) — the returned page
 * already reflects the whole matching dataset, not just the current window.
 */
export function useEngagementsPage(options?: EngagementsPageQuery) {
    const includeProposed = !!options?.includeProposed;
    const page = Math.max(1, options?.page ?? 1);
    const pageSize = options?.pageSize ?? 25;
    const skip = (page - 1) * pageSize;
    const q = options?.q?.trim() || '';
    const statusFilter = options?.status && options.status !== 'all' ? options.status : '';
    const typeFilter = options?.type && options.type !== 'all' ? options.type : '';
    const dateFrom = options?.startDateFrom || '';
    const dateTo = options?.startDateTo || '';
    const sortBy = options?.sortBy || 'start_date';
    const sortOrder = options?.sortOrder || 'desc';

    return useQuery<EngagementsPage>({
        queryKey: ['engagements', 'page', {
            includeProposed, page, pageSize, q, statusFilter, typeFilter,
            dateFrom, dateTo, sortBy, sortOrder,
        }],
        queryFn: async () => {
            const params = new URLSearchParams();
            params.set('skip', String(skip));
            params.set('limit', String(pageSize));
            if (includeProposed) params.set('include_proposed', 'true');
            if (q) params.set('q', q);
            if (statusFilter) params.set('status', statusFilter);
            if (typeFilter) params.set('type', typeFilter);
            if (dateFrom) params.set('start_date_from', dateFrom);
            if (dateTo) params.set('start_date_to', dateTo);
            params.set('sort_by', sortBy);
            params.set('sort_order', sortOrder);
            const res = await api.get<Engagement[]>(`/engagements?${params.toString()}`);
            const totalHeader = res.headers?.['x-total-count'] ?? res.headers?.['X-Total-Count'];
            const total = totalHeader ? Number(totalHeader) : res.data.length;
            return { items: res.data, total, page, pageSize };
        },
        staleTime: 30_000,
        placeholderData: (prev) => prev,
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
