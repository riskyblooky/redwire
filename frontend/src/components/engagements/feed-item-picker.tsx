'use client';

import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
    Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from '@/components/ui/command';
import { Check, Crosshair, ChevronsUpDown, Bug, CheckSquare, Server, StickyNote } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFindings } from '@/lib/hooks/use-findings';
import { useTestCases } from '@/lib/hooks/use-testcases';
import { useAssets } from '@/lib/hooks/use-assets';
import { useNotes } from '@/lib/hooks/use-notes';

interface FeedItemPickerProps {
    engagementId: string;
    /** Selected entity ids (activity resource_ids). */
    selected: string[];
    onChange: (ids: string[]) => void;
}

interface Group {
    key: string;
    label: string;
    icon: React.ElementType;
    color: string;
    items: { id: string; label: string }[];
}

/**
 * Searchable multi-select of the engagement's content entities (findings, test
 * cases, assets, notes). Selecting scopes the activity feed to those items'
 * resource_ids. Toggling applies live (like the feed's other filters).
 */
export function FeedItemPicker({ engagementId, selected, onChange }: FeedItemPickerProps) {
    const { data: findings = [] } = useFindings({ engagement_id: engagementId });
    const { data: testcases = [] } = useTestCases(engagementId);
    const { data: assets = [] } = useAssets(engagementId);
    const { data: notes = [] } = useNotes(engagementId);

    const groups: Group[] = useMemo(() => [
        { key: 'finding', label: 'Findings', icon: Bug, color: 'text-red-400', items: findings.map((f: any) => ({ id: f.id, label: f.title })) },
        { key: 'testcase', label: 'Test Cases', icon: CheckSquare, color: 'text-emerald-400', items: testcases.map((t: any) => ({ id: t.id, label: t.title })) },
        { key: 'asset', label: 'Assets', icon: Server, color: 'text-blue-400', items: assets.map((a: any) => ({ id: a.id, label: a.name })) },
        { key: 'note', label: 'Notes', icon: StickyNote, color: 'text-teal-400', items: notes.map((n: any) => ({ id: n.id, label: n.title })) },
    ], [findings, testcases, assets, notes]);

    const selectedSet = new Set(selected);

    const toggle = (id: string) => {
        const next = new Set(selectedSet);
        if (next.has(id)) next.delete(id); else next.add(id);
        onChange([...next]);
    };

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button variant="outline" role="combobox" className="h-8 justify-between gap-2 border-slate-700 bg-slate-900 text-xs font-normal text-slate-300 hover:bg-slate-800 hover:text-white">
                    <span className="flex items-center gap-1.5">
                        <Crosshair className="h-3 w-3 text-slate-400" />
                        {selected.length ? `${selected.length} item${selected.length > 1 ? 's' : ''}` : 'All items'}
                    </span>
                    <ChevronsUpDown className="h-3 w-3 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-0 border-slate-700 bg-slate-900 text-white">
                <Command className="bg-transparent">
                    <CommandInput placeholder="Search findings, test cases, assets, notes…" className="text-xs" />
                    <CommandList className="max-h-72">
                        <CommandEmpty className="py-4 text-center text-xs text-slate-500">No items found.</CommandEmpty>
                        {selected.length > 0 && (
                            <div className="px-2 py-1.5 border-b border-slate-800">
                                <button
                                    type="button"
                                    onClick={() => onChange([])}
                                    className="text-[11px] text-slate-400 hover:text-white"
                                >
                                    Clear {selected.length} selected
                                </button>
                            </div>
                        )}
                        {groups.filter(g => g.items.length > 0).map(g => {
                            const Icon = g.icon;
                            return (
                                <CommandGroup key={g.key} heading={g.label} className="text-slate-500">
                                    {g.items.map(item => {
                                        const on = selectedSet.has(item.id);
                                        return (
                                            <CommandItem
                                                key={item.id}
                                                value={`${g.label} ${item.label}`}
                                                onSelect={() => toggle(item.id)}
                                                className="gap-2 text-xs cursor-pointer aria-selected:bg-slate-800"
                                            >
                                                <Check className={cn('h-3.5 w-3.5 shrink-0', on ? 'opacity-100 text-blue-400' : 'opacity-0')} />
                                                <Icon className={cn('h-3.5 w-3.5 shrink-0', g.color)} />
                                                <span className="flex-1 truncate">{item.label}</span>
                                            </CommandItem>
                                        );
                                    })}
                                </CommandGroup>
                            );
                        })}
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}
