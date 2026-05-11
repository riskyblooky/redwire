import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';

export type ResourceType = 'engagement' | 'finding' | 'asset' | 'testcase' | 'evidence' | 'cleanup_artifact' | 'finding_remediation';

export interface Thread {
    id: string;
    engagement_id: string;
    resource_type: ResourceType;
    resource_id: string | null;
    title: string;
    created_by: string;
    created_at: string;
    is_resolved: boolean;
    comment_count: number;
}

export interface ThreadCreate {
    engagement_id: string;
    resource_type: ResourceType;
    resource_id?: string | null;
    title: string;
}

// - [ ] Implement sorting for resource lists
//     - [ ] Sorting for Findings (Severity, Status, Created)
//     - [ ] Sorting for Assets (Type, Identifier, Name)
//     - [ ] Sorting for TestCases (Category, Status, Title)
//   - [ ] Fix real-time update issues on back navigation
//   - [ ] Create "Log" tab in Engagement dashboard
export interface Comment {
    id: string;
    thread_id: string;
    content: string;
    created_by: string;
    created_at: string;
    is_resolvable: boolean;
    is_resolved: boolean;
    resolved_by: string | null;
    resolved_at: string | null;
    author_name: string | null;
    resolver_name: string | null;
}

export interface CommentCreate {
    thread_id: string;
    content: string;
    is_resolvable?: boolean;
}

export interface ActivityLog {
    id: string;
    engagement_id: string;
    user_id: string;
    action: string;
    resource_type: ResourceType;
    resource_id: string;
    resource_name: string | null;
    details: string | null;
    created_at: string;
    user_name: string | null;
}

// Threads
export function useThreads(params?: { engagement_id?: string; resource_type?: ResourceType; resource_id?: string }) {
    return useQuery({
        queryKey: ['threads', params],
        queryFn: async () => {
            const { data } = await api.get<Thread[]>('/discussions/threads', { params });
            return data;
        },
        // Driven by WS discussion_update events, no polling needed
    });
}

export function useThread(id: string) {
    return useQuery({
        queryKey: ['threads', id],
        queryFn: async () => {
            const { data } = await api.get<Thread>(`/discussions/threads/${id}`);
            return data;
        },
        enabled: !!id,
    });
}

export function useCreateThread() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (thread: ThreadCreate) => {
            const { data } = await api.post<Thread>('/discussions/threads', thread);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['threads'] });
            // Invalidate findings/assets/testcases to update unresolved_thread_count
            queryClient.invalidateQueries({ queryKey: ['findings'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

export function useUpdateThread() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string; title?: string; is_resolved?: boolean }) => {
            const { data } = await api.put<Thread>(`/discussions/threads/${id}`, updates);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['threads'] });
            queryClient.invalidateQueries({ queryKey: ['threads', data.id] });
            // Aggressively invalidate findings/assets/testcases to update unresolved_thread_count
            queryClient.invalidateQueries({ queryKey: ['findings'], refetchType: 'all' });
            queryClient.invalidateQueries({ queryKey: ['assets'], refetchType: 'all' });
            queryClient.invalidateQueries({ queryKey: ['testcases'], refetchType: 'all' });
        },
    });
}

export function useResolveThread() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (threadId: string) => {
            const { data } = await api.put<Thread>(`/discussions/threads/${threadId}/resolve`);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['threads'] });
            queryClient.invalidateQueries({ queryKey: ['threads', data.id] });
            // Aggressively invalidate findings/assets/testcases to update unresolved_thread_count
            queryClient.invalidateQueries({ queryKey: ['findings'], refetchType: 'all' });
            queryClient.invalidateQueries({ queryKey: ['assets'], refetchType: 'all' });
            queryClient.invalidateQueries({ queryKey: ['testcases'], refetchType: 'all' });
        },
    });
}

export function useDeleteThread() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/discussions/threads/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['threads'] });
            // Invalidate findings/assets/testcases to update unresolved_thread_count
            queryClient.invalidateQueries({ queryKey: ['findings'] });
            queryClient.invalidateQueries({ queryKey: ['assets'] });
            queryClient.invalidateQueries({ queryKey: ['testcases'] });
        },
    });
}

// Comments
export function useComments(thread_id: string) {
    return useQuery({
        queryKey: ['comments', thread_id],
        queryFn: async () => {
            const { data } = await api.get<Comment[]>('/discussions/comments', { params: { thread_id } });
            return data;
        },
        enabled: !!thread_id,
        // Driven by WS discussion_update events, no polling needed
    });
}

export function useCreateComment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (comment: CommentCreate) => {
            const { data } = await api.post<Comment>('/discussions/comments', comment);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['comments', data.thread_id] });
            queryClient.invalidateQueries({ queryKey: ['threads'] });
        },
    });
}

export function useResolveComment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            const { data } = await api.put<Comment>(`/discussions/comments/${id}/resolve`);
            return data;
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['comments', data.thread_id] });
        },
    });
}

export function useDeleteComment() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({ id, thread_id }: { id: string; thread_id: string }) => {
            await api.delete(`/discussions/comments/${id}`);
            return { thread_id };
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['comments', data.thread_id] });
            queryClient.invalidateQueries({ queryKey: ['threads'] });
        },
    });
}

// Activity Log
export function useActivityLog(engagement_id: string, resource_type?: ResourceType) {
    return useQuery({
        queryKey: ['activity', engagement_id, resource_type],
        queryFn: async () => {
            const params: any = { engagement_id };
            if (resource_type) params.resource_type = resource_type;
            const { data } = await api.get<ActivityLog[]>('/discussions/activity', { params });
            return data;
        },
        enabled: !!engagement_id,
    });
}
