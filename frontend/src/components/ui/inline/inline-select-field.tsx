'use client';

import { useState, useEffect, ReactNode } from 'react';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export interface InlineSelectOption {
    value: string;
    label: string;
    icon?: React.ComponentType<{ className?: string }>;
    iconClass?: string;
    /** Badge classes for the read view when this option is selected. */
    badgeClass?: string;
}

interface InlineSelectFieldProps {
    value: string;
    options: InlineSelectOption[];
    onSave: (value: string) => Promise<void>;
    canEdit?: boolean;
    /** Override the read-view rendering (defaults to a coloured Badge). */
    renderRead?: (opt: InlineSelectOption | undefined, value: string) => ReactNode;
    triggerClassName?: string;
    placeholder?: string;
}

/**
 * An enum/type field that reads as a badge and, on double-click (for editors),
 * opens a dropdown. Picking a value saves immediately (optimistic) — the
 * selected value shows at once and rolls back if the save fails.
 */
export function InlineSelectField({
    value,
    options,
    onSave,
    canEdit = false,
    renderRead,
    triggerClassName,
    placeholder = 'Select…',
}: InlineSelectFieldProps) {
    const [editing, setEditing] = useState(false);
    const [override, setOverride] = useState<string | null>(null);
    const shown = override ?? value;

    // Clear the optimistic override once the server value catches up.
    useEffect(() => {
        if (override !== null && value === override) setOverride(null);
    }, [value, override]);

    const shownOpt = options.find(o => o.value === shown);

    const commit = async (next: string) => {
        setEditing(false);
        if (next === value) return;
        setOverride(next);
        try {
            await onSave(next);
        } catch (e: any) {
            setOverride(null);
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to save');
        }
    };

    const renderOptionInner = (opt: InlineSelectOption | undefined, fallback: string) => {
        if (!opt) return fallback;
        const I = opt.icon;
        return (
            <span className="flex items-center gap-1.5">
                {I && <I className={cn('h-3.5 w-3.5', opt.iconClass)} />}
                <span>{opt.label}</span>
            </span>
        );
    };

    if (editing && canEdit) {
        return (
            <Select
                defaultOpen
                value={shown}
                onValueChange={commit}
                onOpenChange={(open) => { if (!open) setEditing(false); }}
            >
                <SelectTrigger className={cn('h-7 w-auto min-w-[9rem] bg-slate-950/50 border-slate-700 text-xs', triggerClassName)}>
                    <SelectValue placeholder={placeholder}>{renderOptionInner(shownOpt, shown)}</SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-white">
                    {options.map(opt => (
                        <SelectItem key={opt.value} value={opt.value} className="text-xs focus:bg-slate-800">
                            {renderOptionInner(opt, opt.value)}
                        </SelectItem>
                    ))}
                </SelectContent>
            </Select>
        );
    }

    return (
        <span
            className={cn('group/inline relative inline-flex items-center', canEdit && 'cursor-pointer')}
            onDoubleClick={() => canEdit && setEditing(true)}
            title={canEdit ? 'Double-click to edit' : undefined}
        >
            {renderRead
                ? renderRead(shownOpt, shown)
                : <Badge className={cn('px-2 py-0.5', shownOpt?.badgeClass)}>{shownOpt?.label ?? shown}</Badge>}
            {canEdit && (
                <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="ml-1 p-0.5 rounded opacity-0 group-hover/inline:opacity-100 text-slate-500 hover:text-white transition-opacity"
                    title="Edit"
                    aria-label="Edit"
                >
                    <Pencil className="h-3 w-3" />
                </button>
            )}
        </span>
    );
}
