'use client';

/**
 * personal-gantt.tsx — Personal Gantt timeline view for /calendar
 *
 * A 3-month sliding Gantt chart driven by the same feed that powers the
 * month grid on /calendar. Rows are grouped:
 *
 *   Engagements → one row per unique `engagement_id`, with phase-colored
 *                 segments per feed item (SCOPING / PLANNING / IN_PROGRESS /
 *                 REPORTING). Feed items without a phase collapse into a
 *                 single purple bar spanning the engagement window.
 *   Events      → one row per ops event (blue)
 *   Out of Office → one row per OOO block (red)
 *
 * Bar-positioning math (getPosition, monthLabels, weekMarkers, today
 * marker) mirrors /planning — kept inline rather than extracted because
 * the two views' surrounding chrome is otherwise very different and
 * premature abstraction would obscure both.
 *
 * Clicking a bar surfaces the same inspector event shape as the month
 * grid so the parent's inspector sidebar keeps working unchanged.
 */

import { useMemo } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import {
    format, startOfMonth, endOfMonth, addMonths, subMonths,
    parseISO, differenceInDays, eachWeekOfInterval,
    max as dateMax, min as dateMin,
} from 'date-fns';
import { cn } from '@/lib/utils';
import { Target, Clock, TreePalm, CalendarDays } from 'lucide-react';
import type { FeedItem } from '@/lib/hooks/use-calendar';

const PHASE_COLORS: Record<string, { bg: string; label: string }> = {
    SCOPING: { bg: 'bg-cyan-500', label: 'Scoping' },
    PLANNING: { bg: 'bg-amber-500', label: 'Planning' },
    IN_PROGRESS: { bg: 'bg-purple-500', label: 'In Progress' },
    REPORTING: { bg: 'bg-blue-500', label: 'Reporting' },
};

interface PersonalGanttViewProps {
    currentMonth: Date;
    feed: FeedItem[];
    onSelect: (event: FeedItem) => void;
    selectedId?: string | null;
}

interface GanttRow {
    key: string;
    label: string;
    sublabel?: string;
    icon: 'engagement' | 'event' | 'ooo';
    items: FeedItem[];
}

