import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import api from '../api';

// ── Types ───────────────────────────────────────────────────────────────────

export type EventOutcome = 'success' | 'failure' | 'info';

export interface SecurityEvent {
    id: string;
    created_at: string;
    event_type: string;
    outcome: EventOutcome;
    user_id: string | null;
    username: string | null;
    actor_id: string | null;
    actor_username: string | null;
    ip: string | null;
    user_agent: string | null;
    reason: string | null;
    details: Record<string, any> | null;
}

export interface Paged<T> {
    items: T[];
    total: number;
}

export interface HourlySignins { bucket: string; success: number; failure: number }

export interface SigninSummary {
    hours: number;
    logins_ok: number;
    logins_failed: number;
    mfa_failed: number;
    rate_limited: number;
    failing_ips: number;
    counts: Record<string, number>;
    top_ips: { ip: string; failures: number; usernames: number; last: string }[];
    top_usernames: { username: string; failures: number; ips: number; last: string }[];
    hourly: HourlySignins[];
}

export interface HourlyTraffic { bucket: string; requests: number; s4xx: number; s5xx: number; flagged: number }
export interface CountRow { value: string; count: number }

export interface TrafficSummary {
    hours: number;
    requests: number;
    unique_ips: number;
    s4xx: number;
    s5xx: number;
    s429: number;
    probes: number;
    scanner: number;
    top_ips: { ip: string; requests: number; errors: number; flagged: number; last: string }[];
    top_404: CountRow[];
    top_probes: CountRow[];
    top_user_agents: CountRow[];
    flagged_user_agents: CountRow[];
    top_5xx: CountRow[];
    hourly: HourlyTraffic[];
    ingest: { configured: boolean; path: string; last_ingest: string | null; pending_bytes: number | null };
}

export interface HttpRequestRow {
    id: string;
    ts: string;
    ip: string | null;
    method: string | null;
    path: string | null;
    status: number;
    bytes: number | null;
    duration_ms: number | null;
    host: string | null;
    user_agent: string | null;
    referer: string | null;
    area: 'web' | 'api' | 'ws' | null;
    flags: string[];
}

export interface TrafficDay { day: string; requests: number; s4xx: number; s5xx: number; s429: number; probes: number; scanner: number }

export interface SecurityAccount {
    id: string;
    username: string;
    full_name: string | null;
    email: string | null;
    role: string | null;
    is_active: boolean;
    auth_provider: string;
    mfa: boolean;
    last_login: string | null;
    last_active: string | null;
    created_at: string | null;
    last_ip: string | null;
    failed_24h: number;
    active_tokens: number;
    privileged: boolean;
    dormant: boolean;
    must_change_password: boolean;
}

export interface SecurityToken {
    id: string;
    name: string;
    token_prefix: string;
    permission: 'ro' | 'rw';
    user_id: string;
    username: string;
    created_at: string;
    last_used_at: string | null;
    expires_at: string | null;
    is_active: boolean;
    flags: string[];
}

export interface AccountsResponse {
    users: SecurityAccount[];
    tokens: SecurityToken[];
    dormant_days: number;
    stale_token_days: number;
}

export type CheckStatus = 'pass' | 'warn' | 'fail' | 'info';

export interface PostureCheck {
    id: string;
    title: string;
    status: CheckStatus;
    detail: string;
    fix: string;
    category: string;
}

export interface PostureResponse {
    checks: PostureCheck[];
    tally: Record<CheckStatus, number>;
    generated_at: string;
}

export interface AttentionItem {
    severity: 'high' | 'medium';
    title: string;
    detail: string;
    tab: string;
    ip?: string;
}

export interface SecurityOverview {
    version: string;
    signins: Pick<SigninSummary, 'logins_ok' | 'logins_failed' | 'mfa_failed' | 'rate_limited' | 'failing_ips' | 'hourly'>;
    traffic: Pick<TrafficSummary, 'requests' | 'unique_ips' | 's4xx' | 's5xx' | 's429' | 'probes' | 'scanner' | 'hourly'>;
    posture: Record<CheckStatus, number>;
    tls: PostureCheck | null;
    attention: AttentionItem[];
}

export interface SensitiveActivity {
    id: string;
    created_at: string;
    action: string;
    user_id: string;
    username: string | null;
    resource_type: string;
    resource_id: string;
    resource_name: string | null;
    engagement_id: string | null;
    details: string | null;
}

export interface Retention { http_days: number; events_days: number; rollup_days: number }

export interface EventFilters {
    event_type?: string;
    outcome?: EventOutcome;
    q?: string;
    ip?: string;
    user_id?: string;
    audit?: boolean;
    hours?: number;
    limit?: number;
    offset?: number;
}

