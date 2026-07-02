'use client';

/**
 * Admin Widget Management — CRUD for widget definitions.
 * Advanced step-by-step query builder with date-range filtering,
 * time-series bucketing, multi-series support, and live preview.
 */

import { useState, useMemo, useEffect } from 'react';
import {
    useDashboardWidgets, useCreateWidget, useUpdateWidget, useDeleteWidget,
    useQueryPreview, useQuerySchema, useComputedMetrics,
    type DashboardWidgetDef, type QueryDefinition, type QuerySchema,
} from '@/lib/hooks/use-dashboard-widgets';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
    LayoutGrid, Plus, Pencil, Trash2, BarChart3, Play, X, Database,
    Bug, Target, Server, CheckSquare, Flame, Clock, CalendarDays,
    TrendingUp, Layers, Filter, ArrowRight, Table2, AlertTriangle,
    Shield, ClipboardCheck, ChevronDown, ChevronUp, Zap, LineChart,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import {
    ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Tooltip,
    XAxis, YAxis, CartesianGrid, AreaChart, Area, LineChart as RLineChart, Line, Legend,
} from 'recharts';

// ── Constants ──────────────────────────────────────────────────────

const WIDGET_TYPES = [
    { value: 'bar_chart', label: 'Bar Chart', Icon: BarChart3 },
    { value: 'pie_chart', label: 'Pie Chart', Icon: Target },
    { value: 'area_chart', label: 'Area Chart', Icon: TrendingUp },
    { value: 'stat_card', label: 'Stat Card', Icon: Zap },
    { value: 'gauge', label: 'Gauge', Icon: Target },
    { value: 'list', label: 'List', Icon: Table2 },
];

const WIDGET_SIZES = [
    { value: 'small', label: 'Small (1×1)' },
    { value: 'medium', label: 'Medium (2×1)' },
    { value: 'large', label: 'Large (2×2)' },
    { value: 'wide', label: 'Wide (3×1)' },
    { value: 'full', label: 'Full Width (6×1)' },
];

const WIDGET_CATEGORIES = [
    { value: 'overview', label: 'Overview' },
    { value: 'findings', label: 'Findings' },
    { value: 'engagements', label: 'Engagements' },
    { value: 'operators', label: 'Operators' },
    { value: 'clients', label: 'Clients' },
    { value: 'custom', label: 'Custom' },
];

const DATA_SOURCES = [
    { value: 'personal_stats.my_active_engagements', label: 'My Active Engagements (stat)' },
    { value: 'personal_stats.my_open_findings', label: 'My Open Findings (stat)' },
    { value: 'personal_stats.my_pending_tests', label: 'Pending Tests (stat)' },
    { value: 'personal_stats.my_findings_this_month', label: 'Findings This Month (stat)' },
    { value: 'personal_stats.my_pending_cleanup', label: 'Pending Cleanup (stat)' },
    { value: 'personal_stats.my_unread_notifications', label: 'Unread Notifications (stat)' },
    { value: 'severity_distribution', label: 'Severity Distribution (chart)' },
    { value: 'findings_by_status', label: 'Findings by Status (chart)' },
    { value: 'engagement_status', label: 'Engagement Pipeline (chart)' },
    { value: 'findings_timeline', label: 'Findings Timeline (chart)' },
    { value: 'engagement_types', label: 'Engagements by Type (chart)' },
    { value: 'cleanup_status', label: 'Cleanup Status (chart)' },
    { value: 'top_contributors', label: 'Top Contributors (chart)' },
    { value: 'testcase_coverage', label: 'Test Case Coverage (chart)' },
    { value: 'findings_by_category', label: 'Findings by Category (chart)' },
    { value: 'my_engagements', label: 'My Engagements (list)' },
    { value: 'top_findings', label: 'Top Critical Findings (list)' },
    { value: 'upcoming_engagements', label: 'Upcoming Engagements (list)' },
    { value: 'recent_activity', label: 'Recent Activity (list)' },
    { value: 'team_utilization', label: 'Team Utilization (gauge)' },
    { value: 'custom_query', label: '⚡ Custom Query Builder' },
];

const TABLE_ICONS: Record<string, any> = {
    findings: Bug,
    engagements: Target,
    assets: Server,
    testcases: CheckSquare,
    cleanup_artifacts: Flame,
};

