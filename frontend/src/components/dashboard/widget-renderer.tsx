'use client';

/**
 * WidgetRenderer — universal widget renderer.
 * Renders stat cards, charts, gauges, and list widgets with premium styling.
 * Chart data hooks use stable memoized params to avoid infinite re-fetch.
 */

import { useMemo, createContext, useContext } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { DashboardWidgetDef } from '@/lib/hooks/use-dashboard-widgets';
import {
    Briefcase, Bug, AlertTriangle, CheckSquare, Target, Trash2,
    Activity, BarChart3, CircleDot, Users, Calendar, TrendingUp,
    UserCheck, ClipboardCheck, Server, Clock, ArrowUpRight,
    Shield, Flame, History, MessageSquare, FileText as FileIcon, Eye, Zap,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import {
    ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend,
    XAxis, YAxis, CartesianGrid, Tooltip, Area, AreaChart, Line, LineChart,
    ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { formatDistanceToNow, format } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import {
    useOverviewStats, useSeverityDistribution, useEngagementStatus,
    useFindingsByStatus, useFindingsTimeline, useEngagementTypes,
    useCleanupStats, useUserActivity, useTestCaseStats,
    useFindingsByCategory,
} from '@/lib/hooks/use-stats';
import { useDashboardStats } from '@/lib/hooks/use-analytics';
import { useCustomWidgetData } from '@/lib/hooks/use-dashboard-widgets';

// Selects the backend scoping model for custom_query widget data. The
// dashboard leaves the default ('dashboard' → assignment-scoped); a shared
// stats page provides 'stats' so the widget honors the platform Stats Scope
// Mode. Only custom_query widgets read this — built-in /stats/* data sources
// already scope server-side.
export const WidgetDataContext = createContext<'dashboard' | 'stats'>('dashboard');

// ── Icons ──────────────────────────────────────────────────────────
const ICON_MAP: Record<string, any> = {
    Briefcase, Bug, AlertTriangle, CheckSquare, Target, Trash2,
    Activity, BarChart3, CircleDot, Users, Calendar, TrendingUp,
    UserCheck, ClipboardCheck, Server, Clock, Shield, Flame, Eye, Zap,
    History, MessageSquare, FileIcon, ArrowUpRight,
};

// ── Theme constants ────────────────────────────────────────────────
// Themed via CSS variables so tooltips follow the user's selected accent
// theme (--popover / --border / --foreground change per theme_preference).
// wrapperStyle z-index + allowEscapeViewBox let the tooltip render above and
// outside the widget card instead of being clipped by it.
const TOOLTIP_STYLE = {
    contentStyle: {
        backgroundColor: 'hsl(var(--popover))',
        border: '1px solid hsl(var(--border))',
        borderRadius: '8px',
        color: 'hsl(var(--popover-foreground))',
        boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
    },
    itemStyle: { color: 'hsl(var(--popover-foreground))' },
    labelStyle: { color: 'hsl(var(--muted-foreground))' },
    wrapperStyle: { zIndex: 50, outline: 'none' },
    allowEscapeViewBox: { x: true, y: true } as { x: boolean; y: boolean },
};

const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#3b82f6', INFO: '#64748b',
    Critical: '#ef4444', High: '#f97316', Medium: '#f59e0b', Low: '#3b82f6', Info: '#64748b',
};
const STATUS_COLORS: Record<string, string> = {
    OPEN: '#ef4444', IN_REVIEW: '#f59e0b', VERIFIED: '#3b82f6', REMEDIATED: '#10b981', CLOSED: '#64748b',
};
const ENG_STATUS_COLORS: Record<string, string> = {
    PLANNING: '#818cf8', IN_PROGRESS: '#3b82f6', REPORTING: '#f59e0b',
    COMPLETED: '#10b981', ON_HOLD: '#ef4444', PROPOSED: '#a855f7', SCOPING: '#06b6d4',
};
const ENG_STATUS_BADGE: Record<string, string> = {
    PLANNING: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
    IN_PROGRESS: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
    REPORTING: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    COMPLETED: 'bg-green-500/10 text-green-400 border-green-500/30',
    ON_HOLD: 'bg-red-500/10 text-red-400 border-red-500/30',
    PROPOSED: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
    SCOPING: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
};
const CLEANUP_COLORS: Record<string, string> = {
    PENDING: '#f97316', CLEANED: '#10b981', PARTIALLY_CLEANED: '#f59e0b', NOT_APPLICABLE: '#64748b',
};
const ACCENT_COLORS = ['#818cf8', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#ec4899', '#8b5cf6', '#14b8a6'];

// ── Number formatting ─────────────────────────────────────────────
function formatValue(v: any): string {
    if (typeof v !== 'number') return String(v ?? '');
    if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
    return v % 1 === 0 ? v.toString() : v.toFixed(1);
}

// ── Types ──────────────────────────────────────────────────────────
interface WidgetRendererProps {
    widget: DashboardWidgetDef;
    isEditing?: boolean;
    engagementId?: string | null;
    onRemove?: () => void;
}

// ══════════════════════════════════════════════════════════════════
//  MAIN ENTRY
// ══════════════════════════════════════════════════════════════════

export default function WidgetRenderer({ widget, isEditing, engagementId, onRemove }: WidgetRendererProps) {
    const { data: dashStats } = useDashboardStats(engagementId);

    switch (widget.widget_type) {
        case 'stat_card':
            return <StatCardWidget widget={widget} stats={dashStats} isEditing={isEditing} onRemove={onRemove} />;
        case 'bar_chart':
        case 'stacked_bar':
            return <BarChartWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'pie_chart':
            return <PieChartWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'area_chart':
            return <AreaChartWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'gauge':
            return <GaugeWidget widget={widget} stats={dashStats} isEditing={isEditing} onRemove={onRemove} />;
        case 'list':
            return <ListWidget widget={widget} stats={dashStats} isEditing={isEditing} onRemove={onRemove} />;
        case 'heatmap':
            return <HeatmapWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'scatter':
            return <ScatterWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'ratio':
        case 'percentage':
            return <RatioWidget widget={widget} isEditing={isEditing} onRemove={onRemove} mode={widget.widget_type as 'ratio' | 'percentage'} />;
        case 'delta':
            return <DeltaWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        case 'overlay':
            return <OverlayWidget widget={widget} isEditing={isEditing} onRemove={onRemove} />;
        default:
            return (
                <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                    <p className="text-slate-500 text-xs italic text-center py-4">Unsupported widget type: {widget.widget_type}</p>
                </WidgetShell>
            );
    }
}

// ══════════════════════════════════════════════════════════════════
//  WIDGET SHELL (shared card wrapper — flex column so content fills)
// ══════════════════════════════════════════════════════════════════

function WidgetShell({ widget, children, isEditing, onRemove }: {
    widget: DashboardWidgetDef; children: React.ReactNode;
    isEditing?: boolean; onRemove?: () => void;
}) {
    const Icon = ICON_MAP[widget.icon || ''] || BarChart3;
    return (
        <Card className="border-slate-800/60 bg-slate-900/50 backdrop-blur-md h-full relative group/widget flex flex-col">
            {isEditing && onRemove && (
                <button
                    onClick={onRemove}
                    className="absolute -top-2 -right-2 z-10 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center text-xs font-bold opacity-0 group-hover/widget:opacity-100 transition-opacity hover:bg-red-400"
                >
                    ×
                </button>
            )}
            <CardHeader className="pb-1 pt-4 px-5 shrink-0">
                <CardTitle className="text-sm font-bold text-white flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-slate-800/80 flex items-center justify-center shrink-0">
                        <Icon className="h-3.5 w-3.5 text-slate-400" />
                    </div>
                    <span className="truncate">{widget.name}</span>
                </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 flex-1 min-h-0 flex flex-col">
                {children}
            </CardContent>
        </Card>
    );
}

// ══════════════════════════════════════════════════════════════════
//  STAT CARD
// ══════════════════════════════════════════════════════════════════

function StatCardWidget({ widget, stats, isEditing, onRemove }: {
    widget: DashboardWidgetDef; stats: any; isEditing?: boolean; onRemove?: () => void;
}) {
    const Icon = ICON_MAP[widget.icon || ''] || BarChart3;
    const variant = widget.config?.variant || 'default';

    const parts = widget.data_source.split('.');
    let value: any = stats;
    for (const p of parts) value = value?.[p];
    value = value ?? 0;

    const styles: Record<string, { bg: string; border: string; icon: string; glow: string }> = {
        default: { bg: 'from-blue-500/5 via-cyan-500/5 to-transparent', border: 'border-blue-500/15 hover:border-blue-500/30', icon: 'text-blue-400 bg-blue-500/10', glow: 'shadow-blue-500/5' },
        danger: { bg: 'from-red-500/5 via-rose-500/5 to-transparent', border: 'border-red-500/15 hover:border-red-500/30', icon: 'text-red-400 bg-red-500/10', glow: 'shadow-red-500/5' },
        warning: { bg: 'from-amber-500/5 via-orange-500/5 to-transparent', border: 'border-amber-500/15 hover:border-amber-500/30', icon: 'text-amber-400 bg-amber-500/10', glow: 'shadow-amber-500/5' },
        success: { bg: 'from-green-500/5 via-emerald-500/5 to-transparent', border: 'border-green-500/15 hover:border-green-500/30', icon: 'text-green-400 bg-green-500/10', glow: 'shadow-green-500/5' },
        purple: { bg: 'from-purple-500/5 via-violet-500/5 to-transparent', border: 'border-purple-500/15 hover:border-purple-500/30', icon: 'text-purple-400 bg-purple-500/10', glow: 'shadow-purple-500/5' },
        cyan: { bg: 'from-cyan-500/5 via-teal-500/5 to-transparent', border: 'border-cyan-500/15 hover:border-cyan-500/30', icon: 'text-cyan-400 bg-cyan-500/10', glow: 'shadow-cyan-500/5' },
    };
    const s = styles[variant] || styles.default;

    return (
        <div className={`relative rounded-xl border bg-gradient-to-br ${s.bg} ${s.border} backdrop-blur-sm p-4 transition-all duration-300 hover:shadow-lg ${s.glow} h-full group/widget`}>
            {isEditing && onRemove && (
                <button onClick={onRemove}
                    className="absolute -top-2 -right-2 z-10 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center text-xs font-bold opacity-0 group-hover/widget:opacity-100 transition-opacity hover:bg-red-400">×</button>
            )}
            <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-widest">{widget.name}</span>
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.icon}`}>
                    <Icon className="h-4 w-4" />
                </div>
            </div>
            <div className="text-3xl font-black text-white tracking-tight">{formatValue(value)}</div>
            {widget.description && <p className="text-[11px] text-slate-500 mt-1.5">{widget.description}</p>}
        </div>
    );
}

// ══════════════════════════════════════════════════════════════════
//  BAR CHART — with Tooltip, axis labels, colored bars
// ══════════════════════════════════════════════════════════════════

function BarChartWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const resolved = useResolvedChartData(widget);
    const chartData = resolved?.data ?? null;
    const seriesKeys = resolved?.series;
    const isVertical = widget.config?.layout === 'vertical';
    const dataKey = getDataKey(widget);
    const valueKey = widget.data_source === 'custom_query' ? 'value' : 'count';

    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            {!chartData ? (
                <div className="flex items-center justify-center text-slate-500 py-8 flex-1"><Activity className="h-4 w-4 animate-spin mr-2" /> Loading...</div>
            ) : chartData.length === 0 ? (
                <p className="text-slate-600 text-xs italic text-center py-8 flex-1">No data</p>
            ) : (
                <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} layout={isVertical ? 'vertical' : 'horizontal'}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            {isVertical ? (
                                <>
                                    <XAxis type="number" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                    <YAxis type="category" dataKey={dataKey} stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} width={80} />
                                </>
                            ) : (
                                <>
                                    <XAxis dataKey={dataKey} stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false}
                                        tickFormatter={(v: number) => formatValue(v)} />
                                </>
                            )}
                            <Tooltip {...TOOLTIP_STYLE} />
                            {seriesKeys && seriesKeys.length > 0 ? (
                                <>
                                    {seriesKeys.map((s: string, i: number) => (
                                        <Bar key={s} dataKey={s} stackId="stack" fill={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                                            radius={i === seriesKeys.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
                                    ))}
                                    <Legend verticalAlign="bottom" iconType="circle" iconSize={8}
                                        wrapperStyle={{ fontSize: '10px', paddingTop: '4px' }}
                                        formatter={(value: string) => <span className="text-slate-300 text-[10px]">{value}</span>} />
                                </>
                            ) : (
                                <Bar dataKey={valueKey} radius={isVertical ? [0, 6, 6, 0] : [6, 6, 0, 0]} name="Count">
                                    {chartData.map((entry: any, i: number) => (
                                        <Cell key={i} fill={getColor(widget, entry, i)} />
                                    ))}
                                </Bar>
                            )}
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}
        </WidgetShell>
    );
}

// ══════════════════════════════════════════════════════════════════
//  PIE CHART — Legend + Tooltip only (no inline labels to overflow)
// ══════════════════════════════════════════════════════════════════

function PieChartWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const resolved = useResolvedChartData(widget);
    const chartData = resolved?.data ?? null;
    const nameKey = getDataKey(widget);
    const valueKey = widget.data_source === 'custom_query' ? 'value' : 'count';

    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            {!chartData ? (
                <div className="flex items-center justify-center text-slate-500 py-8 flex-1"><Activity className="h-4 w-4 animate-spin mr-2" /> Loading...</div>
            ) : chartData.length === 0 ? (
                <p className="text-slate-600 text-xs italic text-center py-8 flex-1">No data</p>
            ) : (
                <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={chartData}
                                cx="50%"
                                cy="45%"
                                innerRadius="40%"
                                outerRadius="70%"
                                dataKey={valueKey}
                                nameKey={nameKey}
                                paddingAngle={2}
                            >
                                {chartData.map((entry: any, i: number) => (
                                    <Cell key={i} fill={getColor(widget, entry, i)} />
                                ))}
                            </Pie>
                            <Tooltip
                                {...TOOLTIP_STYLE}
                                formatter={(value: any, name: any) => [`${value}`, `${name}`]}
                            />
                            <Legend
                                verticalAlign="bottom"
                                iconType="circle"
                                iconSize={8}
                                wrapperStyle={{ fontSize: '11px', paddingTop: '4px' }}
                                formatter={(value: string) => <span className="text-slate-300 text-[11px]">{value}</span>}
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </div>
            )}
        </WidgetShell>
    );
}

// ══════════════════════════════════════════════════════════════════
//  AREA CHART — with gradient fill
// ══════════════════════════════════════════════════════════════════

function AreaChartWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const resolved = useResolvedChartData(widget);
    const chartData = resolved?.data ?? null;
    const seriesKeys = resolved?.series;
    const isTimeSeries = resolved?.mode === 'time_series' || resolved?.mode === 'multi_series';
    const xKey = isTimeSeries ? 'date' : 'date';

    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            {!chartData ? (
                <div className="flex items-center justify-center text-slate-500 py-8 flex-1"><Activity className="h-4 w-4 animate-spin mr-2" /> Loading...</div>
            ) : (
                <div className="flex-1 min-h-0">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                            <defs>
                                {seriesKeys && seriesKeys.length > 0 ? (
                                    seriesKeys.map((s: string, i: number) => (
                                        <linearGradient key={s} id={`grad-${widget.id}-${i}`} x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor={ACCENT_COLORS[i % ACCENT_COLORS.length]} stopOpacity={0.2} />
                                            <stop offset="95%" stopColor={ACCENT_COLORS[i % ACCENT_COLORS.length]} stopOpacity={0} />
                                        </linearGradient>
                                    ))
                                ) : (
                                    <linearGradient id={`grad-${widget.id}`} x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                                    </linearGradient>
                                )}
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey={xKey} stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }}
                                tickFormatter={v => {
                                    if (!v) return '';
                                    try { return new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); } catch { return v; }
                                }} />
                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false}
                                tickFormatter={(v: number) => formatValue(v)} />
                            <Tooltip {...TOOLTIP_STYLE}
                                labelFormatter={v => {
                                    try { return new Date(v).toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }); } catch { return v; }
                                }} />
                            {seriesKeys && seriesKeys.length > 0 ? (
                                <>
                                    {seriesKeys.map((s: string, i: number) => (
                                        <Area key={s} type="monotone" dataKey={s}
                                            stroke={ACCENT_COLORS[i % ACCENT_COLORS.length]} strokeWidth={2}
                                            fill={`url(#grad-${widget.id}-${i})`}
                                            dot={false} />
                                    ))}
                                    <Legend verticalAlign="bottom" iconType="circle" iconSize={8}
                                        wrapperStyle={{ fontSize: '10px', paddingTop: '4px' }}
                                        formatter={(value: string) => <span className="text-slate-300 text-[10px]">{value}</span>} />
                                </>
                            ) : (
                                <Area type="monotone" dataKey={isTimeSeries ? 'value' : 'count'} stroke="#818cf8" strokeWidth={2}
                                    fill={`url(#grad-${widget.id})`} dot={{ fill: '#818cf8', r: 2 }} activeDot={{ r: 5 }} />
                            )}
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            )}
        </WidgetShell>
    );
}

