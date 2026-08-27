'use client';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
    Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from '@/components/ui/command';
import { Check, ChevronsUpDown } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { UserAvatar } from '@/components/ui/user-avatar';
import { cn } from '@/lib/utils';

export interface MultiSelectOption {
    value: string;
    label: string;
    sublabel?: string;
    icon?: React.ComponentType<{ className?: string }>;
    iconClass?: string;
    /** When set, the label renders as a colour-tinted badge (with the icon inside). */
    badgeClass?: string;
    /** A hex colour (e.g. a tag colour) — renders the label as a tinted pill. */
    color?: string | null;
    /** When set, a profile photo avatar is shown instead of an icon. */
    avatar?: { id: string; full_name?: string; username?: string; profile_photo?: string | null };
}

interface MultiSelectFilterProps {
    /** Shown on the trigger when nothing is selected (e.g. "All users"). */
    label: string;
    options: MultiSelectOption[];
    selected: string[];
    onChange: (values: string[]) => void;
    /** Leading icon on the trigger. */
    icon?: React.ComponentType<{ className?: string }>;
    /** Singular noun for the "N nouns" trigger summary (e.g. "user"). */
    countNoun?: string;
    searchable?: boolean;
    searchPlaceholder?: string;
    triggerClassName?: string;
    contentClassName?: string;
}

/**
 * A compact searchable multi-select filter (Popover + Command). Toggling applies
 * live via onChange; the trigger summarises the count. Used for the activity
 * feed's type / action / user filters.
 */
export function MultiSelectFilter({
    label,
    options,
    selected,
    onChange,
    icon: TriggerIcon,
    countNoun = 'selected',
    searchable = true,
    searchPlaceholder = 'Search…',
    triggerClassName,
    contentClassName,
}: MultiSelectFilterProps) {
    const selectedSet = new Set(selected);

    const toggle = (value: string) => {
        const next = new Set(selectedSet);
        if (next.has(value)) next.delete(value); else next.add(value);
        onChange([...next]);
    };

    const summary = selected.length
        ? `${selected.length} ${countNoun}${selected.length > 1 ? 's' : ''}`
        : label;

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" className={cn('h-8 justify-between gap-2 border-slate-700 bg-slate-900 text-xs font-normal text-slate-300 hover:bg-slate-800 hover:text-white', triggerClassName)}>
                    <span className="flex items-center gap-1.5">
                        {TriggerIcon && <TriggerIcon className="h-3 w-3 text-slate-400" />}
                        {summary}
                    </span>
                    <ChevronsUpDown className="h-3 w-3 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className={cn('w-56 p-0 border-slate-700 bg-slate-900 text-white', contentClassName)}>
                <Command className="bg-transparent">
                    {searchable && <CommandInput placeholder={searchPlaceholder} className="text-xs" />}
                    <CommandList className="max-h-72">
                        <CommandEmpty className="py-4 text-center text-xs text-slate-500">No matches.</CommandEmpty>
                        {selected.length > 0 && (
                            <div className="px-2 py-1.5 border-b border-slate-800">
                                <button type="button" onClick={() => onChange([])} className="text-[11px] text-slate-400 hover:text-white">
                                    Clear {selected.length} selected
                                </button>
                            </div>
                        )}
                        <CommandGroup>
                            {options.map(opt => {
                                const on = selectedSet.has(opt.value);
                                const OptIcon = opt.icon;
                                return (
                                    <CommandItem
                                        key={opt.value}
                                        value={`${opt.label} ${opt.sublabel ?? ''}`}
                                        onSelect={() => toggle(opt.value)}
                                        className="gap-2 text-xs cursor-pointer aria-selected:bg-slate-800"
                                    >
                                        <Check className={cn('h-3.5 w-3.5 shrink-0', on ? 'opacity-100 text-blue-400' : 'opacity-0')} />
                                        {opt.avatar
                                            ? <UserAvatar user={opt.avatar} className="h-4 w-4 shrink-0" />
                                            : (!opt.badgeClass && !opt.color && OptIcon) ? <OptIcon className={cn('h-3.5 w-3.5 shrink-0', opt.iconClass)} /> : null}
                                        {opt.badgeClass
                                            ? <Badge className={cn('gap-1 h-5 px-1.5 text-[10px] font-medium border', opt.badgeClass)}>
                                                {OptIcon && <OptIcon className="h-3 w-3" />}
                                                {opt.label}
                                            </Badge>
                                            : opt.color
                                                ? <span className="inline-flex h-5 items-center rounded-full border px-1.5 text-[10px] font-medium truncate max-w-[160px]"
                                                        style={{ backgroundColor: `${opt.color}1a`, color: opt.color, borderColor: `${opt.color}40` }}>
                                                    {opt.label}
                                                </span>
                                                : <span className="flex-1 truncate">{opt.label}</span>}
                                        {opt.sublabel && <span className="text-[10px] text-slate-500 shrink-0">{opt.sublabel}</span>}
                                    </CommandItem>
                                );
                            })}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}
