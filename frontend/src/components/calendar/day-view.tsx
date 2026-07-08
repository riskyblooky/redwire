'use client';

/**
 * day-view.tsx — Single-day timeline for /calendar
 *
 * Layout:
 *   All-day strip (top)   — engagement phases, OOO blocks, and any event
 *                           spanning >12h. Rendered as pills.
 *   Timed grid (below)    — 24 hour rows @ 44px each. Timed events sit as
 *                           absolutely-positioned coloured blocks.
 *   Now line              — thin red line at the current wall-clock time
 *                           when the visible day IS today.
 *
 * Overlap handling: naive. Overlapping timed events stack in the same
 * column with a slight left offset per overlap depth. Not the full Google
 * Calendar layout algorithm — good enough for RedWire's typical density.
 *
 * Event styling mirrors the /calendar month grid so a user glancing
 * between views recognises the same colour language.
 */

import { useEffect, useMemo, useRef } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import {
    format, parseISO, differenceInMinutes, isSameDay,
    startOfDay, endOfDay,
} from 'date-fns';
import { cn } from '@/lib/utils';
import { Target, Clock, TreePalm } from 'lucide-react';
import type { FeedItem } from '@/lib/hooks/use-calendar';

const HOUR_HEIGHT = 44; // px per hour
const HOURS = Array.from({ length: 24 }, (_, i) => i);
// All-day threshold: anything spanning >= this many minutes lands in the
// all-day strip. Chosen so a 12-hr on-call/OOO block pins to the top
// rather than obscuring the whole timeline.
const ALL_DAY_THRESHOLD_MIN = 12 * 60;

