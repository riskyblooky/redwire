/**
 * stats/page.tsx — Operations Analytics Dashboard
 *
 * Comprehensive analytics page with five tabs and a configurable
 * time-range selector (7d / 30d / 90d / 6mo / custom date range).
 * Optionally scopes all queries to the currently-selected engagement.
 *
 * **Overview tab** — KPI strip (total findings, active engagements,
 * avg CVSS, team members), findings discovery timeline (area chart),
 * severity distribution (donut), engagement pipeline (horizontal bar).
 *
 * **Findings tab** — Finding status breakdown (donut), severity bar
 * chart, findings by category (horizontal bar), avg CVSS by engagement
 * (dual-axis bar).
 *
 * **Engagements tab** — Avg duration, engagement count, test-case
 * execution rate, cleanup items KPIs. Type pie, client bar, test-case
 * coverage progress bars, cleanup status donut, findings-per-engagement
 * bar.
 *
 * **Clients tab** — Client performance table (engagements, findings,
 * severity split, avg CVSS, avg duration, types), stacked severity bar,
 * engagement volume bar.
 *
 * **Operators tab** — Top contributors bar, operator performance table
 * (avatar, findings, severity split, engagements, test cases, last
 * active), stacked severity per operator bar.
 *
 * Recharts: `BarChart`, `PieChart`, `AreaChart`, `RadialBarChart`.
 * Helpers: `StatCard`, `LoadingPlaceholder`, `EmptyState`.
 * Colour maps: `SEVERITY_COLORS`, `STATUS_COLORS`, `ENG_STATUS_COLORS`,
 * `CLEANUP_COLORS`, `ACCENT_COLORS`.
 */
'use client';

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { parseUTCDate } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    useOverviewStats,
    useFindingsTimeline,
    useSeverityDistribution,
    useUserActivity,
    useEngagementStatus,
    useFindingsByCategory,
    useFindingsByStatus,
    useEngagementTypes,
    useEngagementMetrics,
    useOperatorPerformance,
    useTestCaseStats,
    useCleanupStats,
    useClientStats,
} from '@/lib/hooks/use-stats';
import { useEngagementContext } from '@/stores/engagement-store';
import { useEngagements } from '@/lib/hooks/use-engagements';
import {
    BarChart, Bar, PieChart, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart,
    RadialBarChart, RadialBar, Legend,
} from 'recharts';
import {
    Activity, FileText, Target, Shield, Users, TrendingUp, BarChart3, UserCheck,
    ClipboardCheck, Trash2, Briefcase, Clock, Zap, Building2,
} from 'lucide-react';
import { AuthedImg } from '@/lib/hooks/use-authed-image';

type TimeRange = '7d' | '30d' | '90d' | '180d' | 'custom';

