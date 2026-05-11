import { useQuery } from '@tanstack/react-query';
import api from '../api';

interface OverviewStats {
    total_findings: number;
    total_engagements: number;
    active_engagements: number;
    total_evidence: number;
    critical_high_findings: number;
    active_users: number;
    total_users: number;
    avg_cvss: number;
}

interface TimelineData {
    date: string;
    count: number;
}

interface SeverityDistribution {
    severity: string;
    count: number;
}

interface UserActivity {
    username: string;
    full_name: string | null;
    profile_photo: string | null;
    role: string;
    activity_count: number;
}

interface EngagementStatusDistribution {
    status: string;
    count: number;
}

interface FindingsByCategory {
    category: string;
    count: number;
}

interface FindingsByStatus {
    status: string;
    count: number;
}

interface EngagementType {
    type: string;
    count: number;
}

interface EngagementPerformance {
    engagement: string;
    client: string;
    findings_count: number;
    avg_cvss: number;
}

interface EngagementMetrics {
    avg_duration_days: number;
    per_engagement: EngagementPerformance[];
    by_client: { client: string; count: number }[];
}

interface OperatorPerformance {
    user_id: string;
    username: string;
    full_name: string | null;
    profile_photo: string | null;
    role: string;
    last_active: string | null;
    total_findings: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
    engagement_count: number;
    testcases_total: number;
    testcases_executed: number;
    testcases_successful: number;
}

interface TestCaseStats {
    total: number;
    executed: number;
    successful: number;
    execution_rate: number;
    success_rate: number;
    by_category: { category: string; total: number; executed: number; successful: number }[];
}

interface CleanupStats {
    total: number;
    distribution: { status: string; count: number }[];
}

// Shared param builder
function buildParams(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    const p = new URLSearchParams();
    if (params?.startDate) p.append('start_date', params.startDate);
    if (params?.endDate) p.append('end_date', params.endDate);
    if (params?.engagementId && params.engagementId !== 'global') p.append('engagement_id', params.engagementId);
    return p.toString();
}

// ─── Existing hooks (enhanced) ───

export function useOverviewStats(engagementId?: string) {
    return useQuery<OverviewStats>({
        queryKey: ['stats', 'overview', engagementId],
        queryFn: async () => {
            const params = new URLSearchParams();
            if (engagementId && engagementId !== 'global') params.append('engagement_id', engagementId);
            return (await api.get(`/stats/overview?${params.toString()}`)).data;
        },
    });
}

interface FindingsTimelineParams {
    days?: number;
    startDate?: string;
    endDate?: string;
    engagementId?: string;
}

export function useFindingsTimeline(params: number | FindingsTimelineParams = 30) {
    const queryParams = typeof params === 'number' ? { days: params } : params;
    return useQuery<{ timeline: TimelineData[]; start_date: string; end_date: string }>({
        queryKey: ['stats', 'findings-timeline', queryParams],
        queryFn: async () => {
            const urlParams = new URLSearchParams();
            if (queryParams.days) urlParams.append('days', queryParams.days.toString());
            if (queryParams.startDate) urlParams.append('start_date', queryParams.startDate);
            if (queryParams.endDate) urlParams.append('end_date', queryParams.endDate);
            if (queryParams.engagementId && queryParams.engagementId !== 'global')
                urlParams.append('engagement_id', queryParams.engagementId);
            return (await api.get(`/stats/findings-timeline?${urlParams.toString()}`)).data;
        },
    });
}

export function useSeverityDistribution(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<{ distribution: SeverityDistribution[] }>({
        queryKey: ['stats', 'severity-distribution', params],
        queryFn: async () => (await api.get(`/stats/severity-distribution?${buildParams(params)}`)).data,
    });
}

export function useUserActivity(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<{ top_contributors: UserActivity[] }>({
        queryKey: ['stats', 'user-activity', params],
        queryFn: async () => (await api.get(`/stats/user-activity?${buildParams(params)}`)).data,
    });
}

export function useEngagementStatus(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<{ distribution: EngagementStatusDistribution[] }>({
        queryKey: ['stats', 'engagement-status', params],
        queryFn: async () => (await api.get(`/stats/engagement-status?${buildParams(params)}`)).data,
    });
}

// ─── New hooks ───

export function useFindingsByCategory(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<{ categories: FindingsByCategory[] }>({
        queryKey: ['stats', 'findings-by-category', params],
        queryFn: async () => (await api.get(`/stats/findings-by-category?${buildParams(params)}`)).data,
    });
}

export function useFindingsByStatus(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<{ statuses: FindingsByStatus[] }>({
        queryKey: ['stats', 'findings-by-status', params],
        queryFn: async () => (await api.get(`/stats/findings-by-status?${buildParams(params)}`)).data,
    });
}

export function useEngagementTypes(params?: { startDate?: string; endDate?: string }) {
    return useQuery<{ types: EngagementType[] }>({
        queryKey: ['stats', 'engagement-types', params],
        queryFn: async () => (await api.get(`/stats/engagement-types?${buildParams(params)}`)).data,
    });
}

export function useEngagementMetrics(params?: { startDate?: string; endDate?: string }) {
    return useQuery<EngagementMetrics>({
        queryKey: ['stats', 'engagement-metrics', params],
        queryFn: async () => (await api.get(`/stats/engagement-metrics?${buildParams(params)}`)).data,
    });
}

export function useOperatorPerformance(params?: { startDate?: string; endDate?: string }) {
    return useQuery<{ operators: OperatorPerformance[] }>({
        queryKey: ['stats', 'operator-performance', params],
        queryFn: async () => (await api.get(`/stats/operator-performance?${buildParams(params)}`)).data,
    });
}

export function useTestCaseStats(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<TestCaseStats>({
        queryKey: ['stats', 'testcase-stats', params],
        queryFn: async () => (await api.get(`/stats/testcase-stats?${buildParams(params)}`)).data,
    });
}

export function useCleanupStats(params?: { startDate?: string; endDate?: string; engagementId?: string }) {
    return useQuery<CleanupStats>({
        queryKey: ['stats', 'cleanup-stats', params],
        queryFn: async () => (await api.get(`/stats/cleanup-stats?${buildParams(params)}`)).data,
    });
}

interface ClientStat {
    client: string;
    engagement_count: number;
    avg_duration_days: number;
    total_findings: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
    avg_cvss: number;
    engagement_types: { type: string; count: number }[];
}

export function useClientStats(params?: { startDate?: string; endDate?: string }) {
    return useQuery<{ clients: ClientStat[] }>({
        queryKey: ['stats', 'client-stats', params],
        queryFn: async () => (await api.get(`/stats/client-stats?${buildParams(params)}`)).data,
    });
}
