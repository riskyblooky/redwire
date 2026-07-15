/**
 * dashboard/page.tsx — Dashboard Page
 *
 * Customisable widget-based dashboard with drag-and-drop grid editor.
 * Uses react-grid-layout for visual drag/resize in edit mode.
 * Layout is persisted per-user via the dashboard-widgets API. Features:
 *  - Drag-and-drop grid with snap-to-grid and resize handles
 *  - Edit mode toggle with visual feedback
 *  - Quick-action buttons for creating findings and assets
 *  - Real-time updates via WebSocket (activity_log events)
 */
'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useAuthStore } from '@/stores/auth-store';
import { useEngagementContext } from '@/stores/engagement-store';
import { useEngagements } from '@/lib/hooks/use-engagements';
import DashboardLayout from '@/components/layout/dashboard-layout';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Shield, Loader2, Zap, Bug, Server, Settings2, Plus, RotateCcw, Save, X,
    Move, Maximize2, Wifi,
} from 'lucide-react';
import { useDashboardStats } from '@/lib/hooks/use-analytics';
import { useCollaboration } from '@/lib/hooks/use-collaboration';
import { useQueryClient } from '@tanstack/react-query';
import {
    useDashboardWidgets, useDashboardLayout, useSaveLayout, useResetLayout,
    type DashboardWidgetDef, type LayoutItem,
} from '@/lib/hooks/use-dashboard-widgets';
import WidgetRenderer from '@/components/dashboard/widget-renderer';
import WidgetPicker from '@/components/dashboard/widget-picker';
import { RedWireSpinner } from '@/components/ui/redwire-spinner';
import { SIZE_SPANS, layoutToRGL, rglToLayout } from '@/lib/widget-layout';

// Load the grid component client-only (ssr:false) to avoid CJS/ESM issues
const DashboardGrid = dynamic(
    () => import('@/components/dashboard/dashboard-grid'),
    { ssr: false }
);

/* ── Quick Action ───────────────────────────────────────────────── */
function QuickAction({ icon: Icon, label, onClick, color }: { icon: any; label: string; onClick: () => void; color: string }) {
    const m: Record<string, { hover: string; icon: string; ring: string }> = {
        red: { hover: 'hover:border-red-500/40 hover:bg-red-500/5', icon: 'text-red-400 group-hover:text-red-300', ring: 'group-hover:ring-red-500/10' },
        cyan: { hover: 'hover:border-cyan-500/40 hover:bg-cyan-500/5', icon: 'text-cyan-400 group-hover:text-cyan-300', ring: 'group-hover:ring-cyan-500/10' },
    };
    const c = m[color] || m.cyan;
    return (
        <button onClick={onClick} className={`group flex items-center gap-2.5 rounded-lg border border-slate-800/80 bg-slate-900/30 px-4 py-2.5 transition-all duration-200 ${c.hover} ring-1 ring-transparent ${c.ring}`}>
            <Icon className={`h-4 w-4 ${c.icon} transition-colors`} />
            <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider group-hover:text-white transition-colors">{label}</span>
        </button>
    );
}

/* ══════════════ Dashboard Page ══════════════ */