// ─── Shared constants ───
const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#3b82f6', INFO: '#64748b',
};
const STATUS_COLORS: Record<string, string> = {
    OPEN: '#ef4444', IN_REVIEW: '#f59e0b', VERIFIED: '#3b82f6', REMEDIATED: '#10b981', CLOSED: '#64748b',
};
const ENG_STATUS_COLORS: Record<string, string> = {
    SCOPING: '#06b6d4', PLANNING: '#818cf8', IN_PROGRESS: '#3b82f6', REPORTING: '#f59e0b', COMPLETED: '#10b981', ON_HOLD: '#ef4444',
};
const CLEANUP_COLORS: Record<string, string> = {
    PENDING: '#f97316', CLEANED: '#10b981', PARTIALLY_CLEANED: '#f59e0b', NOT_APPLICABLE: '#64748b',
};
const ACCENT_COLORS = ['#818cf8', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#ec4899', '#8b5cf6', '#14b8a6'];

const TOOLTIP_STYLE = {
    contentStyle: { backgroundColor: '#1a2235', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0' },
    itemStyle: { color: '#e2e8f0' },
    labelStyle: { color: '#94a3b8' },
};

/** Cap for growing chart datasets on this page. Recharts silently
 *  degrades once bars overlap or labels collide; keeping a hard cap
 *  means the visual stays readable at 20 clients / 200 clients /
 *  2000 clients. If you need more, drill into the underlying resource
 *  list page, not the summary chart. */
const TOP_N = 20;

/** Sort by a numeric key desc, then take the top N. Bounded rendering
 *  helper used by every unbounded chart on this page. */
function topN<T>(rows: T[] | undefined | null, key: keyof T, n: number = TOP_N): T[] {
    if (!rows || rows.length === 0) return [];
    return [...rows]
        .sort((a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0))
        .slice(0, n);
}

function LoadingPlaceholder({ height = 300 }: { height?: number }) {
    return <div className={`flex items-center justify-center text-slate-500`} style={{ height }}><Activity className="h-5 w-5 animate-spin mr-2" /> Loading...</div>;
}

function EmptyState({ message = 'No data available' }: { message?: string }) {
    return <div className="flex items-center justify-center text-slate-600 py-12">{message}</div>;
}

// ─── Stat card helper ───
function StatCard({ title, value, subtitle, icon: Icon, color, bgColor }: {
    title: string; value: string | number; subtitle?: string;
    icon: any; color: string; bgColor: string;
}) {
    return (
        <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md p-4">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">{title}</p>
                    <p className="text-2xl font-black text-white mt-1">{value}</p>
                    {subtitle && <p className="text-[10px] text-slate-600 mt-0.5">{subtitle}</p>}
                </div>
                <div className={`h-10 w-10 rounded-lg ${bgColor} flex items-center justify-center`}>
                    <Icon className={`h-5 w-5 ${color}`} />
                </div>
            </div>
        </div>
    );
}

/**
 * AnalyticsOverview — the original rich Recharts stats view (Overview /
 * Findings / Engagements / Clients / Operators sub-tabs). Rendered as the
 * pinned first tab of the tabbed /stats page; the outer DashboardLayout and
 * top-level tab bar are provided by stats/page.tsx.
 */
export default function AnalyticsOverview() {
    const { selectedEngagementId } = useEngagementContext();
    const { data: engagements } = useEngagements();
    const [timeRange, setTimeRange] = useState<TimeRange>('30d');
    const [customStartDate, setCustomStartDate] = useState('');
    const [customEndDate, setCustomEndDate] = useState('');
    const [appliedCustomDates, setAppliedCustomDates] = useState<{ start: string; end: string } | null>(null);

    const engagementId = selectedEngagementId && selectedEngagementId !== 'global' ? selectedEngagementId : undefined;
    const selectedEngagement = engagements?.find(e => e.id === engagementId);

    // Memoize query params
    const queryParams = useMemo(() => {
        if (timeRange === 'custom' && appliedCustomDates) {
            return { startDate: appliedCustomDates.start, endDate: appliedCustomDates.end };
        }
        const daysMap = { '7d': 7, '30d': 30, '90d': 90, '180d': 180, custom: 30 };
        return { days: daysMap[timeRange], engagementId };
    }, [timeRange, appliedCustomDates, engagementId]);

    const dateRangeParams = useMemo(() => {
        if (timeRange === 'custom' && appliedCustomDates) {
            return { startDate: appliedCustomDates.start, endDate: appliedCustomDates.end };
        }
        const daysMap = { '7d': 7, '30d': 30, '90d': 90, '180d': 180, custom: 30 };
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - daysMap[timeRange]);
        return { startDate: start.toISOString(), endDate: end.toISOString(), engagementId };
    }, [timeRange, appliedCustomDates, engagementId]);

    // ─── Data hooks ───
    const { data: overview, isLoading: overviewLoading } = useOverviewStats(engagementId);
    const { data: timeline, isLoading: timelineLoading } = useFindingsTimeline(queryParams);
    const { data: severity, isLoading: severityLoading } = useSeverityDistribution(dateRangeParams);
    const { data: activity, isLoading: activityLoading } = useUserActivity(dateRangeParams);
    const { data: engagementStatus, isLoading: engStatusLoading } = useEngagementStatus(dateRangeParams);
    const { data: findingsByCategory, isLoading: catLoading } = useFindingsByCategory(dateRangeParams);
    const { data: findingsByStatus, isLoading: fStatusLoading } = useFindingsByStatus(dateRangeParams);
    const { data: engTypes, isLoading: typesLoading } = useEngagementTypes(dateRangeParams);
    const { data: engMetrics, isLoading: metricsLoading } = useEngagementMetrics(dateRangeParams);
    const { data: operators, isLoading: opsLoading } = useOperatorPerformance(dateRangeParams);
    const { data: tcStats, isLoading: tcLoading } = useTestCaseStats(dateRangeParams);
    const { data: cleanupStats, isLoading: cleanupLoading } = useCleanupStats(dateRangeParams);
    const { data: clientStats, isLoading: clientsLoading } = useClientStats(dateRangeParams);

    const handleCustomDateApply = () => {
        if (customStartDate && customEndDate) {
            setAppliedCustomDates({
                start: new Date(customStartDate).toISOString(),
                end: new Date(customEndDate).toISOString(),
            });
        }
    };

    const timeRangeOptions = [
        { value: '7d' as TimeRange, label: '7 Days' },
        { value: '30d' as TimeRange, label: '30 Days' },
        { value: '90d' as TimeRange, label: '90 Days' },
        { value: '180d' as TimeRange, label: '6 Months' },
        { value: 'custom' as TimeRange, label: 'Custom' },
    ];

    return (
            <div className="space-y-6">
                {/* Scope note + date controls (the page title/tab bar is the
                    shell's responsibility). */}
                <div className="flex items-center justify-between gap-3">
                    <div>
                        {selectedEngagement && (
                            <p className="text-slate-400 text-sm">
                                Scoped to <span className="text-white font-medium">{selectedEngagement.name}</span> · {selectedEngagement.client_name}
                            </p>
                        )}
                    </div>

                    {/* Date Controls */}
                    <div className="flex items-center gap-1.5">
                        {timeRangeOptions.map(opt => (
                            <Button
                                key={opt.value} size="sm" variant={timeRange === opt.value ? 'default' : 'outline'}
                                onClick={() => setTimeRange(opt.value)}
                                className={timeRange === opt.value
                                    ? 'bg-primary hover:bg-primary/90 h-8 text-xs'
                                    : 'border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs'}
                            >
                                {opt.label}
                            </Button>
                        ))}
                    </div>
                </div>

                {/* Custom date picker */}
                {timeRange === 'custom' && (
                    <div className="flex gap-3 items-end">
                        <div className="space-y-1">
                            <Label className="text-slate-400 text-xs">Start</Label>
                            <Input type="date" value={customStartDate} onChange={e => setCustomStartDate(e.target.value)}
                                className="bg-slate-800 border-slate-700 text-white h-8 text-xs w-40" />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-slate-400 text-xs">End</Label>
                            <Input type="date" value={customEndDate} onChange={e => setCustomEndDate(e.target.value)}
                                className="bg-slate-800 border-slate-700 text-white h-8 text-xs w-40" />
                        </div>
                        <Button size="sm" onClick={handleCustomDateApply} disabled={!customStartDate || !customEndDate}
                            className="bg-primary hover:bg-primary/90 h-8">Apply</Button>
                    </div>
                )}

                {/* Tabs */}
                <Tabs defaultValue="overview" className="space-y-6">
                    <TabsList className="bg-slate-900 border border-slate-800 p-1">
                        <TabsTrigger value="overview" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary text-slate-400 hover:text-slate-200">
                            <Activity className="h-4 w-4 mr-1.5" /> Overview
                        </TabsTrigger>
                        <TabsTrigger value="findings" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary text-slate-400 hover:text-slate-200">
                            <FileText className="h-4 w-4 mr-1.5" /> Findings
                        </TabsTrigger>
                        <TabsTrigger value="engagements" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary text-slate-400 hover:text-slate-200">
                            <Briefcase className="h-4 w-4 mr-1.5" /> Engagements
                        </TabsTrigger>
                        <TabsTrigger value="clients" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary text-slate-400 hover:text-slate-200">
                            <Building2 className="h-4 w-4 mr-1.5" /> Clients
                        </TabsTrigger>
                        <TabsTrigger value="operators" className="data-[state=active]:bg-primary/15 data-[state=active]:text-primary text-slate-400 hover:text-slate-200">
                            <Users className="h-4 w-4 mr-1.5" /> Operators
                        </TabsTrigger>
                    </TabsList>

                    {/* ═══════════ OVERVIEW TAB ═══════════ */}
                    <TabsContent value="overview" className="space-y-6">
                        {/* KPI Cards */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard title="Total Findings" value={overviewLoading ? '...' : overview?.total_findings || 0}
                                subtitle={`${overview?.critical_high_findings || 0} critical`}
                                icon={FileText} color="text-blue-400" bgColor="bg-blue-500/10" />
                            <StatCard title="Active Engagements" value={overviewLoading ? '...' : overview?.active_engagements || 0}
                                subtitle={`${overview?.total_engagements || 0} total`}
                                icon={Target} color="text-purple-400" bgColor="bg-purple-500/10" />
                            <StatCard title="Avg CVSS" value={overviewLoading ? '...' : overview?.avg_cvss || 0}
                                subtitle="across all findings"
                                icon={Shield} color="text-red-400" bgColor="bg-red-500/10" />
                            <StatCard title="Team Members" value={overviewLoading ? '...' : overview?.total_users || 0}
                                subtitle={`${overview?.active_users || 0} active (30d)`}
                                icon={Users} color="text-green-400" bgColor="bg-green-500/10" />
                        </div>

                        {/* Findings timeline */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm flex items-center gap-2">
                                    <TrendingUp className="h-4 w-4 text-blue-500" /> Findings Discovery Timeline
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                {timelineLoading ? <LoadingPlaceholder /> : (
                                    <ResponsiveContainer width="100%" height={300}>
                                        <AreaChart data={timeline?.timeline || []}>
                                            <defs>
                                                <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="date" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }}
                                                tickFormatter={v => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} />
                                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <Tooltip {...TOOLTIP_STYLE} labelFormatter={v => new Date(v).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })} />
                                            <Area type="monotone" dataKey="count" stroke="#818cf8" strokeWidth={2} fill="url(#colorCount)" dot={{ fill: '#818cf8', r: 3 }} activeDot={{ r: 5 }} />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>

                        {/* Severity + Engagement Status Row */}
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Severity Distribution</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {severityLoading ? <LoadingPlaceholder /> : (
                                        <ResponsiveContainer width="100%" height={260}>
                                            <PieChart>
                                                <Pie data={severity?.distribution || []} cx="50%" cy="50%" innerRadius={55} outerRadius={95}
                                                    labelLine={false} label={({ severity: sev, percent }: any) => `${sev}: ${(percent * 100).toFixed(0)}%`}
                                                    dataKey="count" paddingAngle={2}>
                                                    {severity?.distribution.map((e, i) => (
                                                        <Cell key={i} fill={SEVERITY_COLORS[e.severity] || '#64748b'} />
                                                    ))}
                                                </Pie>
                                                <Tooltip {...TOOLTIP_STYLE} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Engagement Pipeline</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {engStatusLoading ? <LoadingPlaceholder /> : (
                                        <ResponsiveContainer width="100%" height={260}>
                                            <BarChart data={engagementStatus?.distribution || []} layout="vertical">
                                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                                <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                                <YAxis type="category" dataKey="status" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} width={100} />
                                                <Tooltip {...TOOLTIP_STYLE} />
                                                <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                                                    {engagementStatus?.distribution.map((e, i) => (
                                                        <Cell key={i} fill={ENG_STATUS_COLORS[e.status] || '#818cf8'} />
                                                    ))}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>

                    {/* ═══════════ FINDINGS TAB ═══════════ */}
                    <TabsContent value="findings" className="space-y-6">
                        {/* Status + Severity Row */}
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Finding Status Breakdown</CardTitle>
                                    <CardDescription>Current status of all findings</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {fStatusLoading ? <LoadingPlaceholder /> : (
                                        <ResponsiveContainer width="100%" height={280}>
                                            <PieChart>
                                                <Pie data={findingsByStatus?.statuses || []} cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                                                    labelLine={false} label={({ status, percent }: any) => `${status}: ${(percent * 100).toFixed(0)}%`}
                                                    dataKey="count" paddingAngle={2}>
                                                    {findingsByStatus?.statuses.map((e, i) => (
                                                        <Cell key={i} fill={STATUS_COLORS[e.status] || '#64748b'} />
                                                    ))}
                                                </Pie>
                                                <Tooltip {...TOOLTIP_STYLE} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Severity Distribution</CardTitle>
                                    <CardDescription>Breakdown by severity level</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {severityLoading ? <LoadingPlaceholder /> : (
                                        <ResponsiveContainer width="100%" height={280}>
                                            <BarChart data={severity?.distribution || []}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                                <XAxis dataKey="severity" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                                <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                                <Tooltip {...TOOLTIP_STYLE} />
                                                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                                                    {severity?.distribution.map((e, i) => (
                                                        <Cell key={i} fill={SEVERITY_COLORS[e.severity] || '#64748b'} />
                                                    ))}
                                                </Bar>
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                        </div>

                        {/* Category Chart */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Findings by Category</CardTitle>
                                <CardDescription>Top vulnerability categories</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {catLoading ? <LoadingPlaceholder /> : (findingsByCategory?.categories?.length ?? 0) === 0 ? <EmptyState /> : (() => {
                                    const rows = topN(findingsByCategory?.categories, 'count');
                                    return (
                                    <ResponsiveContainer width="100%" height={Math.min(700, Math.max(200, rows.length * 35))}>
                                        <BarChart data={rows} layout="vertical">
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                            <YAxis type="category" dataKey="category" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} width={160} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="count" fill="#818cf8" radius={[0, 6, 6, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                    );
                                })()}
                            </CardContent>
                        </Card>

                        {/* Avg CVSS per Engagement */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Avg CVSS by Engagement</CardTitle>
                                <CardDescription>Average CVSS score and finding count per engagement</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {metricsLoading ? <LoadingPlaceholder /> : (engMetrics?.per_engagement?.length ?? 0) === 0 ? <EmptyState /> : (
                                    <ResponsiveContainer width="100%" height={300}>
                                        <BarChart data={topN(engMetrics?.per_engagement, 'findings_count')}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="engagement" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={60} />
                                            <YAxis yAxisId="left" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <YAxis yAxisId="right" orientation="right" stroke="#94a3b8" tick={{ fill: '#f59e0b', fontSize: 10 }} domain={[0, 10]} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar yAxisId="left" dataKey="findings_count" fill="#818cf8" radius={[6, 6, 0, 0]} name="Findings" />
                                            <Bar yAxisId="right" dataKey="avg_cvss" fill="#f59e0b" radius={[6, 6, 0, 0]} name="Avg CVSS" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ═══════════ ENGAGEMENTS TAB ═══════════ */}
                    <TabsContent value="engagements" className="space-y-6">
                        {/* KPI Row */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard title="Avg Duration" value={metricsLoading ? '...' : `${engMetrics?.avg_duration_days || 0}d`}
                                subtitle="start to end" icon={Clock} color="text-blue-400" bgColor="bg-blue-500/10" />
                            <StatCard title="Total Engagements" value={overviewLoading ? '...' : overview?.total_engagements || 0}
                                subtitle={`${overview?.active_engagements || 0} active`} icon={Target} color="text-purple-400" bgColor="bg-purple-500/10" />
                            <StatCard title="Test Case Exec Rate" value={tcLoading ? '...' : `${tcStats?.execution_rate || 0}%`}
                                subtitle={`${tcStats?.executed || 0} of ${tcStats?.total || 0} executed`}
                                icon={ClipboardCheck} color="text-cyan-400" bgColor="bg-cyan-500/10" />
                            <StatCard title="Cleanup Items" value={cleanupLoading ? '...' : cleanupStats?.total || 0}
                                icon={Trash2} color="text-amber-400" bgColor="bg-amber-500/10" />
                        </div>

                        {/* Type + Client Row */}
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Engagements by Type</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {typesLoading ? <LoadingPlaceholder height={250} /> : (
                                        <ResponsiveContainer width="100%" height={250}>
                                            <PieChart>
                                                <Pie data={engTypes?.types || []} cx="50%" cy="45%" innerRadius={50} outerRadius={90}
                                                    dataKey="count" nameKey="type" paddingAngle={2}>
                                                    {engTypes?.types.map((_, i) => <Cell key={i} fill={ACCENT_COLORS[i % ACCENT_COLORS.length]} />)}
                                                </Pie>
                                                <Tooltip {...TOOLTIP_STYLE} />
                                                <Legend verticalAlign="bottom" iconType="circle" iconSize={8}
                                                    formatter={(value: string) => <span className="text-slate-300 text-xs">{value}</span>} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Engagements by Client</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {metricsLoading ? <LoadingPlaceholder height={250} /> : (
                                        <ResponsiveContainer width="100%" height={250}>
                                            <BarChart data={topN(engMetrics?.by_client, 'count')} layout="vertical">
                                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                                <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                                <YAxis type="category" dataKey="client" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} width={120} />
                                                <Tooltip {...TOOLTIP_STYLE} />
                                                <Bar dataKey="count" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                        </div>

                        {/* Test Case Coverage + Cleanup */}
                        <div className="grid gap-6 lg:grid-cols-2">
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Test Case Coverage by Category</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {tcLoading ? <LoadingPlaceholder /> : (tcStats?.by_category?.length ?? 0) === 0 ? <EmptyState message="No test cases" /> : (
                                        <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
                                            {tcStats?.by_category.map((cat) => {
                                                const execPct = cat.total ? Math.round((cat.executed / cat.total) * 100) : 0;
                                                const successPct = cat.executed ? Math.round((cat.successful / cat.executed) * 100) : 0;
                                                return (
                                                    <div key={cat.category} className="space-y-1.5">
                                                        <div className="flex items-center justify-between text-xs">
                                                            <span className="text-slate-300 font-medium truncate max-w-[180px]">{cat.category}</span>
                                                            <span className="text-slate-500">{cat.executed}/{cat.total} executed</span>
                                                        </div>
                                                        <div className="h-2 bg-slate-800 rounded-full overflow-hidden flex">
                                                            <div className="bg-green-500 transition-all" style={{ width: `${(cat.successful / Math.max(cat.total, 1)) * 100}%` }} />
                                                            <div className="bg-amber-500 transition-all" style={{ width: `${((cat.executed - cat.successful) / Math.max(cat.total, 1)) * 100}%` }} />
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                            <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-white text-sm">Cleanup Status</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    {cleanupLoading ? <LoadingPlaceholder /> : (cleanupStats?.distribution?.length ?? 0) === 0 ? <EmptyState message="No cleanup artifacts" /> : (
                                        <ResponsiveContainer width="100%" height={250}>
                                            <PieChart>
                                                <Pie data={cleanupStats?.distribution || []} cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                                                    labelLine={false} label={({ status, percent }: any) => `${status}: ${(percent * 100).toFixed(0)}%`}
                                                    dataKey="count" paddingAngle={2}>
                                                    {cleanupStats?.distribution.map((e, i) => (
                                                        <Cell key={i} fill={CLEANUP_COLORS[e.status] || '#64748b'} />
                                                    ))}
                                                </Pie>
                                                <Tooltip {...TOOLTIP_STYLE} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    )}
                                </CardContent>
                            </Card>
                        </div>

                        {/* Findings per Engagement */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Findings per Engagement</CardTitle>
                            </CardHeader>
                            <CardContent>
                                {metricsLoading ? <LoadingPlaceholder /> : (engMetrics?.per_engagement?.length ?? 0) === 0 ? <EmptyState /> : (
                                    <ResponsiveContainer width="100%" height={300}>
                                        <BarChart data={topN(engMetrics?.per_engagement, 'findings_count')}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="engagement" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} interval={0} angle={-20} textAnchor="end" height={60} />
                                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="findings_count" fill="#3b82f6" radius={[6, 6, 0, 0]} name="Findings" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ═══════════ CLIENTS TAB ═══════════ */}
                    <TabsContent value="clients" className="space-y-6">
                        {/* KPI Cards */}
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                            <StatCard title="Total Clients" value={clientsLoading ? '...' : clientStats?.clients?.length || 0}
                                subtitle="with engagements" icon={Building2} color="text-violet-400" bgColor="bg-violet-500/10" />
                            <StatCard title="Avg Findings / Client"
                                value={clientsLoading ? '...' : clientStats?.clients?.length
                                    ? Math.round(clientStats.clients.reduce((s, c) => s + c.total_findings, 0) / clientStats.clients.length)
                                    : 0}
                                icon={FileText} color="text-blue-400" bgColor="bg-blue-500/10" />
                            <StatCard title="Avg CVSS"
                                value={clientsLoading ? '...' : clientStats?.clients?.length
                                    ? (clientStats.clients.reduce((s, c) => s + c.avg_cvss, 0) / clientStats.clients.filter(c => c.avg_cvss > 0).length || 0).toFixed(1)
                                    : 0}
                                icon={Shield} color="text-red-400" bgColor="bg-red-500/10" />
                            <StatCard title="Avg Duration"
                                value={clientsLoading ? '...' : clientStats?.clients?.length
                                    ? `${Math.round(clientStats.clients.reduce((s, c) => s + c.avg_duration_days, 0) / clientStats.clients.filter(c => c.avg_duration_days > 0).length || 0)}d`
                                    : '0d'}
                                icon={Clock} color="text-amber-400" bgColor="bg-amber-500/10" />
                        </div>

                        {/* Client Table */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Client Performance</CardTitle>
                                <CardDescription>Findings, severity breakdown, and CVSS by client</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {clientsLoading ? <LoadingPlaceholder height={200} /> : (clientStats?.clients?.length ?? 0) === 0 ? <EmptyState /> : (() => {
                                    const shown = topN(clientStats?.clients, 'total_findings');
                                    const total = clientStats?.clients?.length ?? 0;
                                    return (
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-xs">
                                            <thead>
                                                <tr className="border-b border-slate-800 text-slate-400">
                                                    <th className="text-left py-2 px-3 font-medium">Client</th>
                                                    <th className="text-center py-2 px-2 font-medium">Engagements</th>
                                                    <th className="text-center py-2 px-2 font-medium">Findings</th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />C
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-orange-500 mr-1" />H
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />M
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />L
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">Avg CVSS</th>
                                                    <th className="text-center py-2 px-2 font-medium">Avg Duration</th>
                                                    <th className="text-left py-2 px-3 font-medium">Types</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {shown.map((c, idx) => {
                                                    // Client name is null in global stats mode for non-admins.
                                                    const label = c.client ?? '—';
                                                    const initial = (c.client?.[0] ?? '·').toUpperCase();
                                                    return (
                                                    <tr key={c.client ?? `anon-${idx}`} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                                                        <td className="py-2.5 px-3">
                                                            <div className="flex items-center gap-2">
                                                                <div className="h-7 w-7 rounded-lg bg-violet-500/10 flex items-center justify-center text-[11px] text-violet-400 font-bold shrink-0">
                                                                    {initial}
                                                                </div>
                                                                <span className="text-white font-medium">{label}</span>
                                                            </div>
                                                        </td>
                                                        <td className="text-center py-2.5 px-2 text-primary font-bold">{c.engagement_count}</td>
                                                        <td className="text-center py-2.5 px-2 text-white font-bold">{c.total_findings}</td>
                                                        <td className="text-center py-2.5 px-2 text-red-400">{c.critical || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-orange-400">{c.high || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-amber-400">{c.medium || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-blue-400">{c.low || '-'}</td>
                                                        <td className="text-center py-2.5 px-2">
                                                            <span className={c.avg_cvss >= 7 ? 'text-red-400 font-bold' : c.avg_cvss >= 4 ? 'text-amber-400' : 'text-green-400'}>
                                                                {c.avg_cvss || '-'}
                                                            </span>
                                                        </td>
                                                        <td className="text-center py-2.5 px-2 text-slate-400">{c.avg_duration_days ? `${c.avg_duration_days}d` : '-'}</td>
                                                        <td className="py-2.5 px-3">
                                                            <div className="flex flex-wrap gap-1">
                                                                {c.engagement_types.map(t => (
                                                                    <span key={t.type} className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                                                                        {t.type}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                        {total > shown.length && (
                                            <p className="text-[10px] text-slate-500 text-center pt-2 border-t border-slate-800/50 mt-1">
                                                Showing top {shown.length} of {total} clients by findings.
                                            </p>
                                        )}
                                    </div>
                                    );
                                })()}
                            </CardContent>
                        </Card>

                        {/* Findings by Client (stacked severity) */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Findings by Severity per Client</CardTitle>
                                <CardDescription>Stacked vulnerability output per client</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {clientsLoading ? <LoadingPlaceholder /> : (clientStats?.clients?.filter(c => c.total_findings > 0).length ?? 0) === 0 ? <EmptyState /> : (
                                    <ResponsiveContainer width="100%" height={300}>
                                        <BarChart data={topN((clientStats?.clients || []).filter(c => c.total_findings > 0), 'total_findings')}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="client" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={60} />
                                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="critical" stackId="sev" fill={SEVERITY_COLORS.CRITICAL} name="Critical" />
                                            <Bar dataKey="high" stackId="sev" fill={SEVERITY_COLORS.HIGH} name="High" />
                                            <Bar dataKey="medium" stackId="sev" fill={SEVERITY_COLORS.MEDIUM} name="Medium" />
                                            <Bar dataKey="low" stackId="sev" fill={SEVERITY_COLORS.LOW} name="Low" />
                                            <Bar dataKey="info" stackId="sev" fill={SEVERITY_COLORS.INFO} name="Info" radius={[6, 6, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>

                        {/* Engagements by Client */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Engagement Volume by Client</CardTitle>
                                <CardDescription>Number of engagements per client</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {clientsLoading ? <LoadingPlaceholder height={250} /> : (clientStats?.clients?.length ?? 0) === 0 ? <EmptyState /> : (
                                    <ResponsiveContainer width="100%" height={250}>
                                        <BarChart data={topN(clientStats?.clients, 'engagement_count')} layout="vertical">
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <YAxis type="category" dataKey="client" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} width={120} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="engagement_count" fill="#8b5cf6" radius={[0, 6, 6, 0]} name="Engagements" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ═══════════ OPERATORS TAB ═══════════ */}
                    <TabsContent value="operators" className="space-y-6">
                        {/* Top Contributors */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Top Contributors</CardTitle>
                                <CardDescription>Most active operators by all logged activity</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {activityLoading ? <LoadingPlaceholder /> : (
                                    <ResponsiveContainer width="100%" height={280}>
                                        <BarChart data={topN(activity?.top_contributors, 'activity_count')}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="username" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="activity_count" fill="#10b981" radius={[6, 6, 0, 0]} name="Activity" />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>

                        {/* Operator Table */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Operator Performance</CardTitle>
                                <CardDescription>Comprehensive per-operator breakdown</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {opsLoading ? <LoadingPlaceholder height={200} /> : (operators?.operators?.length ?? 0) === 0 ? <EmptyState /> : (() => {
                                    const shownOps = topN(operators?.operators, 'total_findings');
                                    const totalOps = operators?.operators?.length ?? 0;
                                    return (
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-xs">
                                            <thead>
                                                <tr className="border-b border-slate-800 text-slate-400">
                                                    <th className="text-left py-2 px-3 font-medium">Operator</th>
                                                    <th className="text-center py-2 px-2 font-medium">Findings</th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />C
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-orange-500 mr-1" />H
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />M
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">
                                                        <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-1" />L
                                                    </th>
                                                    <th className="text-center py-2 px-2 font-medium">Engagements</th>
                                                    <th className="text-center py-2 px-2 font-medium">Test Cases</th>
                                                    <th className="text-left py-2 px-3 font-medium">Last Active</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {shownOps.map((op, idx) => {
                                                    // username / full_name are null in global stats mode for non-admins.
                                                    const label = op.full_name || op.username || '—';
                                                    const initial = (op.full_name?.[0] || op.username?.[0] || '·').toUpperCase();
                                                    return (
                                                    <tr key={op.user_id ?? `anon-${idx}`} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                                                        <td className="py-2.5 px-3">
                                                            <div className="flex items-center gap-2">
                                                                {op.profile_photo ? (
                                                                    <AuthedImg src={op.profile_photo} className="h-6 w-6 rounded-full object-cover" alt="" />
                                                                ) : (
                                                                    <div className="h-6 w-6 rounded-full bg-slate-700 flex items-center justify-center text-[10px] text-slate-400 font-bold">
                                                                        {initial}
                                                                    </div>
                                                                )}
                                                                <div>
                                                                    <span className="text-white font-medium">{label}</span>
                                                                    <span className="text-slate-600 ml-1.5 text-[10px]">{op.role}</span>
                                                                </div>
                                                            </div>
                                                        </td>
                                                        <td className="text-center py-2.5 px-2 text-white font-bold">{op.total_findings}</td>
                                                        <td className="text-center py-2.5 px-2 text-red-400">{op.critical || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-orange-400">{op.high || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-amber-400">{op.medium || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-blue-400">{op.low || '-'}</td>
                                                        <td className="text-center py-2.5 px-2 text-primary">{op.engagement_count}</td>
                                                        <td className="text-center py-2.5 px-2">
                                                            <span className="text-cyan-400">{op.testcases_executed}</span>
                                                            <span className="text-slate-600">/{op.testcases_total}</span>
                                                        </td>
                                                        <td className="py-2.5 px-3 text-slate-500">
                                                            {op.last_active ? parseUTCDate(op.last_active).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                                                        </td>
                                                    </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                        {totalOps > shownOps.length && (
                                            <p className="text-[10px] text-slate-500 text-center pt-2 border-t border-slate-800/50 mt-1">
                                                Showing top {shownOps.length} of {totalOps} operators by findings.
                                            </p>
                                        )}
                                    </div>
                                    );
                                })()}
                            </CardContent>
                        </Card>

                        {/* Severity Breakdown per Operator Chart */}
                        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-xs">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-white text-sm">Findings by Severity per Operator</CardTitle>
                                <CardDescription>Stacked view of operator vulnerability output</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {opsLoading ? <LoadingPlaceholder /> : (
                                    <ResponsiveContainer width="100%" height={300}>
                                        <BarChart data={topN((operators?.operators || []).filter(o => o.total_findings > 0), 'total_findings')}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                            <XAxis dataKey="username" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
                                            <Tooltip {...TOOLTIP_STYLE} />
                                            <Bar dataKey="critical" stackId="sev" fill={SEVERITY_COLORS.CRITICAL} name="Critical" />
                                            <Bar dataKey="high" stackId="sev" fill={SEVERITY_COLORS.HIGH} name="High" />
                                            <Bar dataKey="medium" stackId="sev" fill={SEVERITY_COLORS.MEDIUM} name="Medium" />
                                            <Bar dataKey="low" stackId="sev" fill={SEVERITY_COLORS.LOW} name="Low" />
                                            <Bar dataKey="info" stackId="sev" fill={SEVERITY_COLORS.INFO} name="Info" radius={[6, 6, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                )}
                            </CardContent>
                        </Card>
                    </TabsContent>
                </Tabs>
            </div>
    );
}
