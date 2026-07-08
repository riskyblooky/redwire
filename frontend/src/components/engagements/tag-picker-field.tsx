'use client';

/**
 * TagPickerField — shared tag chooser used on the engagement create + edit
 * forms. Mirrors the finding/testcase pattern: a scrollable grid of tag
 * pills that toggle in/out of the selected list. Empty tag list falls
 * back to a hint pointing operators at /tags for creating them.
 *
 * Purely presentational; state lives in the parent form.
 */

import { useTags } from '@/lib/hooks/use-tags';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { CheckCircle2, Loader2, TagsIcon } from 'lucide-react';

interface TagPickerFieldProps {
    selected: string[];
    onChange: (ids: string[]) => void;
}

export function TagPickerField({ selected, onChange }: TagPickerFieldProps) {
    const { data: tags = [], isLoading } = useTags();

    const toggle = (id: string) => {
        onChange(
            selected.includes(id)
                ? selected.filter(t => t !== id)
                : [...selected, id],
        );
    };

    return (
        <div className="space-y-2">
            <Label className="text-xs text-slate-500 font-semibold uppercase tracking-widest flex items-center justify-between">
                Tags
                <Badge variant="outline" className="text-[10px] px-1.5 h-4 border-slate-800 text-slate-500">
                    {selected.length} selected
                </Badge>
            </Label>
            {isLoading ? (
                <div className="py-4 text-center">
                    <Loader2 className="h-4 w-4 animate-spin mx-auto text-slate-600" />
                </div>
            ) : tags.length === 0 ? (
                <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-500">
                    <TagsIcon className="h-4 w-4 shrink-0 text-slate-600" />
                    <span>No tags yet — create some at <code className="text-slate-400">/tags</code> and they&apos;ll show up here.</span>
                </div>
            ) : (
                <div className="grid grid-cols-2 gap-1.5 max-h-[220px] overflow-y-auto pr-1">
                    {tags.map(tag => (
                        <div
                            key={tag.id}
                            onClick={() => toggle(tag.id)}
                            className={cn(
                                'flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-all',
                                selected.includes(tag.id)
                                    ? 'bg-slate-800/40 border-slate-700 shadow-xs'
                                    : 'bg-slate-950/20 border-transparent hover:bg-slate-900/40',
                            )}
                        >
                            <div
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{ backgroundColor: tag.color ?? undefined }}
                            />
                            <span className={cn(
                                'text-xs font-medium truncate flex-1',
                                selected.includes(tag.id) ? 'text-white' : 'text-slate-400',
                            )}>
                                {tag.name}
                            </span>
                            {selected.includes(tag.id) && (
                                <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
