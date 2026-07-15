'use client';

/**
 * StatsPageView — one widget-grid stats tab.
 *
 * A dashboard-style grid of global widgets, but the layout is SHARED
 * (page-owned): an editor's change is what every viewer sees. Editing is
 * gated on MANAGE_STATS_PAGES. Widget data is fetched in the 'stats'
 * context (WidgetDataContext) so custom_query widgets honor the platform
 * Stats Scope Mode instead of assignment-scoping.
 */

import { useState, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Button } from '@/components/ui/button';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Plus, Settings2, Save, X, Move, Maximize2, Loader2, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiErrorMessage } from '@/lib/api';
import WidgetRenderer, { WidgetDataContext } from '@/components/dashboard/widget-renderer';
import WidgetPicker from '@/components/dashboard/widget-picker';
import { SIZE_SPANS, layoutToRGL, rglToLayout } from '@/lib/widget-layout';
import type { DashboardWidgetDef, LayoutItem } from '@/lib/hooks/use-dashboard-widgets';
import { useSaveStatsPageLayout, type StatsPage } from '@/lib/hooks/use-stats-pages';

const DashboardGrid = dynamic(() => import('@/components/dashboard/dashboard-grid'), { ssr: false });

interface StatsPageViewProps {
    page: StatsPage;
    widgets: DashboardWidgetDef[];
    canManage: boolean;
    onRename: () => void;
    onDelete: () => void;
}

export default function StatsPageView({ page, widgets, canManage, onRename, onDelete }: StatsPageViewProps) {
    const saveLayout = useSaveStatsPageLayout();

    const [isEditing, setIsEditing] = useState(false);
    const [editLayout, setEditLayout] = useState<LayoutItem[]>([]);
    const [pickerOpen, setPickerOpen] = useState(false);

    const currentLayout = isEditing ? editLayout : (page.layout || []);
    const rglLayout = useMemo(() => layoutToRGL(currentLayout, widgets), [currentLayout, widgets]);
    const widgetMap = useMemo(() => new Map(widgets.map(w => [w.id, w])), [widgets]);

    const startEditing = useCallback(() => {
        setEditLayout(page.layout || []);
        setIsEditing(true);
    }, [page.layout]);

    const cancelEditing = useCallback(() => {
        setIsEditing(false);
        setEditLayout([]);
    }, []);

    const handleSave = useCallback(async () => {
        try {
            await saveLayout.mutateAsync({ id: page.id, layout: editLayout });
            setIsEditing(false);
            toast.success('Layout saved');
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Failed to save layout'));
        }
    }, [editLayout, page.id, saveLayout]);

    const handleAddWidget = useCallback((widget: DashboardWidgetDef) => {
        const spans = SIZE_SPANS[widget.size] || SIZE_SPANS.medium;
        const maxY = editLayout.length > 0 ? Math.max(...editLayout.map(l => l.y + l.h)) : 0;
        setEditLayout(prev => [...prev, { widget_id: widget.id, x: 0, y: maxY, w: spans.col, h: spans.row }]);
        setPickerOpen(false);
    }, [editLayout]);

    const handleRemoveWidget = useCallback((widgetId: string) => {
        setEditLayout(prev => prev.filter(l => l.widget_id !== widgetId));
    }, []);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handleLayoutChange = useCallback((newLayout: any[]) => {
        if (!isEditing) return;
        setEditLayout(rglToLayout(newLayout));
    }, [isEditing]);

    return (
        <div className="space-y-4">
            {/* Edit toolbar */}
            {canManage && (
                <div className="flex items-center justify-end gap-2">
                    {isEditing ? (
                        <>
                            <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)}
                                className="border-primary/30 text-primary hover:bg-primary/10 h-8 text-xs gap-1.5">
                                <Plus className="h-3.5 w-3.5" /> Add Widget
                            </Button>
                            <Button size="sm" variant="outline" onClick={cancelEditing}
                                className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs gap-1.5">
                                <X className="h-3.5 w-3.5" /> Cancel
                            </Button>
                            <Button size="sm" onClick={handleSave} disabled={saveLayout.isPending}
                                className="bg-green-600 hover:bg-green-500 text-white h-8 text-xs gap-1.5">
                                {saveLayout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                                Save Layout
                            </Button>
                        </>
                    ) : (
                        <Button size="sm" variant="outline" onClick={startEditing}
                            className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 text-xs gap-1.5">
                            <Settings2 className="h-3.5 w-3.5" /> Customize
                        </Button>
                    )}

                    {/* Page actions (rename / delete) collapsed into a menu */}
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button size="icon" variant="outline"
                                className="border-slate-700 text-slate-400 hover:bg-slate-800 h-8 w-8">
                                <MoreVertical className="h-4 w-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent className="bg-slate-900 border-slate-800 text-white" align="end">
                            <DropdownMenuItem
                                className="text-slate-300 focus:bg-slate-800/50 focus:text-white"
                                onClick={onRename}>
                                <Pencil className="h-3.5 w-3.5 mr-2" /> Rename page
                            </DropdownMenuItem>
                            {!page.is_system && (
                                <DropdownMenuItem
                                    className="text-red-400 focus:bg-red-500/10 focus:text-red-400"
                                    onClick={onDelete}>
                                    <Trash2 className="h-3.5 w-3.5 mr-2" /> Delete page
                                </DropdownMenuItem>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            )}

            {isEditing && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/5 border border-primary/20">
                    <Move className="h-4 w-4 text-primary" />
                    <span className="text-xs text-primary">
                        <strong>Customize Mode</strong> — this layout is shared; changes apply for everyone. Drag to reposition, resize from the corner, then Save.
                    </span>
                    <span className="ml-auto text-[10px] text-primary/60 flex items-center gap-1">
                        <Maximize2 className="h-3 w-3" /> Drag corners to resize
                    </span>
                </div>
            )}

            {/* Grid — stats context so custom_query widgets honor Stats Scope Mode */}
            <WidgetDataContext.Provider value="stats">
                {currentLayout.length === 0 ? (
                    <div className="text-center py-16 border border-dashed border-slate-700 rounded-xl">
                        <Settings2 className="h-8 w-8 text-slate-600 mx-auto mb-3" />
                        <p className="text-slate-500 text-sm">This page has no widgets yet.</p>
                        {canManage && (
                            <Button size="sm" variant="outline" className="mt-3 border-primary/30 text-primary"
                                onClick={() => { if (!isEditing) startEditing(); setPickerOpen(true); }}>
                                <Plus className="h-3.5 w-3.5 mr-1.5" /> Add your first widget
                            </Button>
                        )}
                    </div>
                ) : (
                    <div className={isEditing ? 'rgl-editing' : ''}>
                        <DashboardGrid layout={rglLayout} isEditing={isEditing} onLayoutChange={handleLayoutChange}>
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
                                                engagementId={null}
                                                onRemove={() => handleRemoveWidget(widget.id)} />
                                        </div>
                                    </div>
                                );
                            })}
                        </DashboardGrid>
                    </div>
                )}
            </WidgetDataContext.Provider>

            <WidgetPicker
                open={pickerOpen}
                onOpenChange={setPickerOpen}
                widgets={widgets}
                currentLayout={editLayout}
                onAddWidget={handleAddWidget}
            />
        </div>
    );
}
