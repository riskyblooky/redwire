'use client';

import { useState } from 'react';
import { TagList, TagListTag } from '@/components/ui/tag-list';
import {
    Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import {
    Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from '@/components/ui/command';
import { Checkbox } from '@/components/ui/checkbox';
import { Pencil } from 'lucide-react';
import { toast } from 'sonner';

interface InlineTagsFieldProps {
    /** Current tags, for the read view. */
    tags?: TagListTag[];
    /** All selectable tags for this entity type. */
    allTags: { id: string; name: string; color?: string | null }[];
    selectedIds: string[];
    onSave: (ids: string[]) => Promise<void>;
    canEdit?: boolean;
    max?: number;
}

/**
 * Tags that read as a TagList and, for editors, open a searchable multi-select
 * dropdown (checkbox list). Toggling stages the selection; closing the dropdown
 * commits the full tag_ids set via the caller's onSave (only if it changed).
 */
export function InlineTagsField({
    tags = [],
    allTags,
    selectedIds,
    onSave,
    canEdit = false,
    max = 6,
}: InlineTagsFieldProps) {
    const [open, setOpen] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set(selectedIds));

    const toggle = (id: string) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const commitIfChanged = async (finalSel: Set<string>) => {
        const next = [...finalSel];
        const changed = next.length !== selectedIds.length || next.some(id => !selectedIds.includes(id));
        if (!changed) return;
        try {
            await onSave(next);
            toast.success('Tags updated');
        } catch (e: any) {
            toast.error(e?.response?.data?.detail || e?.message || 'Failed to update tags');
        }
    };

    const handleOpenChange = (o: boolean) => {
        if (o) {
            setSelected(new Set(selectedIds)); // seed from current on open
            setOpen(true);
        } else {
            setOpen(false);
            commitIfChanged(selected); // commit staged selection on close
        }
    };

    const readView = tags.length > 0
        ? <TagList tags={tags} max={max} />
        : canEdit ? <span className="text-xs text-slate-600 italic">no tags</span> : null;

    if (!canEdit) return <>{readView}</>;

    return (
        <span
            className="group/inline inline-flex items-center gap-1"
            onDoubleClick={() => handleOpenChange(true)}
        >
            {readView}
            <Popover open={open} onOpenChange={handleOpenChange}>
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        className="p-0.5 rounded opacity-0 group-hover/inline:opacity-100 data-[state=open]:opacity-100 text-slate-500 hover:text-white transition-opacity"
                        title="Edit tags"
                        aria-label="Edit tags"
                    >
                        <Pencil className="h-3 w-3" />
                    </button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-0 bg-slate-900 border-slate-800 text-white" align="start">
                    <Command className="bg-transparent">
                        <CommandInput placeholder="Search tags…" className="text-xs" />
                        <CommandList>
                            <CommandEmpty className="py-4 text-center text-xs text-slate-500">
                                {allTags.length === 0 ? 'No tags defined for this type.' : 'No tags found.'}
                            </CommandEmpty>
                            <CommandGroup>
                                {allTags.map(t => {
                                    const on = selected.has(t.id);
                                    return (
                                        <CommandItem
                                            key={t.id}
                                            value={t.name}
                                            onSelect={() => toggle(t.id)}
                                            className="gap-2 text-xs cursor-pointer aria-selected:bg-slate-800"
                                        >
                                            <Checkbox checked={on} className="h-3.5 w-3.5 pointer-events-none" />
                                            <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: t.color || '#64748b' }} />
                                            <span className="flex-1 truncate">{t.name}</span>
                                        </CommandItem>
                                    );
                                })}
                            </CommandGroup>
                        </CommandList>
                    </Command>
                </PopoverContent>
            </Popover>
        </span>
    );
}
