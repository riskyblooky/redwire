'use client';

/**
 * week-view.tsx — Work Week (Mon-Fri) grid for /calendar
 *
 * Same event-tile look as the Month grid but with 5 taller columns so
 * more events fit before we hit the "+N more" affordance. Density cap is
 * higher than Month (8 vs 3) because each column has ~3x the height.
 *
 * Weekend (Sat/Sun) is intentionally skipped — this is a RedWire ops
 * planner and weekend engagement work is rare enough that hiding those
 * columns is worth the horizontal room.
 */

import { useMemo, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import {
    format, parseISO, startOfWeek, addDays,
    isSameDay, isWithinInterval,
} from 'date-fns';
import { cn } from '@/lib/utils';
import { Target, Clock, TreePalm } from 'lucide-react';
import type { FeedItem } from '@/lib/hooks/use-calendar';
import { DayEventsPopover } from './day-events-popover';

const PHASE_STYLE: Record<string, { tile: string; label: string }> = {
    SCOPING: { tile: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300 border-l-cyan-500', label: 'Scoping' },
    PLANNING: { tile: 'bg-amber-500/10 border-amber-500/20 text-amber-300 border-l-amber-500', label: 'Planning' },
    IN_PROGRESS: { tile: 'bg-purple-500/10 border-purple-500/20 text-purple-300 border-l-purple-500', label: 'In Progress' },
    REPORTING: { tile: 'bg-blue-500/10 border-blue-500/20 text-blue-300 border-l-blue-500', label: 'Reporting' },
};

const ENGAGEMENT_DEFAULT_TILE = 'bg-purple-500/10 border-purple-500/20 text-purple-400 border-l-purple-500';

const WEEK_CAP = 8;

interface WeekViewProps {
    currentDate: Date;
    feed: FeedItem[];
    onSelect: (event: FeedItem) => void;
    onJumpToDay?: (day: Date) => void;
}

export function WeekView({ currentDate, feed, onSelect, onJumpToDay }: WeekViewProps) {
    // Monday of the visible week (weekStartsOn: 1). Work Week = Mon-Fri only.
    const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
    const days = useMemo(
        () => Array.from({ length: 5 }, (_, i) => addDays(weekStart, i)),
        [weekStart],
    );
    const [popoverDay, setPopoverDay] = useState<Date | null>(null);

    return (
        <Card className="border-slate-800 bg-slate-900/50 backdrop-blur-md overflow-hidden">
            <CardContent className="p-0">
                {/* Day headers */}
                <div className="grid grid-cols-5 border-b border-slate-800 bg-slate-800/30">
                    {days.map(day => {
                        const isToday = isSameDay(day, new Date());
                        return (
                            <button
                                key={day.toString()}
                                onClick={() => onJumpToDay?.(day)}
                                className={cn(
                                    'py-3 px-2 text-center border-r border-slate-800 last:border-r-0 transition-colors',
                                    isToday ? 'bg-primary/5' : 'hover:bg-slate-800/40',
                                )}
                            >
                                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                                    {format(day, 'EEE')}
                                </div>
                                <div className={cn(
                                    'text-lg font-bold mt-0.5',
                                    isToday ? 'text-primary' : 'text-white',
                                )}>
                                    {format(day, 'd')}
                                </div>
                            </button>
                        );
                    })}
                </div>

                {/* Day columns */}
                <div className="grid grid-cols-5 min-h-[500px]">
                    {days.map(day => {
                        const dayEvents = feed.filter(e => {
                            const start = parseISO(e.start);
                            const end = parseISO(e.end);
                            return isSameDay(start, day) || isWithinInterval(day, { start, end });
                        });
                        const shown = dayEvents.slice(0, WEEK_CAP);
                        const hidden = dayEvents.length - shown.length;
                        const isToday = isSameDay(day, new Date());

                        return (
                            <div
                                key={day.toString()}
                                className={cn(
                                    'p-2 border-r border-slate-800 last:border-r-0 space-y-1.5',
                                    isToday && 'bg-primary/[0.03]',
                                )}
                            >
                                {dayEvents.length === 0 ? (
                                    <div className="text-[10px] text-slate-700 italic pt-2">Empty</div>
                                ) : (
                                    <>
                                        {shown.map(event => {
                                            const phaseStyle = event.type === 'engagement' && event.phase
                                                ? PHASE_STYLE[event.phase] : null;
                                            const tile = event.type === 'engagement'
                                                ? (phaseStyle?.tile ?? ENGAGEMENT_DEFAULT_TILE)
                                                : event.type === 'ooo'
                                                    ? 'bg-red-500/10 border-red-500/20 text-red-400 border-l-red-500'
                                                    : 'bg-blue-500/10 border-blue-500/20 text-blue-400 border-l-blue-500';
                                            const Icon = event.type === 'engagement' ? Target
                                                : event.type === 'ooo' ? TreePalm : Clock;
                                            return (
                                                <button
                                                    key={event.id}
                                                    onClick={() => onSelect(event)}
                                                    title={event.title}
                                                    className={cn(
                                                        'w-full text-left text-[10px] p-1.5 rounded-md border cursor-pointer hover:brightness-125 transition-all border-l-[3px] shadow-sm font-bold flex items-center gap-1.5',
                                                        tile,
                                                    )}
                                                >
                                                    <Icon className="h-2.5 w-2.5 shrink-0" />
                                                    <span className="truncate">{event.title}</span>
                                                </button>
                                            );
                                        })}
                                        {hidden > 0 && (
                                            <DayEventsPopover
                                                open={popoverDay?.getTime() === day.getTime()}
                                                onOpenChange={o => setPopoverDay(o ? day : null)}
                                                day={day}
                                                events={dayEvents}
                                                onSelect={event => {
                                                    onSelect(event);
                                                    setPopoverDay(null);
                                                }}
                                            >
                                                <button className="w-full text-[10px] text-slate-400 hover:text-white bg-slate-800/40 hover:bg-slate-800 rounded-md py-1 transition-colors">
                                                    +{hidden} more…
                                                </button>
                                            </DayEventsPopover>
                                        )}
                                    </>
                                )}
                            </div>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}
