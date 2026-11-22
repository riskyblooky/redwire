import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../api';
import { format } from 'date-fns';

/**
 * Calendar times are stored as wall-clock values without a zone (the event
 * form's datetime-local input), so range queries must be in the same terms.
 * Sending UTC (toISOString) — the backend drops the zone — shifted every
 * range by the viewer's UTC offset: west of UTC an early-morning event fell
 * out of its own day view.
 */
const wallClock = (d: Date) => format(d, "yyyy-MM-dd'T'HH:mm:ss");

export interface CalendarEvent {
    id: string;
    title: string;
    description: string | null;
    start_time: string;
    end_time: string;
    location: string | null;
    is_all_day: boolean;
    event_type: string;
    created_by: string;
    created_at: string;
    updated_at: string;
}

export interface FeedItem {
    id: string;
    engagement_id?: string;
    title: string;
    description: string | null;
    start: string;
    end: string;
    type: 'event' | 'engagement' | 'ooo';
    color: string;
    status?: string;
    phase?: 'SCOPING' | 'PLANNING' | 'IN_PROGRESS' | 'REPORTING' | null;
    phase_sort_order?: number;
    engagement_start?: string;
    engagement_end?: string | null;
    event_type?: string;
    created_by?: string;
    creator?: {
        id: string;
        username: string;
        full_name: string | null;
        profile_photo: string | null;
    };
    assigned_users?: Array<{
        id: string;
        username: string;
        full_name: string | null;
        role: string;
    }>;
}

export interface CalendarEventCreate {
    title: string;
    description?: string;
    start_time: string;
    end_time: string;
    location?: string;
    is_all_day?: boolean;
    event_type?: string;
}

export interface TeamMemberAvailability {
    user: {
        id: string;
        username: string;
        full_name: string | null;
        role: string;
        profile_photo: string | null;
    };
    engagements: Array<{
        id: string;
        name: string;
        client_name: string;
        start_date: string | null;
        end_date: string | null;
        status: string;
        engagement_type?: string;
    }>;
    engagement_count: number;
    ooo_events: Array<{
        id: string;
        title: string;
        start_time: string;
        end_time: string;
    }>;
    user_skills: Array<{
        skill_id: string;
        skill_name: string;
        category_id: string;
        category_name: string;
        level: number;
    }>;
}

export interface AutoAssignSuggestion {
    user: {
        id: string;
        username: string;
        full_name: string | null;
        role: string;
        profile_photo: string | null;
    };
    overlapping_count: number;
    engagements: Array<{
        id: string;
        name: string;
        client_name: string;
        start_date: string | null;
        end_date: string | null;
        status: string;
    }>;
    ooo_events: Array<{
        id: string;
        title: string;
        start_time: string;
        end_time: string;
    }>;
}

export function useCalendarFeed(start: Date, end: Date, userIds?: string[]) {
    return useQuery({
        queryKey: ['calendar', 'feed', start.toISOString(), end.toISOString(), userIds],
        queryFn: async () => {
            const params: Record<string, string> = {
                start: wallClock(start),
                end: wallClock(end),
            };
            if (userIds && userIds.length > 0) {
                params.user_ids = userIds.join(',');
            }
            const { data } = await api.get<FeedItem[]>('/calendar/feed', { params });
            return data;
        },
        enabled: !!start && !!end,
    });
}

export function useTeamAvailability(start: Date, end: Date, enabled = true) {
    return useQuery({
        queryKey: ['calendar', 'team-availability', start.toISOString(), end.toISOString()],
        queryFn: async () => {
            const { data } = await api.get<TeamMemberAvailability[]>('/calendar/team-availability', {
                params: {
                    start: wallClock(start),
                    end: wallClock(end),
                },
            });
            return data;
        },
        enabled: enabled && !!start && !!end,
    });
}

export function useCreateCalendarEvent() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (event: CalendarEventCreate) => {
            const { data } = await api.post<CalendarEvent>('/calendar/events', event);
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['calendar'] });
        },
    });
}

export function useDeleteCalendarEvent() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/calendar/events/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['calendar'] });
        },
    });
}