// ══════════════════════════════════════════════════════════════════
//  GAUGE — SVG ring gauge
// ══════════════════════════════════════════════════════════════════

function GaugeWidget({ widget, stats, isEditing, onRemove }: {
    widget: DashboardWidgetDef; stats: any; isEditing?: boolean; onRemove?: () => void;
}) {
    const utilData = stats?.team_utilization || { total_operators: 0, assigned_operators: 0, utilization_pct: 0 };
    const pct = utilData.utilization_pct;
    const circumference = 2 * Math.PI * 36;
    const dashOffset = circumference - (pct / 100) * circumference;
    const color = pct >= 80 ? 'text-green-400' : pct >= 50 ? 'text-amber-400' : 'text-red-400';
    const strokeColor = pct >= 80 ? 'stroke-green-500' : pct >= 50 ? 'stroke-amber-500' : 'stroke-red-500';

    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <div className="flex flex-col items-center justify-center gap-2 flex-1">
                <div className="relative w-20 h-20">
                    <svg className="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
                        <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="6" className="text-slate-800" />
                        <circle cx="40" cy="40" r="36" fill="none" strokeWidth="6" strokeLinecap="round"
                            className={`${strokeColor} transition-all duration-1000`}
                            strokeDasharray={circumference} strokeDashoffset={dashOffset} />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className={`text-lg font-black ${color}`}>{pct}%</span>
                    </div>
                </div>
                <span className="text-[10px] text-slate-500 text-center">
                    {utilData.assigned_operators}/{utilData.total_operators} deployed
                </span>
            </div>
        </WidgetShell>
    );
}

