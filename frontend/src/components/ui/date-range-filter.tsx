'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Input } from '@/components/ui/input';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DateRangeFilterProps {
    /** YYYY-MM-DD (empty string = unset). */
    from: string;
    to: string;
    onChange: (from: string, to: string) => void;
}

const PRESETS: { label: string; days: number }[] = [
    { label: 'Last 7 days', days: 7 },
    { label: 'Last 30 days', days: 30 },
    { label: 'Last 90 days', days: 90 },
    { label: 'Last year', days: 365 },
];

// Local (not UTC) YYYY-MM-DD so day boundaries match the user's calendar.
function toISO(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function fmtShort(s: string): string {
    const d = new Date(`${s}T00:00:00`);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/**
 * A single calendar-icon button that opens quick day presets (Last 7/30/90
 * days, Last year) plus a custom from/to range. Reports the range as two
 * YYYY-MM-DD strings via onChange.
 */
export function DateRangeFilter({ from, to, onChange }: DateRangeFilterProps) {
    const [open, setOpen] = useState(false);
    const [preset, setPreset] = useState<string | null>(null);

    const applyPreset = (days: number, label: string) => {
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - (days - 1)); // inclusive of today
        setPreset(label);
        onChange(toISO(start), toISO(end));
        setOpen(false);
    };

    const clear = () => { setPreset(null); onChange('', ''); };

    const active = !!(from || to);
    const summary = preset
        ? preset
        : active
            ? `${from ? fmtShort(from) : '…'} – ${to ? fmtShort(to) : '…'}`
            : 'Any time';

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    className={cn('h-8 gap-1.5 border-slate-700 bg-slate-900 text-xs font-normal text-slate-300 hover:bg-slate-800 hover:text-white', active && 'text-white')}
                >
                    <CalendarIcon className="h-3 w-3 text-slate-400" />
                    {summary}
                    {active && (
                        <X
                            className="h-3 w-3 text-slate-500 hover:text-white"
                            onClick={(e) => { e.stopPropagation(); clear(); }}
                        />
                    )}
                </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-64 space-y-2 border-slate-700 bg-slate-900 p-2 text-white">
                <div className="grid grid-cols-2 gap-1.5">
                    {PRESETS.map((p) => (
                        <button
                            key={p.label}
                            type="button"
                            onClick={() => applyPreset(p.days, p.label)}
                            className={cn(
                                'rounded border px-2 py-1.5 text-left text-xs transition-colors',
                                preset === p.label ? 'border-blue-500/40 bg-blue-500/10 text-blue-300' : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                            )}
                        >
                            {p.label}
                        </button>
                    ))}
                </div>
                <div className="space-y-1.5 border-t border-slate-800 pt-2">
                    <p className="text-[10px] uppercase tracking-wider text-slate-500">Custom range</p>
                    <div className="flex items-center gap-1">
                        <Input
                            type="date" value={from} title="From date"
                            onChange={(e) => { setPreset(null); onChange(e.target.value, to); }}
                            className="h-7 border-slate-700 bg-slate-950 text-xs"
                        />
                        <span className="text-xs text-slate-600">→</span>
                        <Input
                            type="date" value={to} title="To date"
                            onChange={(e) => { setPreset(null); onChange(from, e.target.value); }}
                            className="h-7 border-slate-700 bg-slate-950 text-xs"
                        />
                    </div>
                </div>
                {active && (
                    <button type="button" onClick={clear} className="text-[11px] text-slate-400 hover:text-white">
                        Clear dates
                    </button>
                )}
            </PopoverContent>
        </Popover>
    );
}
