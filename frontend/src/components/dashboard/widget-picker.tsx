'use client';

/**
 * WidgetPicker — dialog for browsing and adding widgets to the dashboard.
 */

import { useState } from 'react';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    Briefcase, Bug, AlertTriangle, CheckSquare, Target, Trash2,
    Activity, BarChart3, CircleDot, Users, Calendar, TrendingUp,
    UserCheck, ClipboardCheck, Server, Clock, Shield, Flame, Eye, Zap,
    Plus, Search, LayoutGrid,
} from 'lucide-react';
import type { DashboardWidgetDef, LayoutItem } from '@/lib/hooks/use-dashboard-widgets';

const ICON_MAP: Record<string, any> = {
    Briefcase, Bug, AlertTriangle, CheckSquare, Target, Trash2,
    Activity, BarChart3, CircleDot, Users, Calendar, TrendingUp,
    UserCheck, ClipboardCheck, Server, Clock, Shield, Flame, Eye, Zap,
};

const SIZE_LABELS: Record<string, string> = {
    small: '1×1', medium: '2×1', large: '2×2', wide: '3×1', full: '4×1',
};

const TYPE_LABELS: Record<string, string> = {
    stat_card: 'Stat Card', bar_chart: 'Bar Chart', pie_chart: 'Pie Chart',
    area_chart: 'Area Chart', stacked_bar: 'Stacked Bar', gauge: 'Gauge',
    table: 'Table', list: 'List',
};

const CATEGORY_COLORS: Record<string, string> = {
    overview: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    findings: 'bg-red-500/10 text-red-400 border-red-500/20',
    engagements: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    operators: 'bg-green-500/10 text-green-400 border-green-500/20',
    clients: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    custom: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
};

interface WidgetPickerProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    widgets: DashboardWidgetDef[];
    currentLayout: LayoutItem[];
    onAddWidget: (widget: DashboardWidgetDef) => void;
}

export default function WidgetPicker({ open, onOpenChange, widgets, currentLayout, onAddWidget }: WidgetPickerProps) {
    const [search, setSearch] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

    const usedWidgetIds = new Set(currentLayout.map(l => l.widget_id));

    const filtered = widgets.filter(w => {
        if (search && !w.name.toLowerCase().includes(search.toLowerCase())) return false;
        if (selectedCategory && w.category !== selectedCategory) return false;
        return true;
    });

    const categories = [...new Set(widgets.map(w => w.category))];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden bg-slate-950 border-slate-800">
                <DialogHeader>
                    <DialogTitle className="text-white flex items-center gap-2">
                        <LayoutGrid className="h-5 w-5 text-primary" />
                        Add Widget
                    </DialogTitle>
                    <DialogDescription>
                        Browse available widgets and add them to your dashboard.
                    </DialogDescription>
                </DialogHeader>

                {/* Search + Filter */}
                <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
                        <Input
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Search widgets..."
                            className="pl-9 bg-slate-900 border-slate-700 text-white placeholder:text-slate-500"
                        />
                    </div>
                </div>

                {/* Category pills */}
                <div className="flex gap-1.5 flex-wrap">
                    <button
                        onClick={() => setSelectedCategory(null)}
                        className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full transition-all
                            ${!selectedCategory ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                    >
                        All
                    </button>
                    {categories.map(cat => (
                        <button
                            key={cat}
                            onClick={() => setSelectedCategory(cat === selectedCategory ? null : cat)}
                            className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full transition-all
                                ${cat === selectedCategory ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                        >
                            {cat}
                        </button>
                    ))}
                </div>

                {/* Widget grid */}
                <div className="overflow-y-auto max-h-[50vh] pr-1 -mr-1 space-y-2">
                    {filtered.length === 0 && (
                        <p className="text-slate-600 text-sm text-center py-8 italic">No widgets match your search</p>
                    )}
                    {filtered.map(widget => {
                        const isUsed = usedWidgetIds.has(widget.id);
                        const Icon = ICON_MAP[widget.icon || ''] || BarChart3;
                        return (
                            <div
                                key={widget.id}
                                className={`flex items-center gap-3 p-3 rounded-lg border transition-all
                                    ${isUsed
                                        ? 'border-slate-800/30 bg-slate-900/20 opacity-50'
                                        : 'border-slate-800/60 bg-slate-900/40 hover:border-primary/30 hover:bg-primary/5'}`}
                            >
                                <div className="w-9 h-9 rounded-lg bg-slate-800/80 flex items-center justify-center shrink-0">
                                    <Icon className="h-4 w-4 text-slate-400" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-semibold text-white">{widget.name}</span>
                                        <Badge variant="outline" className={`text-[9px] px-1.5 h-4 border ${CATEGORY_COLORS[widget.category] || ''}`}>
                                            {widget.category}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-500">
                                        <span>{TYPE_LABELS[widget.widget_type] || widget.widget_type}</span>
                                        <span className="text-slate-700">·</span>
                                        <span>Size: {SIZE_LABELS[widget.size] || widget.size}</span>
                                        {widget.is_system && <><span className="text-slate-700">·</span><span className="text-slate-600">System</span></>}
                                    </div>
                                </div>
                                <Button
                                    size="sm"
                                    variant={isUsed ? 'outline' : 'default'}
                                    disabled={isUsed}
                                    onClick={() => onAddWidget(widget)}
                                    className={isUsed
                                        ? 'border-slate-700 text-slate-500 h-7 text-xs'
                                        : 'bg-primary hover:bg-primary/90 text-white h-7 text-xs gap-1'}
                                >
                                    {isUsed ? 'Added' : <><Plus className="h-3 w-3" /> Add</>}
                                </Button>
                            </div>
                        );
                    })}
                </div>
            </DialogContent>
        </Dialog>
    );
}
