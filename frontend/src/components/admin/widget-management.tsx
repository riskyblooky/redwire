'use client';

/**
 * Admin Widget Management — CRUD for widget definitions.
 * Advanced step-by-step query builder with date-range filtering,
 * time-series bucketing, multi-series support, and live preview.
 */

import { useState, useMemo, useEffect } from 'react';
import {
    useDashboardWidgets, useCreateWidget, useUpdateWidget, useDeleteWidget,
    useQueryPreview, useQueryPreviewMulti, useQuerySchema, useComputedMetrics,
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
    // Post-P5 additions — 2D heatmap from multi-column group_by
    // (severity × status etc.) and scatter for correlation widgets that
    // consume multi-query results.
    { value: 'heatmap', label: 'Heatmap (2D)', Icon: BarChart3 },
    { value: 'scatter', label: 'Scatter / Correlation', Icon: TrendingUp },
    // Post-P3 composite widget flavors — all consume config.queries
    // (up to 6 sub-queries).
    { value: 'ratio', label: 'Ratio (A ÷ B)', Icon: Zap },
    { value: 'percentage', label: 'Percentage (A / B × 100)', Icon: Zap },
    { value: 'delta', label: 'Delta (period vs previous)', Icon: TrendingUp },
    { value: 'overlay', label: 'Overlay time-series', Icon: TrendingUp },
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
    { value: 'count_distinct', label: 'Count (distinct)' },
    { value: 'avg', label: 'Average' },
    { value: 'sum', label: 'Sum' },
    { value: 'max', label: 'Maximum' },
    { value: 'min', label: 'Minimum' },
    { value: 'median', label: 'Median (P50)' },
    { value: 'p95', label: 'P95' },
    { value: 'p99', label: 'P99' },
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

interface FilterDef {
    column: string;
    operator: string;
    value: string;
}

/** One sub-query — the shape backed by config.query (single-query
 *  widgets) or an element of config.queries (composite widgets). */
interface QueryDef {
    table: string;
    group_by: string;
    aggregation: string;
    value_column: string;
    limit: number;
    date_column: string;
    date_range: string;
    time_bucket: string;
    series_by: string;
    filters: FilterDef[];
}

interface FormState {
    name: string;
    description: string;
    widget_type: string;
    data_source: string;
    size: string;
    category: string;
    icon: string;
    // Ordered list of sub-queries. Non-composite widgets always have
    // length 1 and land as config.query; composite types (scatter,
    // ratio, percentage, delta, overlay) land as config.queries.
    queries: QueryDef[];
    // Optional series labels for overlay widgets — same length as queries
    // when supplied. Used by OverlayWidget's legend.
    series_labels: string[];
}

/** Composite widget types consume config.queries (multiple sub-queries)
 *  and render via per-widget flavors on the dashboard. */
const COMPOSITE_TYPES = ['scatter', 'ratio', 'percentage', 'delta', 'overlay'];
const isCompositeType = (t: string) => COMPOSITE_TYPES.includes(t);

/** How many sub-queries each composite type needs. Values are [min, max].
 *  Non-composite = [1, 1]. */
function queryCountRange(widget_type: string): [number, number] {
    switch (widget_type) {
        case 'ratio':
        case 'percentage':
        case 'delta':
        case 'scatter':
            return [2, 2];
        case 'overlay':
            return [2, 6];
        default:
            return [1, 1];
    }
}

const EMPTY_QUERY: QueryDef = {
    table: 'findings', group_by: 'severity', aggregation: 'count',
    value_column: 'id', limit: 50,
    date_column: '', date_range: '30d', time_bucket: '',
    series_by: '', filters: [],
};

const EMPTY_FORM: FormState = {
    name: '', description: '', widget_type: 'bar_chart',
    data_source: 'severity_distribution', size: 'medium', category: 'custom', icon: 'BarChart3',
    queries: [{ ...EMPTY_QUERY }],
    series_labels: [],
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
    const queryPreviewMulti = useQueryPreviewMulti();
    const { data: schema } = useQuerySchema();
    const { data: metricsData } = useComputedMetrics();

    // Friendly label for a column: custom fields ("cf:key") show their admin
    // label with a "(custom)" hint; real columns show as-is.
    const colLabel = (c: string) => {
        const cf = schema?.custom_field_labels?.[c];
        return cf ? `${cf} (custom)` : c;
    };

    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [form, setForm] = useState<FormState>(EMPTY_FORM);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [previewData, setPreviewData] = useState<any>(null);
    const [previewMode, setPreviewMode] = useState<'chart' | 'table'>('chart');
    const [builderStep, setBuilderStep] = useState(0); // 0=source 1=metrics 2=filters 3=viz 4=preview
    // Which sub-query the wizard's fields target. Reset on dialog open /
    // widget-type change so the user isn't editing a deleted sub-query.
    const [activeQueryIdx, setActiveQueryIdx] = useState(0);

    // Convenience: pull the currently active sub-query and a setter that
    // patches just that slot so component code doesn't need to spread the
    // whole queries array every time.
    const activeQuery = form.queries[activeQueryIdx] ?? form.queries[0];
    const updateActiveQuery = (patch: Partial<QueryDef>) => {
        setForm(f => {
            const next = [...f.queries];
            next[activeQueryIdx] = { ...next[activeQueryIdx], ...patch };
            return { ...f, queries: next };
        });
        setPreviewData(null);
    };

    /** Reshape a widget's stored config into the flat FormState.queries
     *  array. Handles both single-query (config.query) and composite
     *  (config.queries) shapes so an existing widget of either flavor
     *  opens correctly. Fields missing on the stored config are
     *  back-filled from EMPTY_QUERY. */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const normalizeConfigToQueries = (config: any): QueryDef[] => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const asDef = (raw: any): QueryDef => ({
            ...EMPTY_QUERY,
            ...raw,
            // group_by can be a string or list on the wire; the wizard
            // only edits single-column groups today, so collapse a list
            // back to the first entry. Multi-col group-by editing is
            // still supported by editing config.query directly.
            group_by: Array.isArray(raw?.group_by) ? raw.group_by[0] : (raw?.group_by ?? EMPTY_QUERY.group_by),
            filters: raw?.filters ?? [],
        });
        if (Array.isArray(config?.queries) && config.queries.length > 0) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return config.queries.map((q: any) => asDef(q));
        }
        if (config?.query) return [asDef(config.query)];
        return [{ ...EMPTY_QUERY }];
    };

    const openCreate = () => {
        setEditingId(null);
        setForm(EMPTY_FORM);
        setActiveQueryIdx(0);
        setPreviewData(null);
        setBuilderStep(0);
        setDialogOpen(true);
    };

    const openEdit = (w: DashboardWidgetDef) => {
        const queries = normalizeConfigToQueries(w.config);
        setEditingId(w.id);
        setForm({
            name: w.name,
            description: w.description || '',
            widget_type: w.widget_type,
            data_source: w.data_source,
            size: w.size,
            category: w.category,
            icon: w.icon || 'BarChart3',
            queries,
            series_labels: w.config?.series_labels || [],
        });
        setActiveQueryIdx(0);
        setPreviewData(null);
        setBuilderStep(0);
        setDialogOpen(true);
    };

    /** Trim / extend the queries array so its length is within the
     *  widget-type's constraint. Called whenever widget_type changes. */
    const enforceQueryCount = (widget_type: string) => {
        const [min] = queryCountRange(widget_type);
        setForm(f => {
            let queries = f.queries;
            while (queries.length < min) queries = [...queries, { ...EMPTY_QUERY }];
            return { ...f, queries };
        });
        setActiveQueryIdx(0);
    };

    /** Build a QueryDefinition (backend wire shape) from a QueryDef
     *  form entry. Drops empty-string fields so the payload matches
     *  what the backend expects (e.g. no ``date_range`` when
     *  ``date_column`` isn't set). */
    const queryDefForWire = (q: QueryDef): QueryDefinition => {
        const wire: QueryDefinition = {
            table: q.table,
            group_by: q.group_by,
            aggregation: q.aggregation,
            value_column: q.value_column,
            limit: q.limit,
        };
        if (q.date_column) {
            wire.date_column = q.date_column;
            wire.date_range = q.date_range;
        }
        if (q.time_bucket) {
            wire.time_bucket = q.time_bucket;
            if (!wire.date_column) {
                const tSchema = schema?.schema?.[q.table];
                if (tSchema?.date_columns?.[0]) {
                    wire.date_column = tSchema.date_columns[0];
                    wire.date_range = q.date_range || '30d';
                }
            }
        }
        if (q.series_by) wire.series_by = q.series_by;
        if (q.filters.length > 0) wire.filters = q.filters;
        return wire;
    };

    const handlePreview = async () => {
        try {
            if (isCompositeType(form.widget_type) && form.queries.length > 1) {
                const wires = form.queries.map(queryDefForWire);
                const result = await queryPreviewMulti.mutateAsync({ queries: wires });
                setPreviewData(result);   // { results: [...] }
            } else {
                const wire = queryDefForWire(activeQuery);
                const result = await queryPreview.mutateAsync(wire);
                setPreviewData(result);
            }
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } catch (err: any) {
            toast.error(apiErrorMessage(err, 'Query failed'));
        }
    };

    const handleSave = async () => {
        try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const config: any = {};
            if (form.data_source === 'custom_query') {
                if (isCompositeType(form.widget_type) && form.queries.length > 1) {
                    // Composite widget — write config.queries and optional
                    // series_labels for overlay widgets.
                    config.queries = form.queries.map(queryDefForWire);
                    if (form.widget_type === 'overlay' && form.series_labels.length > 0) {
                        config.series_labels = form.series_labels;
                    }
                } else {
                    config.query = queryDefForWire(form.queries[0]);
                }
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
        updateActiveQuery({
            table,
            group_by: tSchema?.group_by[0] || '',
            value_column: tSchema?.aggregate[0] || 'id',
            date_column: '',
            time_bucket: '',
            series_by: '',
            filters: [],
        });
    };

    // Current sub-query's table schema
    const tSchema = schema?.schema?.[activeQuery.table];

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
                                <Select value={form.widget_type} onValueChange={v => {
                                    setForm(f => ({ ...f, widget_type: v }));
                                    enforceQueryCount(v);
                                    setPreviewData(null);
                                }}>
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

                                {/* ── Sub-query tabs — composite widgets only ── */}
                                {isCompositeType(form.widget_type) && (() => {
                                    const [min, max] = queryCountRange(form.widget_type);
                                    return (
                                        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2 space-y-1.5">
                                            <div className="flex items-center gap-1.5 text-[10px] text-cyan-300 font-semibold uppercase tracking-wider">
                                                <Layers className="h-3 w-3" />
                                                <span>Sub-queries — this widget composes {min === max ? min : `${min}–${max}`}</span>
                                                <span className="ml-auto text-cyan-500/60 text-[9px] font-normal normal-case tracking-normal">
                                                    Configure each sub-query below via its tab.
                                                </span>
                                            </div>
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                                {form.queries.map((_, i) => (
                                                    <button
                                                        key={i}
                                                        onClick={() => { setActiveQueryIdx(i); setPreviewData(null); }}
                                                        className={`px-2.5 py-1 rounded text-[10px] font-bold transition-all border ${
                                                            activeQueryIdx === i
                                                                ? 'bg-cyan-500/25 text-cyan-200 border-cyan-500/40'
                                                                : 'bg-slate-900/50 text-slate-400 border-slate-700/50 hover:border-cyan-500/30 hover:text-cyan-300'
                                                        }`}
                                                    >
                                                        Query {i + 1}
                                                        {form.widget_type === 'delta' && i === 0 && ' (current)'}
                                                        {form.widget_type === 'delta' && i === 1 && ' (previous)'}
                                                        {form.widget_type === 'ratio' && i === 0 && ' (numerator)'}
                                                        {form.widget_type === 'ratio' && i === 1 && ' (denominator)'}
                                                        {form.widget_type === 'percentage' && i === 0 && ' (part)'}
                                                        {form.widget_type === 'percentage' && i === 1 && ' (whole)'}
                                                        {form.widget_type === 'scatter' && i === 0 && ' (x)'}
                                                        {form.widget_type === 'scatter' && i === 1 && ' (y)'}
                                                        {form.queries.length > min && (
                                                            <span
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setForm(f => ({ ...f, queries: f.queries.filter((_, j) => j !== i) }));
                                                                    if (activeQueryIdx >= form.queries.length - 1) setActiveQueryIdx(Math.max(0, form.queries.length - 2));
                                                                    setPreviewData(null);
                                                                }}
                                                                className="ml-1.5 text-red-400/70 hover:text-red-400 cursor-pointer"
                                                                role="button"
                                                                aria-label={`Remove query ${i + 1}`}
                                                            >×</span>
                                                        )}
                                                    </button>
                                                ))}
                                                {form.queries.length < max && (
                                                    <button
                                                        onClick={() => {
                                                            setForm(f => ({ ...f, queries: [...f.queries, { ...EMPTY_QUERY }] }));
                                                            setActiveQueryIdx(form.queries.length);
                                                            setPreviewData(null);
                                                        }}
                                                        className="px-2.5 py-1 rounded text-[10px] font-bold transition-all border border-dashed border-cyan-500/40 bg-cyan-500/5 text-cyan-400 hover:bg-cyan-500/15"
                                                    >
                                                        <Plus className="h-2.5 w-2.5 inline mr-0.5" />
                                                        Add sub-query
                                                    </button>
                                                )}
                                            </div>
                                            {form.widget_type === 'overlay' && (
                                                <div className="pt-1.5 border-t border-cyan-500/10">
                                                    <Label className="text-[9px] text-cyan-500/70 uppercase tracking-wider">Series label (for legend)</Label>
                                                    <Input
                                                        value={form.series_labels[activeQueryIdx] ?? ''}
                                                        onChange={e => {
                                                            const next = [...form.series_labels];
                                                            next[activeQueryIdx] = e.target.value;
                                                            setForm(f => ({ ...f, series_labels: next }));
                                                        }}
                                                        placeholder={`Series ${activeQueryIdx + 1}`}
                                                        className="bg-slate-900 border-slate-700 text-white h-7 text-xs mt-1"
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    );
                                })()}

                                {/* ── Step 1: Data Source Table ── */}
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="w-5 h-5 rounded-full bg-cyan-500/20 text-cyan-400 text-[10px] font-bold flex items-center justify-center shrink-0">1</span>
                                        <span className="text-xs font-bold text-slate-200">Data Source</span>
                                    </div>
                                    <div className="flex gap-2 flex-wrap">
                                        {schema?.tables?.map(t => {
                                            const TIcon = TABLE_ICONS[t] || Database;
                                            const isActive = activeQuery.table === t;
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
                                            <Select value={activeQuery.group_by} onValueChange={v => { updateActiveQuery({ group_by: v }); setPreviewData(null); }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.group_by.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{colLabel(c)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Aggregation</Label>
                                            <Select value={activeQuery.aggregation} onValueChange={v => { updateActiveQuery({ aggregation: v }); setPreviewData(null); }}>
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
                                            <Select value={activeQuery.value_column} onValueChange={v => { updateActiveQuery({ value_column: v }); setPreviewData(null); }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.aggregate.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{colLabel(c)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-slate-400 text-[10px]">Limit</Label>
                                            <Input type="number" value={activeQuery.limit} min={1} max={500}
                                                onChange={e => updateActiveQuery({ limit: parseInt(e.target.value) || 50 })}
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
                                                    <Select value={activeQuery.date_column || '__none__'} onValueChange={v => { updateActiveQuery({ date_column: v === '__none__' ? '' : v }); setPreviewData(null); }}>
                                                        <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent className="bg-slate-950 border-slate-800">
                                                            <SelectItem value="__none__" className="text-slate-400 focus:bg-slate-800 focus:text-white text-xs">No date filter</SelectItem>
                                                            {tSchema.date_columns.map(c => (
                                                                <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{colLabel(c)}</SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                {activeQuery.date_column && (
                                                    <div className="space-y-1">
                                                        <Label className="text-slate-400 text-[10px]">Time Bucket</Label>
                                                        <Select value={activeQuery.time_bucket || '__none__'} onValueChange={v => { updateActiveQuery({ time_bucket: v === '__none__' ? '' : v }); setPreviewData(null); }}>
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
                                            {activeQuery.date_column && (
                                                <div className="flex gap-1.5 flex-wrap">
                                                    {DATE_RANGE_OPTIONS.map(dr => (
                                                        <button key={dr.value}
                                                            onClick={() => { updateActiveQuery({ date_range: dr.value }); setPreviewData(null); }}
                                                            className={`text-[10px] font-bold px-2.5 py-1 rounded-full transition-all border
                                                                ${activeQuery.date_range === dr.value
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
                                                        <Select value={activeQuery.series_by || '__none__'} onValueChange={v => { updateActiveQuery({ series_by: v === '__none__' ? '' : v }); setPreviewData(null); }}>
                                                            <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-8 text-xs">
                                                                <SelectValue />
                                                            </SelectTrigger>
                                                            <SelectContent className="bg-slate-950 border-slate-800">
                                                                <SelectItem value="__none__" className="text-slate-400 focus:bg-slate-800 focus:text-white text-xs">No split (single series)</SelectItem>
                                                                {tSchema.series_by.map(c => (
                                                                    <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{colLabel(c)}</SelectItem>
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
                                        <button onClick={() => updateActiveQuery({ filters: [...activeQuery.filters, { column: tSchema.filter_columns[0] || '', operator: 'eq', value: '' }] })}
                                            className="ml-auto text-[10px] text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1">
                                            <Plus className="h-3 w-3" /> Add Filter
                                        </button>
                                    </div>
                                    {activeQuery.filters.length === 0 && (
                                        <p className="text-slate-600 text-[10px] italic">No filters applied — showing all data.</p>
                                    )}
                                    {activeQuery.filters.map((filter, idx) => (
                                        <div key={idx} className="flex items-center gap-2">
                                            <Select value={filter.column} onValueChange={v => {
                                                const filters = [...activeQuery.filters];
                                                filters[idx] = { ...filters[idx], column: v };
                                                updateActiveQuery({ filters });
                                                setPreviewData(null);
                                            }}>
                                                <SelectTrigger className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] w-32">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent className="bg-slate-950 border-slate-800">
                                                    {tSchema.filter_columns.map(c => (
                                                        <SelectItem key={c} value={c} className="text-slate-200 focus:bg-slate-800 focus:text-white text-xs">{colLabel(c)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Select value={filter.operator} onValueChange={v => {
                                                const filters = [...activeQuery.filters];
                                                filters[idx] = { ...filters[idx], operator: v };
                                                updateActiveQuery({ filters });
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
                                                    const filters = [...activeQuery.filters];
                                                    filters[idx] = { ...filters[idx], value: e.target.value };
                                                    updateActiveQuery({ filters });
                                                    setPreviewData(null);
                                                }}
                                                className="bg-slate-900 border-slate-700 text-white h-7 text-[11px] flex-1" />
                                            <button onClick={() => {
                                                updateActiveQuery({ filters: activeQuery.filters.filter((_, i) => i !== idx) });
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
                                            disabled={queryPreview.isPending || queryPreviewMulti.isPending}
                                            className="bg-cyan-600 hover:bg-cyan-500 text-white h-7 text-xs gap-1.5">
                                            <Play className="h-3 w-3" />
                                            {queryPreview.isPending || queryPreviewMulti.isPending
                                                ? 'Running...'
                                                : (isCompositeType(form.widget_type) && form.queries.length > 1
                                                    ? `Run ${form.queries.length} queries`
                                                    : 'Run Query')}
                                        </Button>
                                        {previewData && (
                                            <span className="text-[10px] text-cyan-400">
                                                {previewData.results
                                                    ? `${previewData.results.length} sub-queries · ${previewData.results.reduce((s: number, r: { data?: unknown[] }) => s + (r.data?.length || 0), 0)} total rows`
                                                    : `${previewData.data?.length || 0} rows · mode: ${previewData.mode || 'standard'}${previewData.series ? ` · ${previewData.series.length} series` : ''}`}
                                            </span>
                                        )}
                                    </div>

                                    {/* Preview output */}
                                    {previewData?.results && Array.isArray(previewData.results) && (
                                        <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-3">
                                            <CompositePreview
                                                data={previewData}
                                                chartType={form.widget_type}
                                                seriesLabels={form.series_labels}
                                            />
                                        </div>
                                    )}
                                    {previewData?.data?.length > 0 && (
                                        <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-3">
                                            {previewMode === 'chart' ? (
                                                <PreviewChart data={previewData} chartType={form.widget_type} />
                                            ) : (
                                                <PreviewTable data={previewData} />
                                            )}
                                        </div>
                                    )}
                                    {previewData && !previewData.results && previewData?.data?.length === 0 && (
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

    // Composite widget types can't preview from a single query — the
    // builder wizard only produces one query, but these consume N.
    // Surface an actionable message instead of silently falling back
    // to a bar chart that misrepresents what the widget will render.
    const COMPOSITE_TYPES = ['scatter', 'ratio', 'percentage', 'delta', 'overlay'];
    if (COMPOSITE_TYPES.includes(chartType)) {
        return (
            <div className="rounded-lg border border-dashed border-cyan-500/30 bg-cyan-500/5 p-4 text-center">
                <p className="text-xs text-cyan-300 font-medium">
                    {chartType} widgets need multiple sub-queries.
                </p>
                <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">
                    The builder wizard only produces one query at a time. Set up the
                    widget's <code className="text-cyan-400">config.queries</code> array
                    directly on save, or duplicate an example widget of this type and
                    edit its sub-queries.
                </p>
                <p className="text-[10px] text-slate-500 mt-2">
                    Preview shows the single-query result below as a stand-in:
                </p>
                <div className="mt-2 opacity-60">
                    <ResponsiveContainer width="100%" height={140}>
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="label" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                            <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                            <Tooltip {...TOOLTIP_STYLE} />
                            <Bar dataKey="value" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        );
    }

    // 2D heatmap — needs multi-column group_by (rows carry `labels[]`).
    if (chartType === 'heatmap') {
        const isMulti = chartData[0] && Array.isArray(chartData[0].labels) && chartData[0].labels.length >= 2;
        if (!isMulti) {
            return (
                <p className="text-slate-500 text-xs italic text-center py-4">
                    Heatmap needs a 2-column group-by. Add a second column at Step 2 (Group).
                </p>
            );
        }
        const xVals = Array.from(new Set(chartData.map((c: any) => c.labels[0])));
        const yVals = Array.from(new Set(chartData.map((c: any) => c.labels[1])));
        const grid: Record<string, number> = {};
        let maxVal = 0;
        for (const c of chartData) {
            grid[`${c.labels[0]}||${c.labels[1]}`] = c.value;
            if (c.value > maxVal) maxVal = c.value;
        }
        return (
            <div className="overflow-x-auto max-w-full">
                <table className="w-full text-[10px] border-collapse">
                    <thead>
                        <tr>
                            <th />
                            {xVals.map(x => (<th key={String(x)} className="p-1 text-slate-400 text-center">{String(x)}</th>))}
                        </tr>
                    </thead>
                    <tbody>
                        {yVals.map(y => (
                            <tr key={String(y)}>
                                <td className="p-1 text-slate-400 font-medium whitespace-nowrap pr-2">{String(y)}</td>
                                {xVals.map(x => {
                                    const v = grid[`${x}||${y}`] || 0;
                                    const alpha = maxVal === 0 ? 0 : v / maxVal;
                                    return (
                                        <td key={String(x)}
                                            className="p-1 text-center text-white font-mono rounded"
                                            style={{ backgroundColor: `rgba(139, 92, 246, ${0.15 + alpha * 0.75})` }}
                                        >{v || ''}</td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        );
    }

    // Stat card / gauge — the query almost always returns a group-by, so
    // collapse it: show the total on top, breakdown mini-bars below.
    if (chartType === 'stat_card' || chartType === 'gauge') {
        const total = chartData.reduce((s: number, r: any) => s + (r.value || 0), 0);
        return (
            <div className="text-center py-4">
                <div className="text-4xl font-bold text-white">
                    {total >= 1_000_000 ? `${(total / 1_000_000).toFixed(1)}M`
                        : total >= 1_000 ? `${(total / 1_000).toFixed(1)}k`
                            : total.toLocaleString()}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">
                    total across {chartData.length} group{chartData.length === 1 ? '' : 's'}
                </div>
            </div>
        );
    }

    // Area chart — standard mode fills a trend line under the values.
    if (chartType === 'area_chart') {
        return (
            <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                    <defs>
                        <linearGradient id="stdAreaGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#818cf8" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="label" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                    <Tooltip {...TOOLTIP_STYLE} />
                    <Area type="monotone" dataKey="value" stroke="#818cf8" strokeWidth={2}
                        fill="url(#stdAreaGrad)" dot={{ fill: '#818cf8', r: 2 }} />
                </AreaChart>
            </ResponsiveContainer>
        );
    }

    // Pie
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

    // Default: bar / stacked-bar (stacked mode requires multi_series data,
    // which falls through to the mode==='multi_series' branch above).
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


// ══════════════════════════════════════════════════════════════════
//  COMPOSITE PREVIEW — scatter / ratio / percentage / delta / overlay
// ══════════════════════════════════════════════════════════════════

/** Pearson r for two parallel numeric arrays. */
function pearsonR(xs: number[], ys: number[]): number {
    const n = Math.min(xs.length, ys.length);
    if (n < 2) return 0;
    const mx = xs.slice(0, n).reduce((a, b) => a + b, 0) / n;
    const my = ys.slice(0, n).reduce((a, b) => a + b, 0) / n;
    let num = 0, dx = 0, dy = 0;
    for (let i = 0; i < n; i++) {
        const a = xs[i] - mx, b = ys[i] - my;
        num += a * b; dx += a * a; dy += b * b;
    }
    const denom = Math.sqrt(dx * dy);
    return denom === 0 ? 0 : num / denom;
}

function sumValues(rows: Array<{ value?: number }> | null | undefined): number {
    if (!rows) return 0;
    return rows.reduce((s, r) => s + (typeof r.value === 'number' ? r.value : 0), 0);
}

function formatBig(v: number): string {
    if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
    return v % 1 === 0 ? v.toString() : v.toFixed(1);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CompositePreview({ data, chartType, seriesLabels }: { data: any; chartType: string; seriesLabels: string[] }) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results: Array<{ data: any[]; mode?: string }> = data.results || [];
    if (results.length < 2) {
        return <p className="text-slate-500 text-xs italic text-center py-4">Composite widgets need at least 2 sub-queries.</p>;
    }

    // Ratio / Percentage — sum both sides.
    if (chartType === 'ratio' || chartType === 'percentage') {
        const a = sumValues(results[0].data);
        const b = sumValues(results[1].data);
        let display = '—';
        if (b !== 0) {
            const v = chartType === 'ratio' ? a / b : (a / b) * 100;
            display = chartType === 'ratio' ? v.toFixed(2) : `${v.toFixed(1)}%`;
        }
        return (
            <div className="text-center py-4">
                <div className="text-4xl font-bold text-white">{display}</div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-2">
                    {formatBig(a)} of {formatBig(b)}
                </div>
            </div>
        );
    }

    // Delta — sum both, show current + % change.
    if (chartType === 'delta') {
        const curr = sumValues(results[0].data);
        const prev = sumValues(results[1].data);
        const delta = prev === 0 ? null : ((curr - prev) / prev) * 100;
        const arrow = delta === null ? '' : delta > 0 ? '▲' : delta < 0 ? '▼' : '=';
        const color = delta === null ? 'text-slate-500' : delta > 0 ? 'text-red-400' : 'text-green-400';
        return (
            <div className="text-center py-4">
                <div className="text-4xl font-bold text-white">{formatBig(curr)}</div>
                <div className={`mt-2 text-sm font-semibold ${color}`}>
                    {arrow} {delta === null ? 'no baseline' : `${Math.abs(delta).toFixed(1)}%`}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">
                    vs previous ({formatBig(prev)})
                </div>
            </div>
        );
    }

    // Scatter — join queries on primary label, plot (x, y). Show Pearson r.
    if (chartType === 'scatter') {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const A: any[] = results[0].data || [];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const B: any[] = results[1].data || [];
        const byLabel = new Map<string, { x?: number; y?: number }>();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        for (const r of A) byLabel.set(r.label, { ...(byLabel.get(r.label) || {}), x: r.value });
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        for (const r of B) byLabel.set(r.label, { ...(byLabel.get(r.label) || {}), y: r.value });
        const points = Array.from(byLabel.entries())
            .filter(([, v]) => v.x !== undefined && v.y !== undefined)
            .map(([label, v]) => ({ label, x: v.x!, y: v.y! }));
        const r = pearsonR(points.map(p => p.x), points.map(p => p.y));
        return (
            <>
                <ResponsiveContainer width="100%" height={200}>
                    <RLineChart data={points}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis type="number" dataKey="x" name="A" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                        <YAxis type="number" dataKey="y" name="B" stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                        <Tooltip {...TOOLTIP_STYLE} />
                        <Line
                            type="linear" dataKey="y" stroke="none"
                            dot={{ r: 4, fill: '#8b5cf6' }} activeDot={{ r: 6 }}
                            isAnimationActive={false}
                        />
                    </RLineChart>
                </ResponsiveContainer>
                <div className="text-center mt-1 text-[11px] text-slate-400">
                    Pearson r = <span className={r > 0.3 ? 'text-green-400 font-semibold' : r < -0.3 ? 'text-red-400 font-semibold' : 'text-slate-400'}>{r.toFixed(3)}</span>
                    <span className="ml-2 text-slate-600">({points.length} points)</span>
                </div>
            </>
        );
    }

    // Overlay — merge time-series on `date` key, one line per sub-query.
    if (chartType === 'overlay') {
        const dateMap: Record<string, Record<string, number | string>> = {};
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        results.forEach((r: { data?: any[] }, i: number) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (r.data || []).forEach((row: any) => {
                const d = row.date;
                if (!d) return;
                if (!dateMap[d]) dateMap[d] = { date: d };
                dateMap[d][`s${i}`] = row.value || 0;
            });
        });
        const merged = Object.values(dateMap).sort((a, b) => String(a.date).localeCompare(String(b.date)));
        return (
            <ResponsiveContainer width="100%" height={200}>
                <RLineChart data={merged}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                        dataKey="date"
                        tickFormatter={(v: string) => v ? new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
                        stroke="#94a3b8"
                        tick={{ fill: '#94a3b8', fontSize: 9 }}
                    />
                    <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                    <Tooltip {...TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    {results.map((_, i) => (
                        <Line
                            key={i}
                            type="monotone"
                            dataKey={`s${i}`}
                            name={seriesLabels[i] || `Series ${i + 1}`}
                            stroke={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                            strokeWidth={2}
                            dot={false}
                        />
                    ))}
                </RLineChart>
            </ResponsiveContainer>
        );
    }

    return (
        <p className="text-slate-500 text-xs italic text-center py-4">
            No composite renderer for &quot;{chartType}&quot;.
        </p>
    );
}
