import { useQuery } from '@tanstack/react-query';
import api from '../api';

export interface DashboardStats {
    active_engagements: {
        total: number;
        in_progress: number;
        planning: number;
        reporting: number;
    };
    findings: {
        total: number;
        critical: number;
        resolved_this_month: number;
        severity_breakdown: Array<{
            severity: string;
            count: number;
            color: string;
        }>;
        status_breakdown: Array<{
            status: string;
            label: string;
            count: number;
        }>;
    };
    top_findings: Array<{
        id: string;
        title: string;
        severity: string;
        status: string;
        engagement_id: string;
        engagement_name: string;
        created_at: string;
    }>;
    pending_cleanup: number;
    my_engagements: Array<{
        id: string;
        name: string;
        client_name: string;
        status: string;
        engagement_type: string;
        start_date: string | null;
        end_date: string | null;
        finding_count: number;
        testcase_count: number;
    }>;
    upcoming_engagements: Array<{
        id: string;
        name: string;
        client_name: string;
        status: string;
        start_date: string | null;
        end_date: string | null;
    }>;
    team_utilization: {
        total_operators: number;
        assigned_operators: number;
        utilization_pct: number;
    };
    recent_activity: Array<{
        id: string;
        type: string;
        title: string;
        user: string;
        time: string;
        severity: string | null;
        action: string;
        resource_id: string;
        engagement_id: string;
        resource_name: string | null;
    }>;
    personal_stats: {
        my_active_engagements: number;
        my_open_findings: number;
        my_pending_tests: number;
        my_findings_this_month: number;
        my_pending_cleanup: number;
        my_unread_notifications: number;
    };
}

export function useDashboardStats(engagementId?: string | null) {
    return useQuery({
        queryKey: ['analytics', 'dashboard', engagementId || 'global'],
        queryFn: async () => {
            const params = engagementId && engagementId !== 'global'
                ? `?engagement_id=${engagementId}`
                : '';
            const { data } = await api.get<DashboardStats>(`/analytics/dashboard-stats${params}`);
            return data;
        },
        refetchInterval: 300000, // 5-min fallback; real-time updates via WS
    });
}