const PHASE_STYLE: Record<string, { tile: string; label: string }> = {
    SCOPING: { tile: 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300', label: 'Scoping' },
    PLANNING: { tile: 'bg-amber-500/15 border-amber-500/40 text-amber-300', label: 'Planning' },
    IN_PROGRESS: { tile: 'bg-purple-500/15 border-purple-500/40 text-purple-300', label: 'In Progress' },
    REPORTING: { tile: 'bg-blue-500/15 border-blue-500/40 text-blue-300', label: 'Reporting' },
};

interface DayViewProps {
    currentDate: Date;
    feed: FeedItem[];
    onSelect: (event: FeedItem) => void;
    selectedId?: string | null;
}

interface TimedLayout {
    item: FeedItem;
    top: number;
    height: number;
    column: number;
    columns: number;
}

/**
 * Assign overlapping timed events to columns so they don't render on top
 * of each other. Sweeps events sorted by start; for each event, reuses
 * the leftmost column whose latest event ends before this one starts.
 */
function layoutTimed(items: Array<{ item: FeedItem; startMin: number; endMin: number }>): TimedLayout[] {
    const sorted = [...items].sort((a, b) => a.startMin - b.startMin);
    // columns[i] = latest end minute currently occupying that column
    const columns: number[] = [];
    const assignments = new Map<string, number>();
    for (const s of sorted) {
        let placed = false;
        for (let i = 0; i < columns.length; i++) {
            if (columns[i] <= s.startMin) {
                columns[i] = s.endMin;
                assignments.set(s.item.id, i);
                placed = true;
                break;
            }
        }
        if (!placed) {
            assignments.set(s.item.id, columns.length);
            columns.push(s.endMin);
        }
    }
    const totalCols = Math.max(columns.length, 1);
    return sorted.map(s => ({
        item: s.item,
        top: (s.startMin / 60) * HOUR_HEIGHT,
        height: Math.max(((s.endMin - s.startMin) / 60) * HOUR_HEIGHT, 20),
        column: assignments.get(s.item.id) ?? 0,
        columns: totalCols,
    }));
}

export function DayView({ currentDate, feed, onSelect, selectedId }: DayViewProps) {
    const scrollRef = useRef<HTMLDivElement>(null);
    const dayStart = startOfDay(currentDate);
    const dayEnd = endOfDay(currentDate);
    const isToday = isSameDay(currentDate, new Date());

    // Split feed into all-day/multi-day pins and timed items constrained to
    // this calendar day. Timed positions are minutes-since-midnight clamped
    // into [0, 1440].
    const { allDay, timedLayout } = useMemo(() => {
        const allDay: FeedItem[] = [];
        const timedRaw: Array<{ item: FeedItem; startMin: number; endMin: number }> = [];

        for (const item of feed) {
            if (!item.start || !item.end) continue;
            const start = parseISO(item.start);
            const end = parseISO(item.end);
            if (end < dayStart || start > dayEnd) continue;

            const spanMin = Math.max(differenceInMinutes(end, start), 0);
            if (spanMin >= ALL_DAY_THRESHOLD_MIN) {
                allDay.push(item);
                continue;
            }

            const clampedStart = start < dayStart ? dayStart : start;
            const clampedEnd = end > dayEnd ? dayEnd : end;
            const startMin = differenceInMinutes(clampedStart, dayStart);
            const endMin = Math.max(differenceInMinutes(clampedEnd, dayStart), startMin + 15);
            timedRaw.push({ item, startMin, endMin });
        }

        return { allDay, timedLayout: layoutTimed(timedRaw) };
    }, [feed, dayStart, dayEnd]);

    // Scroll to 8am on mount so users don't land on the empty pre-dawn hours.
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = 8 * HOUR_HEIGHT;
        }
    }, []);

    const nowMinutes = isToday
        ? new Date().getHours() * 60 + new Date().getMinutes()
        : null;

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
            <CardContent className="p-0">
                {/* Header — the day */}
                <div className="px-4 py-3 border-b border-slate-800 bg-slate-800/30 flex items-center justify-between">
                    <div>
                        <div className="text-xs text-slate-500 uppercase tracking-wider font-medium">
                            {format(currentDate, 'EEEE')}
                        </div>
                        <div className="text-lg font-bold text-white">
                            {format(currentDate, 'MMMM d, yyyy')}
                        </div>
                    </div>
                    {isToday && (
                        <div className="text-[10px] uppercase tracking-wider font-medium text-primary bg-primary/10 border border-primary/30 rounded-full px-2 py-0.5">
                            Today
                        </div>
                    )}
                </div>

                {/* All-day / multi-day strip */}
                {allDay.length > 0 && (
                    <div className="border-b border-slate-800 bg-slate-900/50 px-4 py-2">
                        <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-1.5">
                            All day / multi-day
                        </div>
                        <div className="flex flex-col gap-1">
                            {allDay.map(item => {
                                const phaseStyle = item.type === 'engagement' && item.phase
                                    ? PHASE_STYLE[item.phase] : null;
                                const tile = item.type === 'engagement'
                                    ? (phaseStyle?.tile || 'bg-purple-500/15 border-purple-500/40 text-purple-300')
                                    : item.type === 'ooo'
                                        ? 'bg-red-500/15 border-red-500/40 text-red-300'
                                        : 'bg-blue-500/15 border-blue-500/40 text-blue-300';
                                const Icon = item.type === 'engagement' ? Target
                                    : item.type === 'ooo' ? TreePalm : Clock;
                                return (
                                    <button
                                        key={item.id}
                                        onClick={() => onSelect(item)}
                                        className={cn(
                                            'w-full text-left px-2 py-1.5 rounded-md border text-xs font-medium flex items-center gap-2 transition-all',
                                            tile,
                                            selectedId === item.id ? 'ring-1 ring-white/40' : 'hover:brightness-125',
                                        )}
                                    >
                                        <Icon className="h-3 w-3 shrink-0" />
                                        <span className="truncate flex-1">{item.title}</span>
                                        {phaseStyle && (
                                            <span className="text-[9px] uppercase tracking-wider opacity-70">
                                                {phaseStyle.label}
                                            </span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Timed grid */}
                <div ref={scrollRef} className="relative max-h-[calc(100vh-320px)] overflow-y-auto">
                    <div className="relative" style={{ height: HOUR_HEIGHT * 24 }}>
                        {/* Hour rows */}
                        {HOURS.map(h => (
                            <div
                                key={h}
                                className="absolute left-0 right-0 border-b border-slate-800/60 flex"
                                style={{ top: h * HOUR_HEIGHT, height: HOUR_HEIGHT }}
                            >
                                <div className="w-14 shrink-0 border-r border-slate-800 text-[10px] text-slate-500 font-medium pt-1 pl-2">
                                    {h === 0 ? '' : format(new Date(2000, 0, 1, h), 'ha').toLowerCase()}
                                </div>
                                <div className="flex-1" />
                            </div>
                        ))}

                        {/* Now line */}
                        {nowMinutes !== null && (
                            <div
                                className="absolute left-14 right-0 z-10 pointer-events-none"
                                style={{ top: (nowMinutes / 60) * HOUR_HEIGHT }}
                            >
                                <div className="relative">
                                    <div className="absolute -left-1 -top-1 h-2 w-2 rounded-full bg-red-500" />
                                    <div className="h-0.5 bg-red-500/70" />
                                </div>
                            </div>
                        )}

                        {/* Timed event blocks */}
                        <div className="absolute left-14 right-2 top-0 bottom-0 pointer-events-none">
                            {timedLayout.map(({ item, top, height, column, columns }) => {
                                const widthPct = 100 / columns;
                                const leftPct = column * widthPct;
                                const phaseStyle = item.type === 'engagement' && item.phase
                                    ? PHASE_STYLE[item.phase] : null;
                                const tile = item.type === 'engagement'
                                    ? (phaseStyle?.tile || 'bg-purple-500/15 border-purple-500/40 text-purple-300')
                                    : item.type === 'ooo'
                                        ? 'bg-red-500/15 border-red-500/40 text-red-300'
                                        : 'bg-blue-500/15 border-blue-500/40 text-blue-300';
                                const Icon = item.type === 'engagement' ? Target
                                    : item.type === 'ooo' ? TreePalm : Clock;

                                return (
                                    <button
                                        key={item.id}
                                        onClick={() => onSelect(item)}
                                        className={cn(
                                            'absolute rounded-md border px-2 py-1 text-[10px] font-medium text-left overflow-hidden pointer-events-auto transition-all',
                                            tile,
                                            selectedId === item.id ? 'ring-1 ring-white/40' : 'hover:brightness-125',
                                        )}
                                        style={{
                                            top,
                                            height: height - 2,
                                            left: `calc(${leftPct}% + 2px)`,
                                            width: `calc(${widthPct}% - 4px)`,
                                        }}
                                    >
                                        <div className="flex items-center gap-1">
                                            <Icon className="h-2.5 w-2.5 shrink-0" />
                                            <span className="truncate">{item.title}</span>
                                        </div>
                                        <div className="text-[9px] opacity-70 mt-0.5">
                                            {format(parseISO(item.start), 'h:mma').toLowerCase()}
                                            {' – '}
                                            {format(parseISO(item.end), 'h:mma').toLowerCase()}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