export interface RequestFilters {
    ip?: string;
    path?: string;
    status?: string;
    flag?: 'any' | 'probe' | 'scanner_ua' | 'tool_ua';
    area?: 'web' | 'api' | 'ws';
    hours?: number;
    limit?: number;
    offset?: number;
}

// ── Queries ─────────────────────────────────────────────────────────────────

const BASE = '/admin/security';
const LIVE = 30_000; // the panel is a monitor — keep it fresh while open

/** Drop empty filter values so they don't go out as `?ip=`. */
function clean<T extends object>(params: T): Partial<T> {
    return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null)) as Partial<T>;
}

export function useSecurityOverview() {
    return useQuery({
        queryKey: ['security-center', 'overview'],
        queryFn: async () => (await api.get<SecurityOverview>(`${BASE}/overview`)).data,
        staleTime: 30_000,
        refetchInterval: LIVE,
    });
}

export function useSecurityEvents(filters: EventFilters) {
    return useQuery({
        queryKey: ['security-center', 'events', filters],
        queryFn: async () => (await api.get<Paged<SecurityEvent>>(`${BASE}/events`, { params: clean(filters) })).data,
        staleTime: 30_000,
        refetchInterval: LIVE,
        placeholderData: keepPreviousData,
    });
}

export function useSigninSummary(hours: number) {
    return useQuery({
        queryKey: ['security-center', 'events-summary', hours],
        queryFn: async () => (await api.get<SigninSummary>(`${BASE}/events/summary`, { params: { hours } })).data,
        staleTime: 30_000,
        refetchInterval: LIVE,
    });
}

export function useTrafficSummary(hours: number) {
    return useQuery({
        queryKey: ['security-center', 'traffic-summary', hours],
        queryFn: async () => (await api.get<TrafficSummary>(`${BASE}/traffic/summary`, { params: { hours } })).data,
        staleTime: 30_000,
        refetchInterval: LIVE,
    });
}

export function useTrafficRequests(filters: RequestFilters) {
    return useQuery({
        queryKey: ['security-center', 'traffic-requests', filters],
        queryFn: async () => (await api.get<Paged<HttpRequestRow>>(`${BASE}/traffic/requests`, { params: clean(filters) })).data,
        staleTime: 30_000,
        refetchInterval: LIVE,
        placeholderData: keepPreviousData,
    });
}

export function useTrafficHistory(days: number) {
    return useQuery({
        queryKey: ['security-center', 'traffic-history', days],
        queryFn: async () => (await api.get<TrafficDay[]>(`${BASE}/traffic/history`, { params: { days } })).data,
        staleTime: 5 * 60_000,
    });
}

export function useSecurityAccounts() {
    return useQuery({
        queryKey: ['security-center', 'accounts'],
        queryFn: async () => (await api.get<AccountsResponse>(`${BASE}/accounts`)).data,
        staleTime: 30_000,
    });
}

export function useSecurityPosture() {
    return useQuery({
        queryKey: ['security-center', 'posture'],
        queryFn: async () => (await api.get<PostureResponse>(`${BASE}/posture`)).data,
        staleTime: 60_000,
    });
}

export function useSensitiveActivity(params: { hours?: number; limit?: number; offset?: number }) {
    return useQuery({
        queryKey: ['security-center', 'activity', params],
        queryFn: async () => (await api.get<Paged<SensitiveActivity>>(`${BASE}/audit/activity`, { params: clean(params) })).data,
        staleTime: 30_000,
        placeholderData: keepPreviousData,
    });
}

export function useSecuritySettings() {
    return useQuery({
        queryKey: ['security-center', 'settings'],
        queryFn: async () => (await api.get<{ retention: Retention }>(`${BASE}/settings`)).data,
        staleTime: 60_000,
    });
}

// ── Mutations ───────────────────────────────────────────────────────────────

export function useRefreshPosture() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => (await api.get<PostureResponse>(`${BASE}/posture`, { params: { refresh: true } })).data,
        onSuccess: (data) => {
            qc.setQueryData(['security-center', 'posture'], data);
            qc.invalidateQueries({ queryKey: ['security-center', 'overview'] });
        },
    });
}

function useSecurityAction<V>(fn: (v: V) => Promise<unknown>) {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: fn,
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['security-center'] });
            qc.invalidateQueries({ queryKey: ['admin'] });
        },
    });
}

export function useRevokeSessions() {
    return useSecurityAction((userId: string) => api.post(`${BASE}/users/${userId}/revoke-sessions`));
}

export function useDisableUser() {
    return useSecurityAction((userId: string) => api.post(`${BASE}/users/${userId}/disable`));
}

export function useRevokeApiToken() {
    return useSecurityAction((tokenId: string) => api.post(`${BASE}/api-tokens/${tokenId}/revoke`));
}

export function useUpdateSecuritySettings() {
    return useSecurityAction((retention: Partial<Retention>) => api.put(`${BASE}/settings`, retention));
}