const TABLE_LABELS: Record<string, string> = {
    findings: 'Findings',
    engagements: 'Engagements',
    assets: 'Assets',
    testcases: 'Test Cases',
    cleanup_artifacts: 'Cleanup Artifacts',
};

const DATE_RANGE_OPTIONS = [
    { value: '7d', label: '7 days' },
    { value: '30d', label: '30 days' },
    { value: '90d', label: '90 days' },
    { value: 'quarter', label: 'Quarter' },
    { value: 'year', label: 'Year' },
    { value: 'all', label: 'All time' },
];

const AGGREGATIONS = [
    { value: 'count', label: 'Count' },
    { value: 'avg', label: 'Average' },
    { value: 'sum', label: 'Sum' },
    { value: 'max', label: 'Maximum' },
    { value: 'min', label: 'Minimum' },
];

const CATEGORY_COLORS: Record<string, string> = {
    overview: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    findings: 'bg-red-500/10 text-red-400 border-red-500/20',
    engagements: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    operators: 'bg-green-500/10 text-green-400 border-green-500/20',
    clients: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    custom: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

const ACCENT_COLORS = ['#818cf8', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#ec4899', '#8b5cf6', '#14b8a6'];

const TOOLTIP_STYLE = {
    contentStyle: { backgroundColor: '#1a2235', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0' },
    itemStyle: { color: '#e2e8f0' },
    labelStyle: { color: '#94a3b8' },
};

// ── Form State ─────────────────────────────────────────────────────

interface FormState {
    name: string;
    description: string;
    widget_type: string;
    data_source: string;
    size: string;
    category: string;
    icon: string;
    // Query builder
    query_table: string;
    query_group_by: string;
    query_aggregation: string;
    query_value_column: string;
    query_limit: number;
    // Advanced
    query_date_column: string;
    query_date_range: string;
    query_time_bucket: string;
    query_series_by: string;
    query_filters: Array<{ column: string; operator: string; value: string }>;
}

const EMPTY_FORM: FormState = {
    name: '', description: '', widget_type: 'bar_chart',
    data_source: 'severity_distribution', size: 'medium', category: 'custom', icon: 'BarChart3',
    query_table: 'findings', query_group_by: 'severity', query_aggregation: 'count',
    query_value_column: 'id', query_limit: 50,
    query_date_column: '', query_date_range: '30d', query_time_bucket: '',
    query_series_by: '', query_filters: [],
};

// ══════════════════════════════════════════════════════════════════
//  MAIN COMPONENT
// ══════════════════════════════════════════════════════════════════

export function WidgetManagement() {
    const { data: widgets = [], isLoading } = useDashboardWidgets();
    const createWidget = useCreateWidget();
    const updateWidget = useUpdateWidget();
    const deleteWidget = useDeleteWidget();
    const queryPreview = useQueryPreview();
    const { data: schema } = useQuerySchema();
    const { data: metricsData } = useComputedMetrics();

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [form, setForm] = useState<FormState>(EMPTY_FORM);
    const [previewData, setPreviewData] = useState<any>(null);
    const [previewMode, setPreviewMode] = useState<'chart' | 'table'>('chart');
    const [builderStep, setBuilderStep] = useState(0); // 0=source 1=metrics 2=filters 3=viz 4=preview

    const openCreate = () => {
        setEditingId(null);
        setForm(EMPTY_FORM);
        setPreviewData(null);
        setBuilderStep(0);
        setDialogOpen(true);
    };

    const openEdit = (w: DashboardWidgetDef) => {
        const qConfig = w.config?.query;
        setEditingId(w.id);
        setForm({
            name: w.name,
            description: w.description || '',
            widget_type: w.widget_type,
            data_source: w.data_source,
            size: w.size,
            category: w.category,
            icon: w.icon || 'BarChart3',
            query_table: qConfig?.table || 'findings',
            query_group_by: qConfig?.group_by || 'severity',
            query_aggregation: qConfig?.aggregation || 'count',
            query_value_column: qConfig?.value_column || 'id',
            query_limit: qConfig?.limit || 50,
            query_date_column: qConfig?.date_column || '',
            query_date_range: qConfig?.date_range || '30d',
            query_time_bucket: qConfig?.time_bucket || '',
            query_series_by: qConfig?.series_by || '',
            query_filters: qConfig?.filters || [],
        });
        setPreviewData(null);
        setBuilderStep(0);
        setDialogOpen(true);
    };

    const handlePreview = async () => {
        try {
            const queryDef: QueryDefinition = {
                table: form.query_table,
                group_by: form.query_group_by,
                aggregation: form.query_aggregation,
                value_column: form.query_value_column,
                limit: form.query_limit,
            };
            if (form.query_date_column) {
                queryDef.date_column = form.query_date_column;
                queryDef.date_range = form.query_date_range;
            }
            if (form.query_time_bucket) {
                queryDef.time_bucket = form.query_time_bucket;
                if (!queryDef.date_column) {
                    // Auto-pick first date column
                    const tSchema = schema?.schema?.[form.query_table];
                    if (tSchema?.date_columns?.[0]) {
                        queryDef.date_column = tSchema.date_columns[0];
                        queryDef.date_range = form.query_date_range || '30d';
                    }
                }
            }
            if (form.query_series_by) queryDef.series_by = form.query_series_by;
            if (form.query_filters.length > 0) queryDef.filters = form.query_filters;

            const result = await queryPreview.mutateAsync(queryDef);
            setPreviewData(result);
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Query failed'));
        }
    };

    const handleSave = async () => {
        try {
            const config: any = {};
            if (form.data_source === 'custom_query') {
                const q: any = {
                    table: form.query_table,
                    group_by: form.query_group_by,
                    aggregation: form.query_aggregation,
                    value_column: form.query_value_column,
                    limit: form.query_limit,
                };
                if (form.query_date_column) {
                    q.date_column = form.query_date_column;
                    q.date_range = form.query_date_range;
                }
                if (form.query_time_bucket) {
                    q.time_bucket = form.query_time_bucket;
                    if (!q.date_column) {
                        const tSchema = schema?.schema?.[form.query_table];
                        if (tSchema?.date_columns?.[0]) {
                            q.date_column = tSchema.date_columns[0];
                            q.date_range = form.query_date_range || '30d';
                        }
                    }
                }
                if (form.query_series_by) q.series_by = form.query_series_by;
                if (form.query_filters.length > 0) q.filters = form.query_filters;
                config.query = q;
            }

            const payload: any = {
                name: form.name,
                description: form.description,
                widget_type: form.widget_type,
                data_source: form.data_source,
                size: form.size,
                category: form.category,
                icon: form.icon,
                config,
            };

            if (editingId) {
                await updateWidget.mutateAsync({ id: editingId, ...payload });
                toast.success('Widget updated');
            } else {
                await createWidget.mutateAsync(payload);
                toast.success('Widget created');
            }
            setDialogOpen(false);
        } catch {
            toast.error('Failed to save widget');
        }
    };

    const handleDelete = async (id: string) => {
        try {
            await deleteWidget.mutateAsync(id);
            toast.success('Widget deleted');
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Failed to delete widget'));
        }
    };

    const handleToggleActive = async (w: DashboardWidgetDef) => {
        try {
            await updateWidget.mutateAsync({ id: w.id, is_active: !w.is_active } as any);
            toast.success(`Widget ${w.is_active ? 'disabled' : 'enabled'}`);
        } catch {
            toast.error('Failed to update widget');
        }
    };

    const handleTableChange = (table: string) => {
        const tSchema = schema?.schema?.[table];
        setForm(f => ({
            ...f,
            query_table: table,
            query_group_by: tSchema?.group_by[0] || '',
            query_value_column: tSchema?.aggregate[0] || 'id',
            query_date_column: '',
            query_time_bucket: '',
            query_series_by: '',
            query_filters: [],
        }));
        setPreviewData(null);
    };

    // Current table schema
    const tSchema = schema?.schema?.[form.query_table];

    if (isLoading) {
        return (
            <Card className="border-slate-800 bg-slate-900/50">
                <CardContent className="p-8">
                    <p className="text-slate-400 text-center">Loading widgets...</p>
                </CardContent>
            </Card>
        );
    }

    const systemWidgets = widgets.filter(w => w.is_system);
    const customWidgets = widgets.filter(w => !w.is_system);

    return (
        <div className="space-y-6">
            {/* Computed Metrics Cards */}
            {metricsData?.metrics && (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                    {metricsData.metrics.map(m => {
                        const MIcon = TABLE_ICONS[m.icon] || ({ Target, CheckSquare, AlertTriangle, Shield, Server, ClipboardCheck } as any)[m.icon] || Zap;
                        return (
                            <div key={m.key} className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-3">
                                <div className="flex items-center gap-2 mb-2">
                                    <div className="w-6 h-6 rounded-md bg-cyan-500/10 flex items-center justify-center">
                                        <MIcon className="h-3 w-3 text-cyan-400" />
                                    </div>
                                    <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider truncate">{m.label}</span>
                                </div>
                                <div className="text-xl font-black text-white">
                                    {m.format === 'percent' ? `${m.value}%` : m.value}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            <Card className="border-slate-800 bg-slate-900/50">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <div className="p-1.5 rounded-lg bg-primary/10 border border-primary/20">
                                    <LayoutGrid className="h-4 w-4 text-primary" />
                                </div>
                                Dashboard Widgets
                            </CardTitle>
                            <CardDescription>
                                Manage widget definitions. {systemWidgets.length} system + {customWidgets.length} custom widgets.
                            </CardDescription>
                        </div>
                        <Button size="sm" onClick={openCreate}
                            className="bg-primary hover:bg-primary/90 text-white gap-1.5 h-8 text-xs">
                            <Plus className="h-3.5 w-3.5" /> Create Widget
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="divide-y divide-slate-800/60">
                        {widgets.map(w => (
                            <div key={w.id} className="flex items-center gap-3 py-3">
                                <div className="w-8 h-8 rounded-lg bg-slate-800/80 flex items-center justify-center shrink-0">
                                    {w.data_source === 'custom_query'
                                        ? <Database className="h-4 w-4 text-cyan-400" />
                                        : <BarChart3 className="h-4 w-4 text-slate-400" />}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium text-white">{w.name}</span>
                                        <Badge variant="outline" className={`text-[9px] px-1.5 h-4 border ${CATEGORY_COLORS[w.category] || ''}`}>
                                            {w.category}
                                        </Badge>
                                        {w.is_system && (
                                            <Badge className="bg-slate-500/10 text-slate-500 border-slate-500/20 text-[9px]">System</Badge>
                                        )}
                                        {w.data_source === 'custom_query' && (
                                            <Badge className="bg-cyan-500/10 text-cyan-400 border-cyan-500/20 text-[9px]">Custom Query</Badge>
                                        )}
                                    </div>
                                    <p className="text-[10px] text-slate-500 mt-0.5">
                                        {w.widget_type} · {w.size}
                                        {w.data_source === 'custom_query'
                                            ? ` · ${w.config?.query?.table || '?'} → ${w.config?.query?.group_by || '?'}`
                                            + (w.config?.query?.time_bucket ? ` (${w.config.query.time_bucket})` : '')
                                            + (w.config?.query?.series_by ? ` × ${w.config.query.series_by}` : '')
                                            : ` · ${w.data_source}`
                                        }
                                    </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <Switch
                                        checked={w.is_active}
                                        onCheckedChange={() => handleToggleActive(w)}
                                    />
                                    <Button size="sm" variant="ghost" onClick={() => openEdit(w)}
                                        className="h-7 w-7 p-0 text-slate-400 hover:text-white">
                                        <Pencil className="h-3.5 w-3.5" />
                                    </Button>
                                    {!w.is_system && (
                                        <Button size="sm" variant="ghost" onClick={() => handleDelete(w.id)}
                                            className="h-7 w-7 p-0 text-slate-400 hover:text-red-400">
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                    )}
                                </div>
                            </div>
                        ))}
                        {widgets.length === 0 && (
                            <p className="text-slate-600 text-sm text-center py-6 italic">No widgets defined</p>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* ══════════════════════════════════════════════════════════════
                CREATE / EDIT DIALOG
            ══════════════════════════════════════════════════════════════ */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="bg-slate-950 border-slate-800 max-w-3xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="text-white flex items-center gap-2">
                            <Database className="h-5 w-5 text-primary" />
                            {editingId ? 'Edit Widget' : 'Create Widget'}
                        </DialogTitle>
                        <DialogDescription>
                            Define a widget that users can add to their dashboard.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4">
                        {/* Name + Description */}
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Name *</Label>
                                <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                    placeholder="My Widget"
                                    className="bg-slate-900 border-slate-700 text-white h-9" />
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Description</Label>
                                <Input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                                    placeholder="Optional description"
                                    className="bg-slate-900 border-slate-700 text-white h-9" />
                            </div>
                        </div>

                        {/* Chart type + Size + Category */}
                        <div className="grid grid-cols-3 gap-3">
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Chart Type</Label>
                                <Select value={form.widget_type} onValueChange={v => setForm(f => ({ ...f, widget_type: v }))}>
                                    <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-9">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-950 border-slate-800">
                                        {WIDGET_TYPES.map(t => (
                                            <SelectItem key={t.value} value={t.value} className="text-slate-200 focus:bg-slate-800 focus:text-white">
                                                <span className="flex items-center gap-1.5"><t.Icon className="h-3.5 w-3.5" /> {t.label}</span>
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Size</Label>
                                <Select value={form.size} onValueChange={v => setForm(f => ({ ...f, size: v }))}>
                                    <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-9">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-950 border-slate-800">
                                        {WIDGET_SIZES.map(s => (
                                            <SelectItem key={s.value} value={s.value} className="text-slate-200 focus:bg-slate-800 focus:text-white">{s.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="space-y-1.5">
                                <Label className="text-slate-300 text-xs">Category</Label>
                                <Select value={form.category} onValueChange={v => setForm(f => ({ ...f, category: v }))}>
                                    <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-9">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="bg-slate-950 border-slate-800">
                                        {WIDGET_CATEGORIES.map(c => (
                                            <SelectItem key={c.value} value={c.value} className="text-slate-200 focus:bg-slate-800 focus:text-white">{c.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        {/* Data Source */}
                        <div className="space-y-1.5">
                            <Label className="text-slate-300 text-xs">Data Source</Label>
                            <Select value={form.data_source} onValueChange={v => setForm(f => ({ ...f, data_source: v }))}>
                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-9">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-slate-950 border-slate-800 max-h-[300px]">
                                    {DATA_SOURCES.map(d => (
                                        <SelectItem key={d.value} value={d.value} className="text-slate-200 focus:bg-slate-800 focus:text-white">{d.label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* ━━ CUSTOM QUERY BUILDER ━━ */}
                        {form.data_source === 'custom_query' && tSchema && (
                            <div className="rounded-xl border border-cyan-500/20 bg-gradient-to-b from-cyan-500/5 to-transparent p-4 space-y-4">
                                <div className="flex items-center gap-2 mb-1">
                                    <div className="p-1 rounded-md bg-cyan-500/10">
                                        <Database className="h-4 w-4 text-cyan-400" />
                                    </div>
                                    <span className="text-sm font-bold text-cyan-300">Query Builder</span>
                                    <span className="text-[10px] text-cyan-500/60 ml-auto">Safe, parameterized queries — no raw SQL</span>
                                </div>

                                {/* ── Step 1: Data Source Table ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">1</span>
                                        <span className="text-xs font-bold text-slate-200">Data Source</span>
                                    </div>
                                    <div className="flex gap-2 flex-wrap">
                                        {schema?.tables?.map(t => {
                                            const TIcon = TABLE_ICONS[t] || Database;
                                            const isActive = form.query_table === t;
                                            return (
                                                <button key={t} onClick={() => handleTableChange(t)}
                                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border
                                                        ${isActive
                                                            ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                                                            : 'bg-slate-900/50 text-slate-400 border-slate-700/50 hover:border-slate-600 hover:text-slate-300'}`}>
                                                    <TIcon className="h-3.5 w-3.5" />
                                                    {TABLE_LABELS[t] || t}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* ── Step 2: Metrics ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">2</span>
                                        <span className="text-xs font-bold text-slate-200">Metrics</span>
                                    </div>
                                    <div className="grid grid-cols-4 gap-2">
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Group By</Label>
                                            <Select value={form.query_group_by} onValueChange={v => { setForm(f => ({ ...f, query_group_by: v })); setPreviewData(null); }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.group_by.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{c}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Aggregation</Label>
                                            <Select value={form.query_aggregation} onValueChange={v => { setForm(f => ({ ...f, query_aggregation: v })); setPreviewData(null); }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {AGGREGATIONS.map(a => (
                                                        <SelectItem key={a.value} value={a.value} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{a.label}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Value Column</Label>
                                            <Select value={form.query_value_column} onValueChange={v => { setForm(f => ({ ...f, query_value_column: v })); setPreviewData(null); }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.aggregate.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{c}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Limit</Label>
                                            <Input type="number" value={form.query_limit} min={1} max={500}
                                                onChange={e => setForm(f => ({ ...f, query_limit: parseInt(e.target.value) || 50 }))}
                                                className="bg-slate-900 border-slate-700 text-white h-8 text-xs" />
                                        </div>
                                    </div>
                                </div>

                                {/* ── Step 3: Date Range + Time Series ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">3</span>
                                        <span className="text-xs font-bold text-slate-200">Date Range & Time Series</span>
                                        <CalendarDays className="h-3.5 w-3.5 text-slate-500" />
                                    </div>

                                    {tSchema.date_columns.length > 0 ? (
                                        <div className="space-y-3">
                                            {/* Date column picker */}
                                            <div className="grid grid-cols-2 gap-2">
                                                <div className="space-y-1">
                                                    <Label className="text-slate-400 text-[10px]">Date Column</Label>
                                                    <Select value={form.query_date_column || '__none__'} onValueChange={v => { setForm(f => ({ ...f, query_date_column: v === '__none__' ? '' : v })); setPreviewData(null); }}>
                                                        <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent className="bg-slate-950 border-slate-800">
                                                            <SelectItem value="__none__" className="text-slate-400 focus:bg-slate-800 focus:text-white text-xs">No date filter</SelectItem>
                                                            {tSchema.date_columns.map(c => (
                                                                <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{c}</SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                {form.query_date_column && (
                                                    <div className="space-y-1">
                                                        <Label className="text-slate-400 text-[10px]">Time Bucket</Label>
                                                        <Select value={form.query_time_bucket || '__none__'} onValueChange={v => { setForm(f => ({ ...f, query_time_bucket: v === '__none__' ? '' : v })); setPreviewData(null); }}>
                                                            <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent className="bg-slate-950 border-slate-800">
                                                                <SelectItem value="__none__" className="text-slate-400 focus:bg-slate-800 focus:text-white text-xs">No bucketing (filter only)</SelectItem>
                                                                <SelectItem value="day" className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">By Day</SelectItem>
                                                                <SelectItem value="week" className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">By Week</SelectItem>
                                                                <SelectItem value="month" className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">By Month</SelectItem>
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Date range pills */}
                                            {form.query_date_column && (
                                                <div className="flex gap-1.5 flex-wrap">
                                                    {DATE_RANGE_OPTIONS.map(dr => (
                                                        <button key={dr.value}
                                                            onClick={() => { setForm(f => ({ ...f, query_date_range: dr.value })); setPreviewData(null); }}
                                                            className={`text-[10px] font-bold px-2.5 py-1 rounded-full transition-all border
                                                                ${form.query_date_range === dr.value
                                                                    ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                                                                    : 'text-slate-500 border-slate-700/50 hover:text-slate-300 hover:border-slate-600'}`}>
                                                            {dr.label}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Multi-series toggle */}
                                            {tSchema.series_by.length > 0 && (
                                                <div className="grid grid-cols-2 gap-2">
                                                    <div className="space-y-1">
                                                        <Label className="text-slate-400 text-[10px] flex items-center gap-1">
                                                            <Layers className="h-3 w-3" /> Multi-Series (split by)
                                                        </Label>
                                                        <Select value={form.query_series_by || '__none__'} onValueChange={v => { setForm(f => ({ ...f, query_series_by: v === '__none__' ? '' : v })); setPreviewData(null); }}>
                                                            <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent className="bg-slate-950 border-slate-800">
                                                                <SelectItem value="__none__" className="text-slate-400 focus:bg-slate-800 focus:text-white text-xs">No split (single series)</SelectItem>
                                                                {tSchema.series_by.map(c => (
                                                                    <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{c}</SelectItem>
                                                                ))}
                                                            </SelectContent>
                                                        </Select>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <p className="text-slate-600 text-[10px] italic">No date columns available for this table.</p>
                                    )}
                                </div>

                                {/* ── Step 4: Filters ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">4</span>
                                        <span className="text-xs font-bold text-slate-200">Filters</span>
                                        <Filter className="h-3.5 w-3.5 text-slate-500" />
                                        <button onClick={() => setForm(f => ({ ...f, query_filters: [...f.query_filters, { column: tSchema.filter_columns[0] || '', operator: 'eq', value: '' }] }))}
                                            className="ml-auto text-[10px] text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1">
                                            <Plus className="h-3 w-3" /> Add Filter
                                        </button>
                                    </div>
                                    {form.query_filters.length === 0 && (
                                        <p className="text-slate-600 text-[10px] italic">No filters applied — showing all data.</p>
                                    )}
                                    {form.query_filters.map((filter, idx) => (
                                        <div key={idx} className="flex items-center gap-2">
                                            <Select value={filter.column} onValueChange={v => {
                                                const filters = [...form.query_filters];
                                                filters[idx] = { ...filters[idx], column: v };
                                                setForm(f => ({ ...f, query_filters: filters }));
                                                setPreviewData(null);
                                            }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] w-32">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.filter_columns.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{c}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Select value={filter.operator} onValueChange={v => {
                                                const filters = [...form.query_filters];
                                                filters[idx] = { ...filters[idx], operator: v };
                                                setForm(f => ({ ...f, query_filters: filters }));
                                                setPreviewData(null);
                                            }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {(schema?.filter_operators || ['eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'like']).map(op => (
                                                        <SelectItem key={op} value={op} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{op}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Input value={filter.value} placeholder="value"
                                                onChange={e => {
                                                    const filters = [...form.query_filters];
                                                    filters[idx] = { ...filters[idx], value: e.target.value };
                                                    setForm(f => ({ ...f, query_filters: filters }));
                                                    setPreviewData(null);
                                                }}
                                                className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] flex-1" />
                                            <button onClick={() => {
                                                setForm(f => ({ ...f, query_filters: f.query_filters.filter((_, i) => i !== idx) }));
                                                setPreviewData(null);
                                            }}
                                                className="text-red-400 hover:text-red-300 p-1">
                                                <X className="h-3 w-3" />
                                            </button>
                                        </div>
                                    ))}
                                </div>

                                {/* ── Step 5: Preview ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">5</span>
                                        <span className="text-xs font-bold text-slate-200">Preview</span>
                                        <div className="ml-auto flex items-center gap-1.5">
                                            <button onClick={() => setPreviewMode('chart')}
                                                className={`text-[10px] font-bold px-2 py-0.5 rounded transition-all ${previewMode === 'chart' ? 'bg-cyan-500/15 text-cyan-300' : 'text-slate-500 hover:text-slate-300'}`}>
                                                <BarChart3 className="h-3 w-3 inline mr-1" />Chart
                                            </button>
                                            <button onClick={() => setPreviewMode('table')}
                                                className={`text-[10px] font-bold px-2 py-0.5 rounded transition-all ${previewMode === 'table' ? 'bg-cyan-500/15 text-cyan-300' : 'text-slate-500 hover:text-slate-300'}`}>
                                                <Table2 className="h-3 w-3 inline mr-1" />Table
                                            </button>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <Button size="sm" onClick={handlePreview}
                                            disabled={queryPreview.isPending}
                                            className="bg-cyan-600 hover:bg-cyan-500 text-white h-7 text-xs gap-1.5">
                                            <Play className="h-3 w-3" /> {queryPreview.isPending ? 'Running...' : 'Run Query'}
                                        </Button>
                                        {previewData && (
                                            <span className="text-[10px] text-cyan-400">
                                                {previewData.data?.length || 0} rows · mode: {previewData.mode || 'standard'}
                                                {previewData.series && ` · ${previewData.series.length} series`}
                                            </span>
                                        )}
                                    </div>

                                    {/* Preview output */}
                                    {previewData?.data?.length > 0 && (
                                        <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-3">
                                            {previewMode === 'chart' ? (
                                                <PreviewChart data={previewData} chartType={form.widget_type} />
                                            ) : (
                                                <PreviewTable data={previewData} />
                                            )}
                                        </div>
                                    )}
                                    {previewData?.data?.length === 0 && (
                                        <p className="text-slate-500 text-xs italic text-center py-4">No data returned. Try different parameters.</p>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDialogOpen(false)}
                            className="border-slate-700 text-slate-300">Cancel</Button>
                        <Button onClick={handleSave}
                            disabled={!form.name || createWidget.isPending || updateWidget.isPending}
                            className="bg-primary hover:bg-primary/90 text-white">
                            {editingId ? 'Update' : 'Create'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// ══════════════════════════════════════════════════════════════════
//  PREVIEW CHART
// ══════════════════════════════════════════════════════════════════

function PreviewChart({ data, chartType }: { data: any; chartType: string }) {
    const mode = data.mode || 'standard';
    const series = data.series || [];
    const chartData = data.data || [];

    // Multi-series area/line chart
    if (mode === 'multi_series') {
        return (
            <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="date" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }}
                        tickFormatter={v => {
                            if (!v) return '';
                            const d = new Date(v);
                            return `${d.getMonth()+1}/${d.getDate()}`;
                        }} />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} allowDecimals={false} />
                    <Tooltip {...TOOLTIP_STYLE}
                        labelFormatter={v => v ? new Date(v).toLocaleDateString() : ''} />
                    <Legend
                        verticalAlign="bottom" iconType="circle" iconSize={8}
                        wrapperStyle={{ fontSize: '10px', paddingTop: '4px' }}
                        formatter={(value: string) => <span className="text-slate-300 text-[10px]">{value}</span>}
                    />
                    {series.map((s: string, i: number) => (
                        <Area
                            key={s}
                            type="monotone"
                            dataKey={s}
                            stroke={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                            fill={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                            fillOpacity={0.1}
                            strokeWidth={2}
                            dot={false}
                        />
                    ))}
                </AreaChart>
            </ResponsiveContainer>
        );
    }

    // Single time-series
    if (mode === 'time_series') {
        return (
            <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                    <defs>
                        <linearGradient id="prevGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="date" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }}
                        tickFormatter={v => {
                            if (!v) return '';
                            const d = new Date(v);
                            return `${d.getMonth()+1}/${d.getDate()}`;
                        }} />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} allowDecimals={false} />
                    <Tooltip {...TOOLTIP_STYLE}
                        labelFormatter={v => v ? new Date(v).toLocaleDateString() : ''} />
                    <Area type="monotone" dataKey="value" stroke="#818cf8" strokeWidth={2}
                        fill="url(#prevGrad)" dot={{ fill: '#818cf8', r: 2 }} />
                </AreaChart>
            </ResponsiveContainer>
        );
    }

    // Standard: bar or pie
    if (chartType === 'pie_chart') {
        return (
            <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                    <Pie data={chartData} cx="50%" cy="50%" innerRadius="30%" outerRadius="65%"
                        dataKey="value" nameKey="label" paddingAngle={2}>
                        {chartData.map((_: any, i: number) => (
                            <Cell key={i} fill={ACCENT_COLORS[i % ACCENT_COLORS.length]} />
                        ))}
                    </Pie>
                    <Tooltip {...TOOLTIP_STYLE} />
                    <Legend verticalAlign="bottom" iconType="circle" iconSize={8}
                        wrapperStyle={{ fontSize: '10px', paddingTop: '4px' }}
                        formatter={(value: string) => <span className="text-slate-300 text-[10px]">{value}</span>}
                    />
                </PieChart>
            </ResponsiveContainer>
        );
    }

    // Default: bar chart
    return (
        <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="label" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {chartData.map((_: any, i: number) => (
                        <Cell key={i} fill={ACCENT_COLORS[i % ACCENT_COLORS.length]} />
                    ))}
                </Bar>
            </BarChart>
        </ResponsiveContainer>
    );
}

// ══════════════════════════════════════════════════════════════════
//  PREVIEW DATA TABLE
// ══════════════════════════════════════════════════════════════════

function PreviewTable({ data }: { data: any }) {
    const rows = data.data || [];
    if (rows.length === 0) return null;
    const keys = Object.keys(rows[0]);

    return (
        <div className="overflow-x-auto max-h-[200px] overflow-y-auto custom-scrollbar">
            <table className="w-full text-xs">
                <thead>
                    <tr className="border-b border-slate-700">
                        {keys.map(k => (
                            <th key={k} className="text-left text-[10px] text-slate-400 font-bold uppercase tracking-wider py-1.5 px-2">{k}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.slice(0, 50).map((row: any, i: number) => (
                        <tr key={i} className="border-b border-slate-800/30 hover:bg-slate-800/20">
                            {keys.map(k => (
                                <td key={k} className="text-slate-300 py-1 px-2 font-mono text-[11px]">
                                    {typeof row[k] === 'number' ? row[k].toLocaleString() : String(row[k] ?? '')}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