export default function DashboardPage() {
    const router = useRouter();
    const { isAuthenticated, isLoading: isAuthLoading, user } = useAuthStore();
    const queryClient = useQueryClient();

    // Engagement scope
    const { selectedEngagementId } = useEngagementContext();
    const { data: engagements } = useEngagements();
    const engagementId = selectedEngagementId && selectedEngagementId !== 'global'
        ? selectedEngagementId : null;
    const scopedEngagementName = engagementId
        ? engagements?.find(e => e.id === engagementId)?.name
        : null;

    const { data: stats, isLoading: isStatsLoading } = useDashboardStats(engagementId);

    // Widget system
    const { data: widgets = [], isLoading: widgetsLoading } = useDashboardWidgets();
    const { data: layoutData, isLoading: layoutLoading } = useDashboardLayout();
    const saveLayout = useSaveLayout();
    const resetLayout = useResetLayout();

    // Edit mode state
    const [isEditing, setIsEditing] = useState(false);
    const [editLayout, setEditLayout] = useState<LayoutItem[]>([]);
    const [pickerOpen, setPickerOpen] = useState(false);

    // Use layout from server, or editing copy
    const currentLayout = isEditing ? editLayout : (layoutData?.layout || []);

    // Convert to RGL format
    const rglLayout = useMemo(
        () => layoutToRGL(currentLayout, widgets),
        [currentLayout, widgets]
    );

    useEffect(() => {
        if (!isAuthLoading && !isAuthenticated) router.push('/login');
    }, [isAuthenticated, isAuthLoading, router]);

    // ── Real-time WebSocket: invalidate ALL dashboard queries on activity ──
    const invalidateAll = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: ['analytics'] });
        queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['stats'] });
        queryClient.invalidateQueries({ queryKey: ['engagements'] });
        queryClient.invalidateQueries({ queryKey: ['findings'] });
    }, [queryClient]);

    // Subscribe to global dashboard channel (always)
    const { isConnected: wsGlobalConnected } = useCollaboration({
        resourceType: 'dashboard', resourceId: 'global',
        onMessage: (data) => {
            if (data.type === 'activity_log') invalidateAll();
        }
    });

    // Also subscribe to engagement-specific channel when scoped
    useCollaboration({
        resourceType: 'dashboard',
        resourceId: engagementId || '__none__',
        enabled: !!engagementId,
        onMessage: (data) => {
            if (data.type === 'activity_log') invalidateAll();
        }
    });

    const startEditing = useCallback(() => {
        setEditLayout(layoutData?.layout || []);
        setIsEditing(true);
    }, [layoutData]);

    const cancelEditing = useCallback(() => {
        setIsEditing(false);
        setEditLayout([]);
    }, []);

    const handleSave = useCallback(async () => {
        await saveLayout.mutateAsync(editLayout);
        setIsEditing(false);
    }, [editLayout, saveLayout]);

    const handleReset = useCallback(async () => {
        await resetLayout.mutateAsync();
        setIsEditing(false);
    }, [resetLayout]);

    const handleAddWidget = useCallback((widget: DashboardWidgetDef) => {
        const spans = SIZE_SPANS[widget.size] || SIZE_SPANS.medium;
        const maxY = editLayout.length > 0
            ? Math.max(...editLayout.map(l => l.y + l.h))
            : 0;
        setEditLayout(prev => [...prev, {
            widget_id: widget.id,
            x: 0,
            y: maxY,
            w: spans.col,
            h: spans.row,
        }]);
        setPickerOpen(false);
    }, [editLayout]);

    const handleRemoveWidget = useCallback((widgetId: string) => {
        setEditLayout(prev => prev.filter(l => l.widget_id !== widgetId));
    }, []);

    const handleLayoutChange = useCallback((newLayout: ReactGridLayout.Layout[]) => {
        if (!isEditing) return;
        setEditLayout(rglToLayout(newLayout));
    }, [isEditing]);

    if (isAuthLoading || isStatsLoading || widgetsLoading || layoutLoading) {
        return <RedWireSpinner message="Synchronizing ops data" />;
    }

    if (!isAuthenticated) return null;

    // Build widget map for quick lookup
    const widgetMap = new Map(widgets.map(w => [w.id, w]));

    return (
        <DashboardLayout>
            <div className="p-6 space-y-5 max-w-7xl mx-auto">

                {/* ── Header + Quick Actions ── */}
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
                    <div>
                        <h1 className="text-2xl font-black text-white tracking-tight flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-red-500 to-orange-600 flex items-center justify-center shadow-lg shadow-red-500/20">
                                <Shield className="h-5 w-5 text-white" />
                            </div>
                            Welcome back, {user?.full_name || user?.username}
                        </h1>
                        <div className="flex items-center gap-3 ml-12 mt-1">
                            <p className="text-slate-500 text-sm flex items-center gap-2">
                                <span className="relative flex h-2 w-2">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                                </span>
                                All systems operational
                            </p>
                            {wsGlobalConnected && (
                                <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400/70 uppercase tracking-wider">
                                    <Wifi className="h-3 w-3" /> Live
                                </span>
                            )}
                            {scopedEngagementName && (
                                <Badge className="bg-purple-500/10 text-purple-400 border-purple-500/20 text-[10px]">
                                    Scoped: {scopedEngagementName}
                                </Badge>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                        {isEditing ? (
                            <>
                                <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)}
                                    className="border-primary/30 text-primary hover:bg-primary/10 h-8 text-xs gap-1.5">
                                    <Plus className="h-3.5 w-3.5" /> Add Widget
                                </Button>
                                <Button size="sm" variant="outline" onClick={handleReset}
                                    className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs gap-1.5">
                                    <RotateCcw className="h-3.5 w-3.5" /> Reset
                                </Button>
                                <Button size="sm" variant="outline" onClick={cancelEditing}
                                    className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs gap-1.5">
                                    <X className="h-3.5 w-3.5" /> Cancel
                                </Button>
                                <Button size="sm" onClick={handleSave} disabled={saveLayout.isPending}
                                    className="bg-green-600 hover:bg-green-500 text-white h-8 text-xs gap-1.5">
                                    <Save className="h-3.5 w-3.5" /> Save Layout
                                </Button>
                            </>
                        ) : (
                            <>
                                <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mr-1 hidden lg:block">
                                    <Zap className="h-3 w-3 inline -mt-0.5 mr-0.5" />Quick Actions
                                </span>
                                <QuickAction icon={Bug} label="Finding" onClick={() => router.push('/findings/new')} color="red" />
                                <QuickAction icon={Server} label="Asset" onClick={() => router.push('/assets/new')} color="cyan" />
                                <Button size="sm" variant="outline" onClick={startEditing}
                                    className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs gap-1.5 ml-2">
                                    <Settings2 className="h-3.5 w-3.5" /> Customize
                                </Button>
                            </>
                        )}
                    </div>
                </div>

                {isEditing && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20">
                        <Move className="h-4 w-4 text-primary" />
                        <span className="text-xs text-primary">
                            <strong>Customize Mode</strong> — Drag widgets to reposition. Use corner handles to resize. Click Save when done.
                        </span>
                        <div className="ml-auto flex items-center gap-2">
                            <span className="text-[10px] text-primary/60 flex items-center gap-1">
                                <Maximize2 className="h-3 w-3" /> Drag corners to resize
                            </span>
                            {layoutData?.is_default && (
                                <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[9px]">Default Layout</Badge>
                            )}
                        </div>
                    </div>
                )}

                {/* ── Widget Grid ── */}
                <div className={isEditing ? 'rgl-editing' : ''}>
                    {currentLayout.length === 0 && isEditing ? (
                        <div className="text-center py-16 border border-dashed border-slate-700 rounded-xl">
                            <Settings2 className="h-8 w-8 text-slate-600 mx-auto mb-3" />
                            <p className="text-slate-500 text-sm">Dashboard is empty</p>
                            <Button size="sm" variant="outline" className="mt-3 border-primary/30 text-primary"
                                onClick={() => setPickerOpen(true)}>
                                <Plus className="h-3.5 w-3.5 mr-1.5" /> Add your first widget
                            </Button>
                        </div>
                    ) : (
                        <DashboardGrid
                            layout={rglLayout}
                            isEditing={isEditing}
                            onLayoutChange={handleLayoutChange}
                        >
                            {currentLayout.map((item) => {
                                const widget = widgetMap.get(item.widget_id);
                                if (!widget) return <div key={item.widget_id} />;
                                return (
                                    <div key={item.widget_id} className="h-full">
                                        {isEditing && (
                                            <>
                                                <div className="rgl-drag-handle absolute inset-x-0 top-0 h-10 z-10 cursor-grab active:cursor-grabbing flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                                                    <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/20 border border-primary/30 backdrop-blur-sm">
                                                        <Move className="h-3 w-3 text-primary" />
                                                        <span className="text-[9px] text-primary font-bold uppercase tracking-wider">Drag</span>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleRemoveWidget(item.widget_id); }}
                                                    className="absolute top-1.5 right-1.5 z-20 w-6 h-6 rounded-full bg-red-500/80 hover:bg-red-500 flex items-center justify-center transition-all shadow-lg"
                                                >
                                                    <X className="h-3 w-3 text-white" />
                                                </button>
                                            </>
                                        )}
                                        <div className="h-full overflow-hidden">
                                            <WidgetRenderer widget={widget} isEditing={isEditing}
                                                engagementId={engagementId}
                                                onRemove={() => handleRemoveWidget(widget.id)} />
                                        </div>
                                    </div>
                                );
                            })}
                        </DashboardGrid>
                    )}
                </div>
            </div>

            {/* Widget Picker Dialog */}
            <WidgetPicker
                open={pickerOpen}
                onOpenChange={setPickerOpen}
                widgets={widgets}
                currentLayout={editLayout}
                onAddWidget={handleAddWidget}
            />
        </DashboardLayout>
    );
}