// ══════════════════════════════════════════════════════════════════
//  LIST — engagement list, findings, upcoming, activity feed
//  Uses flex-1 + overflow-y-auto so it fills available space
// ══════════════════════════════════════════════════════════════════

function ListWidget({ widget, stats, isEditing, onRemove }: {
    widget: DashboardWidgetDef; stats: any; isEditing?: boolean; onRemove?: () => void;
}) {
    const router = useRouter();
    const listType = widget.config?.list_type || widget.data_source;

    const renderItem = () => {
        switch (listType) {
            case 'engagements':
            case 'my_engagements': {
                const items = stats?.my_engagements || [];
                if (items.length === 0) return <p className="text-slate-600 text-xs italic text-center py-4">No active engagements</p>;
                return (
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-1">
                        {items.map((e: any) => {
                            const badgeClass = ENG_STATUS_BADGE[e.status] || 'bg-slate-500/10 text-slate-400 border-slate-500/30';
                            return (
                                <div key={e.id} onClick={() => router.push(`/engagements/${e.id}`)}
                                    className="flex items-center gap-2.5 p-2.5 rounded-lg hover:bg-slate-800/40 cursor-pointer transition-all group border border-transparent hover:border-slate-700/50">
                                    <div className="flex-1 min-w-0">
                                        <span className="text-sm font-semibold text-white group-hover:text-blue-400 transition-colors truncate block">{e.name}</span>
                                        <span className="text-[10px] text-slate-500">{e.client_name} · {e.finding_count} findings</span>
                                        {e.user_role && (
                                            <span className="text-[9px] text-cyan-400/70 font-medium block mt-0.5">{e.user_role}</span>
                                        )}
                                    </div>
                                    <Badge variant="outline" className={`text-[9px] px-2 h-5 border shrink-0 font-bold ${badgeClass}`}>
                                        {e.status?.replace('_', ' ')}
                                    </Badge>
                                </div>
                            );
                        })}
                    </div>
                );
            }
            case 'findings':
            case 'top_findings': {
                const items = stats?.top_critical_findings || [];
                if (items.length === 0) return <p className="text-slate-600 text-xs italic text-center py-4">No critical/high findings 🎉</p>;
                return (
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-1">
                        {items.map((f: any) => {
                            const sevColor = f.severity === 'CRITICAL'
                                ? 'border-red-500/30 text-red-400 bg-red-500/5'
                                : 'border-orange-500/30 text-orange-400 bg-orange-500/5';
                            return (
                                <div key={f.id} onClick={() => router.push(`/findings/${f.id}?engagementId=${f.engagement_id}`)}
                                    className="flex items-start gap-2 p-2.5 rounded-lg hover:bg-red-500/5 cursor-pointer transition-all group border border-transparent hover:border-red-500/10">
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-white group-hover:text-red-400 transition-colors line-clamp-1">{f.title}</p>
                                        <div className="flex items-center gap-1.5 mt-0.5 text-[10px] text-slate-500">
                                            <Badge variant="outline" className={`text-[9px] px-1.5 h-4 border font-bold ${sevColor}`}>
                                                {f.severity}
                                            </Badge>
                                            <span className="truncate">{f.engagement_name}</span>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                );
            }
            case 'upcoming':
            case 'upcoming_engagements': {
                const items = stats?.upcoming_engagements || [];
                if (items.length === 0) return <p className="text-slate-600 text-xs italic text-center py-4">No upcoming engagements</p>;
                return (
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-1">
                        {items.map((e: any) => (
                            <div key={e.id} onClick={() => router.push(`/engagements/${e.id}`)}
                                className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-slate-800/40 cursor-pointer transition-all group border border-transparent hover:border-slate-700/50">
                                <div className="w-9 text-center shrink-0 rounded-lg bg-slate-800/60 py-1">
                                    <div className="text-[8px] font-bold text-slate-500 uppercase leading-tight">
                                        {e.start_date ? format(parseUTCDate(e.start_date), 'MMM') : '—'}
                                    </div>
                                    <div className="text-base font-black text-white leading-tight">
                                        {e.start_date ? format(parseUTCDate(e.start_date), 'd') : '—'}
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold text-white group-hover:text-blue-400 transition-colors truncate">{e.name}</p>
                                    <p className="text-[10px] text-slate-500 truncate">{e.client_name}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                );
            }
            case 'activity':
            case 'recent_activity': {
                const items = stats?.recent_activity || [];
                const typeIcons: Record<string, any> = {
                    engagement: Target, finding: Bug, asset: Server, testcase: CheckSquare,
                    evidence: FileIcon, comment: MessageSquare, cleanup_artifact: Flame,
                };
                const typeColors: Record<string, string> = {
                    engagement: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20',
                    finding: 'bg-red-500/10 text-red-400 border-red-500/20',
                    asset: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                    testcase: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
                    evidence: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                    comment: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
                    cleanup_artifact: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
                };
                if (items.length === 0) return <p className="text-slate-600 text-xs italic text-center py-6">No recent activity</p>;
                return (
                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-0.5">
                        {items.map((a: any) => {
                            const type = a.type?.toLowerCase();
                            const AIcon = typeIcons[type] || History;
                            const colors = typeColors[type] || 'bg-slate-800 text-slate-400 border-slate-700';
                            return (
                                <div key={a.id} className="flex items-start gap-2.5 p-2.5 rounded-lg hover:bg-slate-800/40 transition-all cursor-pointer"
                                    onClick={() => {
                                        if (type === 'engagement') router.push(`/engagements/${a.resource_id}`);
                                        else if (type === 'finding') router.push(`/findings/${a.resource_id}?engagementId=${a.engagement_id}`);
                                    }}>
                                    <div className={`w-6 h-6 rounded-md flex items-center justify-center border shrink-0 mt-0.5 ${colors}`}>
                                        <AIcon className="h-3 w-3" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-0.5">
                                            <span className="text-[9px] font-bold text-slate-600 uppercase tracking-wider">{a.action?.replaceAll('_', ' ')}</span>
                                            <span className="text-[9px] text-slate-600 ml-auto shrink-0 flex items-center gap-0.5">
                                                <Clock className="h-2 w-2" />
                                                {formatDistanceToNow(parseUTCDate(a.time), { addSuffix: true })}
                                            </span>
                                        </div>
                                        <p className="text-[12px] font-medium text-slate-200 line-clamp-1">{a.title}</p>
                                        <div className="flex items-center gap-1.5 mt-0.5">
                                            <span className="text-[9px] text-slate-500">{a.user}</span>
                                            {a.engagement_name && (
                                                <span className="text-[9px] text-indigo-400/60 flex items-center gap-0.5 truncate">
                                                    · {a.engagement_name}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                );
            }
            default:
                return <p className="text-slate-600 text-xs italic text-center py-4">Unknown list type</p>;
        }
    };

    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            {renderItem()}
        </WidgetShell>
    );
}

// ══════════════════════════════════════════════════════════════════
//  DATA HOOKS — stable params, supports both built-in + custom_query
// ══════════════════════════════════════════════════════════════════

function useResolvedChartData(widget: DashboardWidgetDef): { data: any[] | null; series?: string[]; mode?: string } {
    const dataContext = useContext(WidgetDataContext);
    const builtInData = useWidgetChartData(widget.data_source === 'custom_query' ? '__none__' : widget.data_source);
    const { data: customData } = useCustomWidgetData(
        widget.data_source === 'custom_query' ? widget.id : undefined,
        dataContext,
    );

    if (widget.data_source === 'custom_query') {
        return {
            data: customData?.data || null,
            series: customData?.series,
            mode: customData?.mode,
        };
    }
    return { data: builtInData };
}

function useWidgetChartData(dataSource: string): any[] | null {
    // CRITICAL: useMemo creates stable param objects.
    const stableParams = useMemo(() => {
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - 30);
        return { startDate: start.toISOString().split('T')[0], endDate: end.toISOString().split('T')[0] };
    }, []);

    const skip = dataSource === '__none__';

    const { data: severity } = useSeverityDistribution(!skip && dataSource === 'severity_distribution' ? stableParams : undefined);
    const { data: engStatus } = useEngagementStatus(!skip && dataSource === 'engagement_status' ? stableParams : undefined);
    const { data: findingStatus } = useFindingsByStatus(!skip && dataSource === 'findings_by_status' ? stableParams : undefined);
    const { data: timeline } = useFindingsTimeline(30);
    const { data: engTypes } = useEngagementTypes(!skip && dataSource === 'engagement_types' ? stableParams : undefined);
    const { data: cleanup } = useCleanupStats(!skip && dataSource === 'cleanup_status' ? stableParams : undefined);
    const { data: activity } = useUserActivity(!skip && dataSource === 'top_contributors' ? stableParams : undefined);
    const { data: tcStats } = useTestCaseStats(!skip && dataSource === 'testcase_coverage' ? stableParams : undefined);
    const { data: catStats } = useFindingsByCategory(!skip && dataSource === 'findings_by_category' ? stableParams : undefined);

    if (skip) return null;

    switch (dataSource) {
        case 'severity_distribution': return severity?.distribution || null;
        case 'engagement_status': return engStatus?.distribution || null;
        case 'findings_by_status': return findingStatus?.statuses || null;
        case 'findings_timeline': return timeline?.timeline || null;
        case 'engagement_types': return engTypes?.types || null;
        case 'cleanup_status': return cleanup?.distribution || null;
        case 'top_contributors': return activity?.top_contributors || null;
        case 'testcase_coverage': return tcStats?.by_category || null;
        case 'findings_by_category': return catStats?.categories || null;
        default: return null;
    }
}

// ── Helper: identify the label key for each data source ──────────

function getDataKey(widget: DashboardWidgetDef): string {
    if (widget.data_source === 'custom_query') return 'label';
    switch (widget.data_source) {
        case 'severity_distribution': return 'severity';
        case 'engagement_status': return 'status';
        case 'findings_by_status': return 'status';
        case 'engagement_types': return 'type';
        case 'cleanup_status': return 'status';
        case 'top_contributors': return 'username';
        case 'testcase_coverage': return 'category';
        case 'findings_by_category': return 'category';
        default: return 'name';
    }
}

// ── Helper: color per bar/cell ───────────────────────────────────

function getColor(widget: DashboardWidgetDef, entry: any, index: number): string {
    if (widget.data_source === 'custom_query') return ACCENT_COLORS[index % ACCENT_COLORS.length];
    switch (widget.data_source) {
        case 'severity_distribution': return SEVERITY_COLORS[entry.severity] || ACCENT_COLORS[index % ACCENT_COLORS.length];
        case 'engagement_status': return ENG_STATUS_COLORS[entry.status] || ACCENT_COLORS[index % ACCENT_COLORS.length];
        case 'findings_by_status': return STATUS_COLORS[entry.status] || ACCENT_COLORS[index % ACCENT_COLORS.length];
        case 'cleanup_status': return CLEANUP_COLORS[entry.status] || ACCENT_COLORS[index % ACCENT_COLORS.length];
        default: return widget.config?.colors?.[entry[getDataKey(widget)]] || ACCENT_COLORS[index % ACCENT_COLORS.length];
    }
}


// ══════════════════════════════════════════════════════════════════
//  P4/P5 — new widget flavors (heatmap, scatter, ratio, delta, overlay)
// ══════════════════════════════════════════════════════════════════

/** Given an array of {value: number} entries (or {value} shaped rows),
 *  return the numeric sum. Used by ratio/percentage/delta collapsors. */
function sumValues(rows: Array<{ value?: number }> | null | undefined): number {
    if (!rows) return 0;
    return rows.reduce((s, r) => s + (typeof r.value === 'number' ? r.value : 0), 0);
}

/** Pearson correlation coefficient for two parallel numeric arrays. */
function pearsonR(xs: number[], ys: number[]): number {
    const n = Math.min(xs.length, ys.length);
    if (n < 2) return 0;
    const mx = xs.slice(0, n).reduce((a, b) => a + b, 0) / n;
    const my = ys.slice(0, n).reduce((a, b) => a + b, 0) / n;
    let num = 0, dx = 0, dy = 0;
    for (let i = 0; i < n; i++) {
        const a = xs[i] - mx, b = ys[i] - my;
        num += a * b;
        dx += a * a;
        dy += b * b;
    }
    const denom = Math.sqrt(dx * dy);
    return denom === 0 ? 0 : num / denom;
}

// Heatmap — consumes 2D group_by results. Each row carries `labels: [x, y]`
// and `value`. We pivot to a matrix and colour cells by intensity.
function HeatmapWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const { data: raw } = useResolvedChartData(widget);
    const cells = Array.isArray(raw) ? raw : [];
    // Extract axis dims from the first row's labels[]; skip if not 2D.
    if (!cells.length || !Array.isArray(cells[0]?.labels) || cells[0].labels.length < 2) {
        return (
            <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                <p className="text-slate-500 text-xs italic text-center py-4">
                    Heatmap needs a 2D group-by (e.g. severity × status).
                </p>
            </WidgetShell>
        );
    }
    const xVals = Array.from(new Set(cells.map(c => c.labels[0])));
    const yVals = Array.from(new Set(cells.map(c => c.labels[1])));
    // Map cellKey → value
    const grid: Record<string, number> = {};
    let maxVal = 0;
    for (const c of cells) {
        const k = `${c.labels[0]}||${c.labels[1]}`;
        grid[k] = c.value;
        if (c.value > maxVal) maxVal = c.value;
    }
    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <div className="overflow-x-auto max-w-full">
                <table className="w-full text-[10px] border-collapse">
                    <thead>
                        <tr>
                            <th className="p-1 text-left text-slate-500"></th>
                            {xVals.map(x => (
                                <th key={x} className="p-1 text-slate-400 font-medium text-center">{String(x)}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {yVals.map(y => (
                            <tr key={y}>
                                <td className="p-1 text-slate-400 font-medium whitespace-nowrap pr-2">{String(y)}</td>
                                {xVals.map(x => {
                                    const v = grid[`${x}||${y}`] || 0;
                                    const alpha = maxVal === 0 ? 0 : v / maxVal;
                                    return (
                                        <td
                                            key={x}
                                            className="p-1 text-center text-white font-mono rounded"
                                            style={{ backgroundColor: `rgba(139, 92, 246, ${0.15 + alpha * 0.75})` }}
                                            title={`${y} × ${x}: ${v}`}
                                        >
                                            {v || ''}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </WidgetShell>
    );
}

// Scatter widget: consumes composite results (2+ queries with a shared
// bucket key). Bucket keys come from group_by columns; we join on the
// primary label. Shows Pearson r underneath.
function ScatterWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const { data: raw } = useResolvedChartData(widget);
    // Composite response? { results: [{data:[...]}, {data:[...]}] } lives on `raw`.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results = (raw as any)?.results;
    if (!Array.isArray(results) || results.length < 2) {
        return (
            <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                <p className="text-slate-500 text-xs italic text-center py-4">
                    Scatter needs a composite widget with at least 2 sub-queries.
                </p>
            </WidgetShell>
        );
    }
    const A: Array<{ label: string; value: number }> = results[0].data || [];
    const B: Array<{ label: string; value: number }> = results[1].data || [];
    const byLabel = new Map<string, { x?: number; y?: number }>();
    for (const r of A) byLabel.set(r.label, { ...(byLabel.get(r.label) || {}), x: r.value });
    for (const r of B) byLabel.set(r.label, { ...(byLabel.get(r.label) || {}), y: r.value });
    const points = Array.from(byLabel.entries())
        .filter(([, v]) => v.x !== undefined && v.y !== undefined)
        .map(([label, v]) => ({ label, x: v.x!, y: v.y! }));
    const r = pearsonR(points.map(p => p.x), points.map(p => p.y));
    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <ResponsiveContainer width="100%" height={200}>
                <ScatterChart>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="x" name="A" stroke="#94a3b8" fontSize={10} />
                    <YAxis dataKey="y" name="B" stroke="#94a3b8" fontSize={10} />
                    <ZAxis range={[60, 60]} />
                    <Tooltip {...TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }} />
                    <Scatter data={points} fill="#8b5cf6" />
                </ScatterChart>
            </ResponsiveContainer>
            <div className="text-center mt-1 text-[11px] text-slate-400">
                Pearson r = <span className={r > 0.3 ? 'text-green-400 font-semibold' : r < -0.3 ? 'text-red-400 font-semibold' : 'text-slate-400'}>{r.toFixed(3)}</span>
                <span className="ml-2 text-slate-600">({points.length} points)</span>
            </div>
        </WidgetShell>
    );
}

// Ratio / Percentage: sum(query0.data) op sum(query1.data). Rendered as a
// giant stat card. Zero-denominator surfaces as em-dash.
function RatioWidget({ widget, isEditing, onRemove, mode }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void; mode: 'ratio' | 'percentage';
}) {
    const { data: raw } = useResolvedChartData(widget);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results = (raw as any)?.results;
    if (!Array.isArray(results) || results.length < 2) {
        return (
            <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                <p className="text-slate-500 text-xs italic text-center py-4">
                    {mode === 'ratio' ? 'Ratio' : 'Percentage'} needs 2 sub-queries in config.queries.
                </p>
            </WidgetShell>
        );
    }
    const a = sumValues(results[0].data);
    const b = sumValues(results[1].data);
    let display = '—';
    if (b !== 0) {
        const v = mode === 'ratio' ? a / b : (a / b) * 100;
        display = mode === 'ratio' ? v.toFixed(2) : `${v.toFixed(1)}%`;
    }
    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <div className="text-center py-6">
                <div className="text-4xl font-bold text-white">{display}</div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-2">
                    {formatValue(a)} of {formatValue(b)}
                </div>
            </div>
        </WidgetShell>
    );
}

// Delta: results[0] = current period, results[1] = previous period.
// Show current + percent-change chip.
function DeltaWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const { data: raw } = useResolvedChartData(widget);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results = (raw as any)?.results;
    if (!Array.isArray(results) || results.length < 2) {
        return (
            <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                <p className="text-slate-500 text-xs italic text-center py-4">
                    Delta needs 2 sub-queries (current + previous period).
                </p>
            </WidgetShell>
        );
    }
    const curr = sumValues(results[0].data);
    const prev = sumValues(results[1].data);
    const delta = prev === 0 ? null : ((curr - prev) / prev) * 100;
    const arrow = delta === null ? '' : delta > 0 ? '▲' : delta < 0 ? '▼' : '=';
    const color = delta === null ? 'text-slate-500' : delta > 0 ? 'text-red-400' : 'text-green-400';
    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <div className="text-center py-6">
                <div className="text-4xl font-bold text-white">{formatValue(curr)}</div>
                <div className={`mt-2 text-sm font-semibold ${color}`}>
                    {arrow} {delta === null ? 'no baseline' : `${Math.abs(delta).toFixed(1)}%`}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">
                    vs previous ({formatValue(prev)})
                </div>
            </div>
        </WidgetShell>
    );
}

// Overlay time-series: multiple sub-queries with time_bucket → LineChart
// with one Line per sub-query, joined on the shared date key.
function OverlayWidget({ widget, isEditing, onRemove }: {
    widget: DashboardWidgetDef; isEditing?: boolean; onRemove?: () => void;
}) {
    const { data: raw } = useResolvedChartData(widget);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results = (raw as any)?.results;
    if (!Array.isArray(results) || results.length < 2) {
        return (
            <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
                <p className="text-slate-500 text-xs italic text-center py-4">
                    Overlay needs 2+ time-series sub-queries.
                </p>
            </WidgetShell>
        );
    }
    // Merge on `date` key. Each sub-query contributes a column named
    // ``s${i}`` for the line to reference.
    const dateMap: Record<string, Record<string, number | string>> = {};
    results.forEach((r: { data?: Array<{ date?: string; value?: number }> }, i: number) => {
        (r.data || []).forEach((row) => {
            const d = row.date;
            if (!d) return;
            if (!dateMap[d]) dateMap[d] = { date: d };
            dateMap[d][`s${i}`] = row.value || 0;
        });
    });
    const merged = Object.values(dateMap).sort((a, b) => String(a.date).localeCompare(String(b.date)));
    const labels = widget.config?.series_labels || results.map((_: unknown, i: number) => `Series ${i + 1}`);
    return (
        <WidgetShell widget={widget} isEditing={isEditing} onRemove={onRemove}>
            <ResponsiveContainer width="100%" height={200}>
                <LineChart data={merged}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                        dataKey="date"
                        tickFormatter={(v: string) => v ? format(new Date(v), 'MMM d') : ''}
                        stroke="#94a3b8"
                        fontSize={10}
                    />
                    <YAxis stroke="#94a3b8" fontSize={10} />
                    <Tooltip {...TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    {results.map((_: unknown, i: number) => (
                        <Line
                            key={i}
                            type="monotone"
                            dataKey={`s${i}`}
                            name={labels[i] || `Series ${i + 1}`}
                            stroke={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                            strokeWidth={2}
                            dot={false}
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </WidgetShell>
    );
}
