'use client';

import { useState, useEffect, ReactNode } from 'react';
import {
    Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from '@/components/ui/command';
import { Check, Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export interface InlineComboboxOption {
    value: string;
    label: string;
    color?: string | null;
}

interface InlineComboboxFieldProps {
    value: string;
    options: InlineComboboxOption[];
    onSave: (value: string) => Promise<void>;
    canEdit?: boolean;
    placeholder?: string;
    /** Read view when value is empty (and editing is allowed). */
    emptyLabel?: string;
    /** Override the read-view rendering (defaults to a colour-tinted badge). */
    renderRead?: (opt: InlineComboboxOption | undefined, value: string) => ReactNode;
}

/** A colour-tinted badge for an option value. */
function ColorBadge({ label, color }: { label: string; color?: string | null }) {
    if (!color) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">{label}</span>;
    }
    return (
        <span
            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border"
            style={{ backgroundColor: `${color}1a`, color, borderColor: `${color}40` }}
        >
            {label}
        </span>
    );
}

/**
 * A single-select, searchable enum/type field. Reads as a colour-tinted badge
 * and, for editors, opens a searchable dropdown (Popover + Command). Picking a
 * value saves immediately (optimistic) and rolls back on failure.
 */
export function InlineComboboxField({
    value,
    options,
    onSave,
    canEdit = false,
    placeholder = 'Search…',
    emptyLabel = 'none',
    renderRead,
}: InlineComboboxFieldProps) {
    const [open, setOpen] = useState(false);
    const [override, setOverride] = useState<string | null>(null);
    const shown = override ?? value;

    useEffect(() => {
        if (override !== null && value === override) setOverride(null);
    }, [value, override]);

    const shownOpt = options.find(o => o.value === shown);

    const commit = async (next: string) => {
        setOpen(false);
        if (next === value) return;
        setOverride(next);
        try {
            await onSave(next);
        } catch (e: any) {
            setOverride(null);
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
        }
    };

    const readView = renderRead
        ? renderRead(shownOpt, shown)
        : shown
            ? <ColorBadge label={shownOpt?.label ?? shown} color={shownOpt?.color} />
            : canEdit ? <span className="text-xs text-slate-600 italic">{emptyLabel}</span> : null;

    if (!canEdit) return <>{readView}</>;

    return (
        <span
            className="group/inline inline-flex items-center gap-1"
            onDoubleClick={() => setOpen(true)}
        >
            {readView}
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        className="p-0.5 rounded opacity-0 group-hover/inline:opacity-100 data-[state=open]:opacity-100 text-slate-500 hover:text-white transition-opacity"
                        title="Edit"
                        aria-label="Edit"
                    >
                        <Pencil className="h-3 w-3" />
                    </button>
                </PopoverTrigger>
                <PopoverContent className="w-56 p-0 bg-slate-900 border-slate-800 text-white" align="start">
                    <Command className="bg-transparent">
                        <CommandInput placeholder={placeholder} className="text-xs" />
                        <CommandList>
                            <CommandEmpty className="py-4 text-center text-xs text-slate-500">No matches.</CommandEmpty>
                            <CommandGroup>
                                {options.map(opt => (
                                    <CommandItem
                                        key={opt.value}
                                        value={opt.label}
                                        onSelect={() => commit(opt.value)}
                                        className="gap-2 text-xs cursor-pointer aria-selected:bg-slate-800"
                                    >
                                        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: opt.color || '#64748b' }} />
                                        <span className="flex-1 truncate">{opt.label}</span>
                                        {opt.value === shown && <Check className="h-3.5 w-3.5 text-primary" />}
                                    </CommandItem>
                                ))}
                            </CommandGroup>
                        </CommandList>
                    </Command>
                </PopoverContent>
            </Popover>
        </span>
    );
}
