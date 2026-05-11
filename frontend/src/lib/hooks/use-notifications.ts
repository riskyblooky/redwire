import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

export interface NotificationItem {
    id: string;
    user_id: string;
    event_type: string;
    title: string;
    message?: string;
    link?: string;
    is_read: boolean;
    actor_id?: string;
    actor_name?: string;
    engagement_id?: string;
    created_at: string;
}

export interface NotificationPreference {
    event_type: string;
    label: string;
    site_muted: boolean;
    email_muted: boolean;
}

export function useNotifications(limit = 20) {
    return useQuery<NotificationItem[]>({
        queryKey: ['notifications', limit],
        queryFn: async () => {
            const { data } = await api.get(`/notifications?limit=${limit}`);
            return data;
        },
        refetchInterval: 60000, // poll every 60s as fallback
    });
}

export function useUnreadCount() {
    return useQuery<number>({
        queryKey: ['notifications', 'unread-count'],
        queryFn: async () => {
            const { data } = await api.get('/notifications/unread-count');
            return data.count;
        },
        refetchInterval: false, // driven by WS push, no polling needed
    });
}

export function useMarkRead() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.patch(`/notifications/${id}/read`);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notifications'] });
        },
    });
}

export function useMarkAllRead() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            await api.post('/notifications/mark-all-read');
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notifications'] });
        },
    });
}

export function useClearAllNotifications() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            await api.post('/notifications/clear-all');
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notifications'] });
        },
    });
}

export function useDeleteNotification() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/notifications/${id}`);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notifications'] });
        },
    });
}

export function useNotificationPreferences() {
    return useQuery<NotificationPreference[]>({
        queryKey: ['notification-preferences'],
        queryFn: async () => {
            const { data } = await api.get('/notifications/preferences');
            return data;
        },
    });
}

export function useUpdateNotificationPreferences() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (prefs: Array<{ event_type: string; site_muted: boolean; email_muted: boolean }>) => {
            await api.put('/notifications/preferences', prefs);
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['notification-preferences'] });
        },
    });
}
