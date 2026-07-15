import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────

export interface DashboardWidgetDef {
    id: string;
    name: string;
    description?: string;
    widget_type:
        | 'stat_card' | 'bar_chart' | 'pie_chart' | 'area_chart' | 'stacked_bar'
        | 'gauge' | 'table' | 'list'
        | 'heatmap' | 'scatter' | 'ratio' | 'percentage' | 'delta' | 'overlay';
    data_source: string;
    size: 'small' | 'medium' | 'large' | 'wide' | 'full';
    category: 'overview' | 'findings' | 'engagements' | 'operators' | 'clients' | 'custom';
    icon?: string;
    config: Record<string, any>;
    is_system: boolean;
    is_active: boolean;
}

export interface LayoutItem {
    widget_id: string;
    x: number;
    y: number;
    w: number;
    h: number;
}

export interface QueryDefinition {
    table: string;
    group_by: string;
    aggregation: string;
    value_column: string;
    filters?: Array<{ column: string; operator: string; value: string }>;
    limit?: number;
    // Advanced
    date_column?: string;
    date_range?: string;
    date_start?: string;
    date_end?: string;
    time_bucket?: string;
    series_by?: string;
    join_tables?: string[];
}

export interface QuerySchemaTable {
    group_by: string[];
    aggregate: string[];
    date_columns: string[];
    filter_columns: string[];
    series_by: string[];
    joins: string[];
}

export interface QuerySchema {
    tables: string[];
    schema: Record<string, QuerySchemaTable>;
    aggregations: string[];
    filter_operators: string[];
    date_ranges: string[];
    time_buckets: string[];
}

export interface ComputedMetric {
    key: string;
    label: string;
    value: number;
    icon: string;
    format: 'number' | 'percent' | 'score';
}

// ── Hooks: Widget Definitions ──────────────────────────────────────

export function useDashboardWidgets() {
    return useQuery<DashboardWidgetDef[]>({
        queryKey: ['dashboard', 'widgets'],
        queryFn: async () => {
            const { data } = await api.get('/dashboard/widgets');
            return data;
        },
    });
}

export function useCreateWidget() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (widget: Partial<DashboardWidgetDef>) => {
            const { data } = await api.post('/dashboard/widgets', widget);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', 'widgets'] }),
    });
}

export function useUpdateWidget() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, ...updates }: { id: string } & Partial<DashboardWidgetDef>) => {
            const { data } = await api.put(`/dashboard/widgets/${id}`, updates);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', 'widgets'] }),
    });
}

export function useDeleteWidget() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (id: string) => {
            const { data } = await api.delete(`/dashboard/widgets/${id}`);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', 'widgets'] }),
    });
}

// ── Hooks: User Layout ─────────────────────────────────────────────

export function useDashboardLayout() {
    return useQuery<{ layout: LayoutItem[]; is_default: boolean }>({
        queryKey: ['dashboard', 'layout'],
        queryFn: async () => {
            const { data } = await api.get('/dashboard/layout');
            return data;
        },
    });
}

export function useSaveLayout() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (layout: LayoutItem[]) => {
            const { data } = await api.put('/dashboard/layout', { layout });
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', 'layout'] }),
    });
}

export function useResetLayout() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async () => {
            const { data } = await api.post('/dashboard/layout/reset');
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboard', 'layout'] }),
    });
}

// ── Custom Query Widget Data ───────────────────────────────────────

// Response shape:
//   single-query widget → { data: [...], mode?: 'standard' | 'time_series' | 'multi_series', series?: string[] }
//   composite widget    → { results: [{data, mode, ...}, ...], mode: 'composite' }
// `context` selects the backend scoping model: 'dashboard' (default)
// assignment-scopes non-admins; 'stats' honors the platform Stats Scope
// Mode for shared global stats pages. It's part of the query key so the
// same widget rendered in both places doesn't share a cache entry.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useCustomWidgetData(
    widgetId: string | undefined,
    context: 'dashboard' | 'stats' = 'dashboard',
) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return useQuery<any>({
        queryKey: ['dashboard', 'widget-data', widgetId, context],
        queryFn: async () => {
            const { data } = await api.get(`/dashboard/widgets/${widgetId}/data`, {
                params: context === 'stats' ? { context: 'stats' } : undefined,
            });
            return data;
        },
        enabled: !!widgetId,
        staleTime: 60_000,
    });
}

export function useQueryPreview() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return useMutation<{ data: any[]; series?: string[]; mode?: string }, Error, QueryDefinition>({
        mutationFn: async (queryDef) => {
            const { data } = await api.post('/dashboard/widgets/query-preview', queryDef);
            return data;
        },
    });
}

/** Preview N parallel sub-queries. Composite widgets (scatter, ratio,
 *  percentage, delta, overlay) use this to render preview data before
 *  saving. Server accepts up to 6 sub-queries per call. */
export function useQueryPreviewMulti() {
    return useMutation<
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        { results: Array<{ data: any[]; series?: string[]; mode?: string }> },
        Error,
        { queries: QueryDefinition[] }
    >({
        mutationFn: async (payload) => {
            const { data } = await api.post('/dashboard/widgets/query-preview-multi', payload);
            return data;
        },
    });
}

// ── Query Schema (for dynamic builder UI) ──────────────────────────

export function useQuerySchema() {
    return useQuery<QuerySchema>({
        queryKey: ['dashboard', 'query-schema'],
        queryFn: async () => {
            const { data } = await api.get('/dashboard/widgets/query-schema');
            return data;
        },
        staleTime: 300_000, // 5 min - schema doesn't change often
    });
}

// ── Computed Metrics ────────────────────────────────────────────────

export function useComputedMetrics() {
    return useQuery<{ metrics: ComputedMetric[] }>({
        queryKey: ['dashboard', 'computed-metrics'],
        queryFn: async () => {
            const { data } = await api.get('/dashboard/widgets/computed-metrics');
            return data;
        },
        staleTime: 120_000, // 2 min cache
    });
}
