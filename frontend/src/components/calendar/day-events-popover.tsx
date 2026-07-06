'use client';

/**
 * day-events-popover.tsx — "+N more…" popover shared by Month and Week
 * grids on /calendar. Lists every feed item for that day (no cap) and
 * calls back with the picked one so the parent's inspector sidebar can
 * update.
 */

import { ReactNode } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { Target, Clock, TreePalm } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import type { FeedItem } from '@/lib/hooks/use-calendar';

const PHASE_STYLE: Record<string, { tile: string; label: string }> = {
    SCOPING: { tile: 'bg-cyan-500/10 border-cyan-500/20 text-cyan-300 border-l-cyan-500', label: 'Scoping' },
    PLANNING: { tile: 'bg-amber-500/10 border-amber-500/20 text-amber-300 border-l-amber-500', label: 'Planning' },
    IN_PROGRESS: { tile: 'bg-purple-500/10 border-purple-500/20 text-purple-300 border-l-purple-500', label: 'In Progress' },
    REPORTING: { tile: 'bg-blue-500/10 border-blue-500/20 text-blue-300 border-l-blue-500', label: 'Reporting' },
};
const ENGAGEMENT_DEFAULT_TILE = 'bg-purple-500/10 border-purple-500/20 text-purple-400 border-l-purple-500';

interface DayEventsPopoverProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    day: Date;
    events: FeedItem[];
    onSelect: (event: FeedItem) => void;
    children: ReactNode;
}

export function DayEventsPopover({
    open, onOpenChange, day, events, onSelect, children,
}: DayEventsPopoverProps) {
    return (
        <Popover open={open} onOpenChange={onOpenChange}>
            <PopoverTrigger asChild>{children}</PopoverTrigger>
            <PopoverContent
                side="bottom"
                align="start"
                className="w-72 p-0 bg-slate-900 border-slate-700 shadow-xl"
            >
                <div className="px-3 py-2 border-b border-slate-800 bg-slate-800/40">
                    <div className="text-[10px] text-slate-500 uppercase tracking-widest font-medium">
                        {format(day, 'EEEE')}
                    </div>
                    <div className="text-sm font-bold text-white">
                        {format(day, 'MMMM d')}
                    </div>
                    <div className="text-[10px] text-slate-600 mt-0.5">
                        {events.length} event{events.length === 1 ? '' : 's'}
                    </div>
                </div>
                <div className="max-h-72 overflow-y-auto p-2 space-y-1.5">
                    {events.map(event => {
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
                                className={cn(
                                    'w-full text-left text-[11px] p-2 rounded-md border cursor-pointer hover:brightness-125 transition-all border-l-[3px]',
                                    tile,
                                )}
                            >
                                <div className="flex items-center gap-1.5">
                                    <Icon className="h-3 w-3 shrink-0" />
                                    <span className="font-bold truncate flex-1">{event.title}</span>
                                </div>
                                <div className="text-[9px] opacity-70 mt-0.5 ml-4.5">
                                    {format(parseISO(event.start), 'MMM d, h:mma').toLowerCase()}
                                    {' – '}
                                    {format(parseISO(event.end), 'MMM d, h:mma').toLowerCase()}
                                </div>
                            </button>
                        );
                    })}
                </div>
            </PopoverContent>
        </Popover>
    );
}