export function PersonalGanttView({
    currentMonth,
    feed,
    onSelect,
    selectedId,
}: PersonalGanttViewProps) {
    // 3-month sliding window centered on the currently-visible month
    const viewStart = startOfMonth(subMonths(currentMonth, 1));
    const viewEnd = endOfMonth(addMonths(currentMonth, 1));
    const totalDays = Math.max(differenceInDays(viewEnd, viewStart), 1);

    // Month labels stripe
    const monthLabels = useMemo(() => {
        const labels: { label: string; left: number; width: number }[] = [];
        let cursor = viewStart;
        while (cursor < viewEnd) {
            const mStart = dateMax([startOfMonth(cursor), viewStart]);
            const mEnd = dateMin([endOfMonth(cursor), viewEnd]);
            const leftDays = differenceInDays(mStart, viewStart);
            const widthDays = differenceInDays(mEnd, mStart) + 1;
            labels.push({
                label: format(cursor, 'MMMM yyyy'),
                left: (leftDays / totalDays) * 100,
                width: (widthDays / totalDays) * 100,
            });
            cursor = addMonths(startOfMonth(cursor), 1);
        }
        return labels;
    }, [viewStart, viewEnd, totalDays]);

    const weekMarkers = useMemo(
        () => eachWeekOfInterval({ start: viewStart, end: viewEnd }, { weekStartsOn: 1 }),
        [viewStart, viewEnd],
    );

    const todayPosition = useMemo(() => {
        const today = new Date();
        if (today < viewStart || today > viewEnd) return null;
        return (differenceInDays(today, viewStart) / totalDays) * 100;
    }, [viewStart, viewEnd, totalDays]);

    // Position a single feed item's bar within the viewport
    const getPosition = (start: string, end: string) => {
        const s = parseISO(start);
        const e = parseISO(end);
        const clampedStart = dateMax([s, viewStart]);
        const clampedEnd = dateMin([e, viewEnd]);
        const leftDays = differenceInDays(clampedStart, viewStart);
        const widthDays = Math.max(differenceInDays(clampedEnd, clampedStart), 1);
        return {
            left: Math.max(0, Math.min((leftDays / totalDays) * 100, 100)),
            width: Math.max(0.5, Math.min((widthDays / totalDays) * 100, 100 - (leftDays / totalDays) * 100)),
        };
    };

    // Group feed items into rows.
    //   - Engagements group by engagement_id (their phase items live together)
    //   - Events and OOO each get one row per item
    // Only feed items that overlap the viewport survive.
    const rows: GanttRow[] = useMemo(() => {
        const inWindow = feed.filter(item => {
            if (!item.start || !item.end) return false;
            const s = parseISO(item.start);
            const e = parseISO(item.end);
            return s <= viewEnd && e >= viewStart;
        });

        const engagementBuckets = new Map<string, FeedItem[]>();
        const events: FeedItem[] = [];
        const ooos: FeedItem[] = [];

        for (const item of inWindow) {
            if (item.type === 'engagement') {
                const key = item.engagement_id || item.id;
                const existing = engagementBuckets.get(key) || [];
                existing.push(item);
                engagementBuckets.set(key, existing);
            } else if (item.type === 'ooo') {
                ooos.push(item);
            } else {
                events.push(item);
            }
        }

        const engagementRows: GanttRow[] = Array.from(engagementBuckets.entries())
            .map(([key, items]): GanttRow => {
                // Sort phase items chronologically so tooltips read left-to-right
                items.sort((a, b) => parseISO(a.start).getTime() - parseISO(b.start).getTime());
                // The first item's title has shape "<engagement name> (<client>)" —
                // use it as the row label so we don't need a second lookup.
                const first = items[0];
                return {
                    key: `eng-${key}`,
                    label: first.title,
                    sublabel: undefined,
                    icon: 'engagement',
                    items,
                };
            })
            // Sort rows by earliest bar start so the timeline reads top-to-bottom
            .sort((a, b) => {
                const aStart = Math.min(...a.items.map(i => parseISO(i.start).getTime()));
                const bStart = Math.min(...b.items.map(i => parseISO(i.start).getTime()));
                return aStart - bStart;
            });

        const eventRows: GanttRow[] = events
            .sort((a, b) => parseISO(a.start).getTime() - parseISO(b.start).getTime())
            .map(e => ({
                key: `ev-${e.id}`,
                label: e.title,
                icon: 'event',
                items: [e],
            }));

        const oooRows: GanttRow[] = ooos
            .sort((a, b) => parseISO(a.start).getTime() - parseISO(b.start).getTime())
            .map(o => ({
                key: `ooo-${o.id}`,
                label: o.title,
                icon: 'ooo',
                items: [o],
            }));

        return [...engagementRows, ...eventRows, ...oooRows];
    }, [feed, viewStart, viewEnd]);

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
            <CardContent className="p-0">
                {/* Month labels */}
                <div className="relative flex">
                    <div className="w-[200px] shrink-0 border-r border-slate-800 bg-slate-800/30" />
                    <div className="flex-1 relative h-8 border-b border-slate-800 bg-slate-800/30">
                        {monthLabels.map((m, i) => (
                            <div
                                key={i}
                                className="absolute top-0 h-full flex items-center px-3 text-xs font-bold text-white/70 uppercase tracking-wider border-r border-slate-700/30"
                                style={{ left: `${m.left}%`, width: `${m.width}%` }}
                            >
                                {m.label}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Week ticks */}
                <div className="relative flex">
                    <div className="w-[200px] shrink-0 border-r border-slate-800 bg-slate-900/30" />
                    <div className="flex-1 relative h-6 border-b border-slate-800/80 bg-slate-900/30">
                        {weekMarkers.map((w, i) => {
                            const pct = (differenceInDays(w, viewStart) / totalDays) * 100;
                            if (pct < 0 || pct > 100) return null;
                            return (
                                <div
                                    key={i}
                                    className="absolute top-0 h-full border-l border-slate-700/30 flex items-center pl-1.5"
                                    style={{ left: `${pct}%` }}
                                >
                                    <span className="text-[9px] text-slate-600 font-medium">
                                        {format(w, 'MMM d')}
                                    </span>
                                </div>
                            );
                        })}
                        {todayPosition !== null && (
                            <div
                                className="absolute top-0 h-full w-0.5 bg-red-500 z-10"
                                style={{ left: `${todayPosition}%` }}
                            />
                        )}
                    </div>
                </div>

                {/* Rows */}
                <TooltipProvider delayDuration={200}>
                    {rows.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
                            <CalendarDays className="h-10 w-10 text-slate-700" />
                            <p className="text-sm text-slate-500">Nothing scheduled in this window</p>
                            <p className="text-xs text-slate-600">
                                Try widening the range or turning off filters
                            </p>
                        </div>
                    ) : (
                        <div className="divide-y divide-slate-800/50">
                            {rows.map(row => {
                                const isSelected = row.items.some(i => i.id === selectedId);
                                return (
                                    <div
                                        key={row.key}
                                        className={cn(
                                            'flex items-center transition-colors border-l-2',
                                            isSelected
                                                ? 'bg-primary/5 border-l-primary'
                                                : 'hover:bg-slate-800/30 border-l-transparent',
                                        )}
                                    >
                                        {/* Name column */}
                                        <div className="w-[200px] shrink-0 min-w-0 px-3 py-2.5 border-r border-slate-800/50">
                                            <div className="flex items-center gap-1.5 min-w-0">
                                                {row.icon === 'engagement' && (
                                                    <Target className="h-3 w-3 text-purple-400 shrink-0" />
                                                )}
                                                {row.icon === 'event' && (
                                                    <Clock className="h-3 w-3 text-blue-400 shrink-0" />
                                                )}
                                                {row.icon === 'ooo' && (
                                                    <TreePalm className="h-3 w-3 text-red-400 shrink-0" />
                                                )}
                                                <span className="text-xs font-medium text-white truncate">
                                                    {row.label}
                                                </span>
                                            </div>
                                            {row.sublabel && (
                                                <span className="text-[10px] text-slate-600 truncate block ml-4.5">
                                                    {row.sublabel}
                                                </span>
                                            )}
                                        </div>

                                        {/* Timeline lane */}
                                        <div className="flex-1 relative h-10 bg-slate-800/20 border-y border-slate-800/40">
                                            {todayPosition !== null && (
                                                <div
                                                    className="absolute top-0 h-full w-px bg-red-500/40 z-[5]"
                                                    style={{ left: `${todayPosition}%` }}
                                                />
                                            )}
                                            {row.items.map(item => {
                                                const pos = getPosition(item.start, item.end);
                                                let barClass = '';
                                                let tooltipLabel = item.title;

                                                if (item.type === 'engagement') {
                                                    const phaseColor = item.phase
                                                        ? PHASE_COLORS[item.phase]
                                                        : null;
                                                    barClass = phaseColor?.bg || 'bg-purple-500';
                                                    tooltipLabel = phaseColor
                                                        ? `${phaseColor.label} — ${format(parseISO(item.start), 'MMM d')} → ${format(parseISO(item.end), 'MMM d')}`
                                                        : item.title;
                                                } else if (item.type === 'ooo') {
                                                    barClass = 'bg-red-500';
                                                } else {
                                                    barClass = 'bg-blue-500';
                                                }

                                                return (
                                                    <Tooltip key={item.id}>
                                                        <TooltipTrigger asChild>
                                                            <div
                                                                onClick={() => onSelect(item)}
                                                                className={cn(
                                                                    'absolute top-1.5 bottom-1.5 rounded-sm cursor-pointer transition-opacity hover:opacity-100',
                                                                    barClass,
                                                                    selectedId === item.id ? 'opacity-100 ring-1 ring-white/50' : 'opacity-70',
                                                                )}
                                                                style={{
                                                                    left: `${pos.left}%`,
                                                                    width: `${pos.width}%`,
                                                                    minWidth: '3px',
                                                                }}
                                                            />
                                                        </TooltipTrigger>
                                                        <TooltipContent
                                                            side="top"
                                                            className="bg-slate-800 border-slate-700 text-xs"
                                                        >
                                                            <p className="font-semibold text-white">{tooltipLabel}</p>
                                                            <p className="text-slate-500 mt-0.5">
                                                                {format(parseISO(item.start), 'MMM d, yyyy')}
                                                                {' — '}
                                                                {format(parseISO(item.end), 'MMM d, yyyy')}
                                                            </p>
                                                        </TooltipContent>
                                                    </Tooltip>
                                                );
                                            })}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </TooltipProvider>
            </CardContent>
        </Card>
    );
}
